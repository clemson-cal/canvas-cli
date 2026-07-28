#!/usr/bin/env python3
"""Configuration loading and the Canvas LMS REST API client."""

import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import json
import os
import re
from pathlib import Path
from typing import Optional

import requests

from canvas_cli.md2html import convert, DEFAULT_THEME_COLOR


CONFIG_FILE = ".canvas.json"


def get_config(config_path: Optional[Path] = None) -> dict:
    """Load Canvas configuration from file or environment.

    Config file format (.canvas.json):
    {
        "api_url": "https://YOUR-INSTITUTION.instructure.com",
        "api_token": "your-token-here",
        "course_id": "123456",
        "theme_color": "#2C3E50"
    }

    ``theme_color`` is optional — it sets the hex accent color used for h2
    headings, table headers, and links in the HTML rendered from markdown.

    Environment variables (override config file):
        CANVAS_API_URL, CANVAS_API_TOKEN, CANVAS_COURSE_ID, CANVAS_THEME_COLOR
    """
    config = {}

    # Try config file
    if config_path is None:
        config_path = Path.cwd() / CONFIG_FILE

    if config_path.exists():
        config = json.loads(config_path.read_text())

    # Environment overrides
    if url := os.environ.get("CANVAS_API_URL"):
        config["api_url"] = url
    if token := os.environ.get("CANVAS_API_TOKEN"):
        config["api_token"] = token
    if course_id := os.environ.get("CANVAS_COURSE_ID"):
        config["course_id"] = course_id
    if theme := os.environ.get("CANVAS_THEME_COLOR"):
        config["theme_color"] = theme

    return config


class CanvasAPI:
    """Simple Canvas LMS API client."""

    def __init__(
        self,
        api_url: str,
        api_token: str,
        course_id: str,
        theme_color: str = DEFAULT_THEME_COLOR,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_token = api_token
        self.course_id = course_id
        self.theme_color = theme_color
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_token}"

    def _url(self, endpoint: str) -> str:
        return f"{self.api_url}/api/v1/courses/{self.course_id}/{endpoint}"

    def _paginated_get(self, url: str, params: Optional[dict] = None) -> list[dict]:
        """GET a Canvas endpoint, following rel=next Link headers to exhaust pagination."""
        params = dict(params or {})
        params.setdefault("per_page", 100)
        results: list[dict] = []
        next_url: Optional[str] = url
        next_params: Optional[dict] = params
        while next_url:
            response = self.session.get(next_url, params=next_params)
            response.raise_for_status()
            page = response.json()
            if isinstance(page, list):
                results.extend(page)
            else:
                results.append(page)
            # Parse Link header for rel=next
            next_url = None
            next_params = None
            link_header = response.headers.get("Link", "")
            for part in link_header.split(","):
                segs = part.strip().split(";")
                if len(segs) < 2:
                    continue
                url_part = segs[0].strip().strip("<>")
                rel_part = segs[1].strip()
                if rel_part == 'rel="next"':
                    next_url = url_part
                    break
        return results

    def list_courses(self) -> list[dict]:
        """List all courses for the authenticated user."""
        response = self.session.get(
            f"{self.api_url}/api/v1/courses",
            params={"per_page": 100},
        )
        response.raise_for_status()
        return response.json()

    def list_assignments(self) -> list[dict]:
        """List all assignments in the course."""
        response = self.session.get(self._url("assignments"), params={"per_page": 100})
        response.raise_for_status()
        return response.json()

    def get_assignment(self, assignment_id: int) -> dict:
        """Get a specific assignment."""
        response = self.session.get(self._url(f"assignments/{assignment_id}"))
        response.raise_for_status()
        return response.json()

    def find_assignment_by_name(self, name: str) -> Optional[dict]:
        """Find an assignment by name."""
        for assignment in self.list_assignments():
            if assignment["name"] == name:
                return assignment
        return None

    def create_assignment(
        self,
        name: str,
        description: str,
        points_possible: float = 3.0,
        submission_types: list[str] = None,
        published: bool = False,
        due_at: str = None,
    ) -> dict:
        """Create a new assignment."""
        if submission_types is None:
            submission_types = ["online_upload"]

        data = {
            "assignment[name]": name,
            "assignment[description]": description,
            "assignment[points_possible]": points_possible,
            "assignment[submission_types][]": submission_types,
            "assignment[published]": str(published).lower(),
        }
        if due_at:
            data["assignment[due_at]"] = due_at

        response = self.session.post(self._url("assignments"), data=data)
        response.raise_for_status()
        return response.json()

    def update_assignment(
        self,
        assignment_id: int,
        name: str = None,
        description: str = None,
        points_possible: float = None,
        submission_types: list[str] = None,
        published: bool = None,
        due_at: str = None,
    ) -> dict:
        """Update an existing assignment."""
        data = {}
        if name is not None:
            data["assignment[name]"] = name
        if description is not None:
            data["assignment[description]"] = description
        if points_possible is not None:
            data["assignment[points_possible]"] = points_possible
        if submission_types is not None:
            data["assignment[submission_types][]"] = submission_types
        if published is not None:
            data["assignment[published]"] = str(published).lower()
        if due_at is not None:
            data["assignment[due_at]"] = due_at

        response = self.session.put(
            self._url(f"assignments/{assignment_id}"), data=data
        )
        response.raise_for_status()
        return response.json()

    # --- Gradebook ---

    def list_students(self) -> list[dict]:
        """List all students enrolled in the course."""
        return self._paginated_get(
            self._url("users"),
            params={"enrollment_type[]": "student"},
        )

    def list_student_enrollments(self) -> list[dict]:
        """List student enrollments (includes current_score / final_score in grades)."""
        return self._paginated_get(
            self._url("enrollments"),
            params={"type[]": "StudentEnrollment", "state[]": "active"},
        )

    def list_all_submissions(self, assignment_ids: Optional[list[int]] = None) -> list[dict]:
        """List submissions for all students across all (or selected) assignments.

        Returns a flat list of submission dicts, each with user_id, assignment_id, score.
        """
        params: dict = {"student_ids[]": "all"}
        if assignment_ids:
            params["assignment_ids[]"] = [str(a) for a in assignment_ids]
        return self._paginated_get(
            self._url("students/submissions"),
            params=params,
        )

    # --- File uploads ---

    def upload_file(self, file_path: Path, folder: str = "uploads") -> dict:
        """Upload a file to the course files area.

        Returns:
            The file record dict, including 'url' for the download link.
        """
        file_path = file_path.resolve()

        # Step 1: Notify Canvas of the upload
        response = self.session.post(
            self._url("files"),
            data={
                "name": file_path.name,
                "parent_folder_path": folder,
                "size": file_path.stat().st_size,
            },
        )
        response.raise_for_status()
        upload_info = response.json()

        # Step 2: Upload the file data
        with open(file_path, "rb") as f:
            upload_response = requests.post(
                upload_info["upload_url"],
                data=upload_info.get("upload_params", {}),
                files={"file": f},
            )
        upload_response.raise_for_status()
        return upload_response.json()

    def upload_image(self, file_path: Path) -> str:
        """Upload an image and return its direct download URL."""
        result = self.upload_file(file_path, folder="images")
        return result["url"]

    # --- Syllabus ---

    def get_syllabus(self) -> dict:
        """Get the course syllabus."""
        response = self.session.get(
            f"{self.api_url}/api/v1/courses/{self.course_id}",
            params={"include[]": "syllabus_body"},
        )
        response.raise_for_status()
        return response.json()

    def update_syllabus(self, body: str) -> dict:
        """Update the course syllabus."""
        response = self.session.put(
            f"{self.api_url}/api/v1/courses/{self.course_id}",
            data={"course[syllabus_body]": body},
        )
        response.raise_for_status()
        return response.json()

    def upload_syllabus(self, md_path: Path) -> dict:
        """Upload a markdown file as the course syllabus."""
        html_content = convert(md_path, standalone=False, upload_image=self.upload_image, upload_file=self.upload_file, theme_color=self.theme_color)
        return self.update_syllabus(html_content)

    # --- Quizzes ---

    def list_quizzes(self) -> list[dict]:
        """List all quizzes in the course."""
        response = self.session.get(self._url("quizzes"), params={"per_page": 100})
        response.raise_for_status()
        return response.json()

    def find_quiz_by_title(self, title: str) -> Optional[dict]:
        """Find a quiz by title."""
        for quiz in self.list_quizzes():
            if quiz["title"] == title:
                return quiz
        return None

    def create_quiz(self, data: dict) -> dict:
        """Create a new quiz."""
        response = self.session.post(self._url("quizzes"), data=data)
        response.raise_for_status()
        return response.json()

    def update_quiz(self, quiz_id: int, data: dict) -> dict:
        """Update an existing quiz."""
        response = self.session.put(self._url(f"quizzes/{quiz_id}"), data=data)
        response.raise_for_status()
        return response.json()

    def create_quiz_question(self, quiz_id: int, question_data: dict) -> dict:
        """Create a question in a quiz.

        Args:
            quiz_id: The quiz ID.
            question_data: Dict with keys: question_name, question_text,
                          question_type, points_possible, answers.
                          answers is a list of dicts with answer_text, answer_weight.
        """
        answers = []
        for ans in question_data["answers"]:
            a = {
                "answer_text": ans["answer_text"],
                "answer_weight": ans["answer_weight"],
            }
            if "answer_match_right" in ans:
                a["answer_match_right"] = ans["answer_match_right"]
            if "answer_comment_html" in ans:
                a["answer_comment_html"] = ans["answer_comment_html"]
            answers.append(a)

        payload = {
            "question": {
                "question_name": question_data["question_name"],
                "question_text": question_data["question_text"],
                "question_type": question_data["question_type"],
                "points_possible": question_data["points_possible"],
                "answers": answers,
            }
        }
        if "matching_answer_incorrect_matches" in question_data:
            payload["question"]["matching_answer_incorrect_matches"] = question_data["matching_answer_incorrect_matches"]

        response = self.session.post(
            self._url(f"quizzes/{quiz_id}/questions"), json=payload
        )
        response.raise_for_status()
        return response.json()

    def delete_quiz_questions(self, quiz_id: int) -> None:
        """Delete all questions from a quiz (for re-upload)."""
        response = self.session.get(
            self._url(f"quizzes/{quiz_id}/questions"),
            params={"per_page": 100},
        )
        response.raise_for_status()
        for q in response.json():
            self.session.delete(
                self._url(f"quizzes/{quiz_id}/questions/{q['id']}")
            ).raise_for_status()

    # --- Pages ---

    def list_pages(self) -> list[dict]:
        """List all pages in the course."""
        response = self.session.get(self._url("pages"), params={"per_page": 100})
        response.raise_for_status()
        return response.json()

    def find_page_by_title(self, title: str) -> Optional[dict]:
        """Find a page by title."""
        for page in self.list_pages():
            if page["title"] == title:
                return page
        return None

    def create_page(
        self,
        title: str,
        body: str,
        published: bool = False,
    ) -> dict:
        """Create a new page."""
        data = {
            "wiki_page[title]": title,
            "wiki_page[body]": body,
            "wiki_page[published]": str(published).lower(),
        }
        response = self.session.post(self._url("pages"), data=data)
        response.raise_for_status()
        return response.json()

    def update_page(
        self,
        url_or_id: str,
        title: str = None,
        body: str = None,
        published: bool = None,
    ) -> dict:
        """Update an existing page."""
        data = {}
        if title is not None:
            data["wiki_page[title]"] = title
        if body is not None:
            data["wiki_page[body]"] = body
        if published is not None:
            data["wiki_page[published]"] = str(published).lower()

        response = self.session.put(self._url(f"pages/{url_or_id}"), data=data)
        response.raise_for_status()
        return response.json()

    def upload_page(
        self,
        md_path: Path,
        publish: bool = False,
        update: bool = True,
    ) -> dict:
        """Upload a markdown file as a page.

        Args:
            md_path: Path to markdown file.
            publish: Whether to publish immediately.
            update: If True, update existing page with same title.

        Returns:
            The created/updated page data.
        """
        md_content = md_path.read_text()
        html_content = convert(md_path, standalone=False, upload_image=self.upload_image, upload_file=self.upload_file, theme_color=self.theme_color)

        # Extract title from first h1
        title = md_path.stem
        for line in md_content.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # Check if page exists
        existing = self.find_page_by_title(title) if update else None

        if existing:
            # Only change published state if --publish is specified;
            # otherwise pass None to preserve existing state
            new_published = True if publish else None
            return self.update_page(
                existing["url"],
                body=html_content,
                published=new_published,
            )
        else:
            return self.create_page(
                title=title,
                body=html_content,
                published=publish,
            )

    def upload_markdown(
        self,
        md_path: Path,
        points: float = 3.0,
        publish: bool = False,
        update: bool = True,
    ) -> dict:
        """Upload a markdown file as an assignment.

        Args:
            md_path: Path to markdown file.
            points: Points possible.
            publish: Whether to publish immediately.
            update: If True, update existing assignment with same name.

        Returns:
            The created/updated assignment data.
        """
        md_content = md_path.read_text()
        html_content = convert(md_path, standalone=False, upload_image=self.upload_image, upload_file=self.upload_file, theme_color=self.theme_color)

        # Extract name from first h1
        name = md_path.stem
        for line in md_content.split("\n"):
            if line.startswith("# "):
                name = line[2:].strip()
                break

        # Extract due date (format: **Due**: M/D/YY)
        due_at = None
        due_match = re.search(r'\*\*Due\*\*:\s*(\d{1,2})/(\d{1,2})/(\d{2,4})', md_content)
        if due_match:
            month, day, year = due_match.groups()
            if len(year) == 2:
                year = "20" + year
            # Canvas expects ISO8601, set to 2:00 PM local time
            due_at = f"{year}-{int(month):02d}-{int(day):02d}T14:00:00"

        # Extract points (format: **Points**: N)
        points_match = re.search(r'\*\*Points\*\*:\s*(\d+(?:\.\d+)?)', md_content)
        if points_match:
            points = float(points_match.group(1))

        # Check if assignment exists
        existing = self.find_assignment_by_name(name) if update else None

        if existing:
            # Only change published state if --publish is specified;
            # otherwise pass None to preserve existing state
            new_published = True if publish else None
            return self.update_assignment(
                existing["id"],
                description=html_content,
                points_possible=points,
                submission_types=["online_upload"],
                published=new_published,
                due_at=due_at,
            )
        else:
            return self.create_assignment(
                name=name,
                description=html_content,
                points_possible=points,
                published=publish,
                due_at=due_at,
            )
