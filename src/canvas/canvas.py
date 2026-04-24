#!/usr/bin/env python3
"""Upload assignments to Canvas LMS."""

import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import argparse
import json
import os
import re
from pathlib import Path
from typing import Optional

import requests

from canvas.md2html import convert, DEFAULT_THEME_COLOR
from canvas.md2tex import (
    convert as convert_to_tex,
    compile_to_pdf as compile_tex_to_pdf,
    open_file as open_file_cmd,
)


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


def _student_sort_key(student: dict) -> str:
    """Sort students by sortable_name (Last, First) when available."""
    return (student.get("sortable_name") or student.get("name") or "").lower()


def _assignment_sort_key(assignment: dict) -> tuple:
    """Sort assignments by position, then due date, then id."""
    return (
        assignment.get("position") if assignment.get("position") is not None else 9999,
        assignment.get("due_at") or "",
        assignment.get("id", 0),
    )


def build_gradebook(
    students: list[dict],
    assignments: list[dict],
    submissions: list[dict],
) -> dict:
    """Index submissions by (user_id, assignment_id) and return a gradebook dict.

    Returns a dict with keys: students, assignments, scores (user_id -> aid -> score),
    and per-student totals (earned, possible) computed from assignment points_possible
    where scored (None scores are treated as missing and excluded from 'possible').
    """
    # Index scores: submissions may have score=None for ungraded/missing
    scores: dict[int, dict[int, Optional[float]]] = {}
    for sub in submissions:
        uid = sub.get("user_id")
        aid = sub.get("assignment_id")
        if uid is None or aid is None:
            continue
        scores.setdefault(uid, {})[aid] = sub.get("score")

    assignment_points = {a["id"]: float(a.get("points_possible") or 0) for a in assignments}

    # Per-student totals: sum of points earned / sum of points possible across scored assignments.
    # We include every published assignment in 'possible' (final-grade style) — unsubmitted = 0 earned.
    totals: dict[int, dict[str, float]] = {}
    for student in students:
        uid = student["id"]
        earned = 0.0
        possible = 0.0
        for a in assignments:
            pts = assignment_points.get(a["id"], 0.0)
            possible += pts
            score = scores.get(uid, {}).get(a["id"])
            if score is not None:
                earned += float(score)
        totals[uid] = {"earned": earned, "possible": possible}

    return {
        "students": students,
        "assignments": assignments,
        "scores": scores,
        "totals": totals,
    }


def render_gradebook_table(
    gradebook: dict,
    show_total: bool = False,
    console=None,
) -> None:
    """Render the gradebook as a rich table.

    Args:
        gradebook: Output of build_gradebook().
        show_total: If True, show the final column as "earned/possible"
                    points. Otherwise, show a percentage.
        console: Optional rich.Console to render into (defaults to stdout).
    """
    from rich.console import Console
    from rich.table import Table
    from rich import box

    if console is None:
        console = Console()

    students = sorted(gradebook["students"], key=_student_sort_key)
    assignments = sorted(gradebook["assignments"], key=_assignment_sort_key)
    scores = gradebook["scores"]
    totals = gradebook["totals"]

    grand_possible = sum(float(a.get("points_possible") or 0) for a in assignments)

    final_header = f"Final ({grand_possible:g} pts)" if show_total else "Final %"
    title = "Gradebook (points)" if show_total else "Gradebook (percent)"

    table = Table(
        title=title,
        box=box.SIMPLE_HEAVY,
        header_style="bold",
        show_lines=False,
    )
    table.add_column("Student", style="bold", no_wrap=True)
    for a in assignments:
        pts = float(a.get("points_possible") or 0)
        table.add_column(
            f"{a['name']}\n[dim]/{pts:g}[/dim]",
            justify="right",
            no_wrap=False,
        )
    table.add_column(final_header, justify="right", style="bold")

    for student in students:
        uid = student["id"]
        row = [student.get("sortable_name") or student.get("name") or str(uid)]
        for a in assignments:
            score = scores.get(uid, {}).get(a["id"])
            if score is None:
                row.append("[dim]—[/dim]")
            else:
                pts = float(a.get("points_possible") or 0)
                if pts > 0 and score / pts < 0.6:
                    row.append(f"[red]{score:g}[/red]")
                else:
                    row.append(f"{score:g}")

        t = totals.get(uid, {"earned": 0.0, "possible": 0.0})
        earned = t["earned"]
        possible = t["possible"]

        if show_total:
            row.append(f"{earned:g} / {possible:g}")
        else:
            pct = (100.0 * earned / possible) if possible > 0 else 0.0
            style = "red" if pct < 60 else ("yellow" if pct < 70 else "green")
            row.append(f"[{style}]{pct:.1f}%[/{style}]")

        table.add_row(*row)

    console.print(table)


def render_gradebook_with_pager(gradebook: dict, show_total: bool = False) -> None:
    """Render the gradebook into ``less -SR`` so wide tables are horizontally scrollable.

    Renders at a very wide fixed console width with forced ANSI colors, then
    pipes the styled output into ``less -SR`` (``-S`` = chop long lines, ``-R`` =
    preserve color escapes). Falls back to normal rendering if ``less`` isn't
    on PATH.
    """
    import os
    import shutil
    import subprocess
    from io import StringIO
    from rich.console import Console

    less_path = shutil.which("less")
    if not less_path:
        render_gradebook_table(gradebook, show_total=show_total)
        return

    # Render to a buffer at a fixed wide width with forced colors. The table
    # shrinks to its natural width, so this just prevents rich from squeezing
    # columns to the terminal; it doesn't pad to 400 chars.
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, color_system="truecolor", width=400)
    render_gradebook_table(gradebook, show_total=show_total, console=console)

    # Pipe to `less -SR`. -S chops lines (no wrap → horizontal scroll with
    # arrow keys), -R passes through ANSI color escapes.
    pager = subprocess.Popen(
        [less_path, "-SR"],
        stdin=subprocess.PIPE,
        env={**os.environ, "LESSSECURE": "1"},
    )
    try:
        pager.communicate(buf.getvalue().encode("utf-8"))
    except (BrokenPipeError, KeyboardInterrupt):
        pass


def _build_gradebook_app(gradebook: dict, show_total: bool = False):
    """Build the Textual App for the gradebook. Separated from ``.run()`` so tests can
    run it headlessly via ``App.run_test()``.
    """
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.widgets import DataTable, Footer, Header
    from rich.text import Text

    students = sorted(gradebook["students"], key=_student_sort_key)
    assignments = sorted(gradebook["assignments"], key=_assignment_sort_key)
    scores = gradebook["scores"]
    totals = gradebook["totals"]
    grand_possible = sum(float(a.get("points_possible") or 0) for a in assignments)
    final_header = f"Final ({grand_possible:g} pts)" if show_total else "Final %"

    class GradebookApp(App):
        TITLE = "Gradebook"
        SUB_TITLE = "← → to scroll · q to quit"
        CSS = """
        Screen { layout: vertical; }
        DataTable { height: 1fr; }
        """
        BINDINGS = [
            Binding("q", "quit", "Quit", priority=True),
            Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        ]

        def compose(self) -> ComposeResult:
            yield Header()
            yield DataTable(zebra_stripes=True, cursor_type="row")
            yield Footer()

        def on_mount(self) -> None:
            table = self.query_one(DataTable)

            # Columns. Student first so fixed_columns=1 pins it.
            student_width = max(
                len("Student"),
                max((len(s.get("sortable_name") or s.get("name") or "") for s in students), default=8),
            )
            table.add_column(Text("Student", style="bold"), width=student_width + 2, key="student")

            for a in assignments:
                pts = float(a.get("points_possible") or 0)
                # Two-line header: name over "/pts"
                header = Text.assemble(
                    (a["name"], "bold"),
                    "\n",
                    (f"/{pts:g}", "dim"),
                )
                col_width = max(len(a["name"]), len(f"/{pts:g}")) + 2
                table.add_column(header, width=col_width, key=f"a{a['id']}")

            table.add_column(Text(final_header, style="bold"), width=len(final_header) + 4, key="final")

            # Rows
            for s in students:
                uid = s["id"]
                name = s.get("sortable_name") or s.get("name") or str(uid)
                row: list = [Text(name, style="bold")]
                for a in assignments:
                    score = scores.get(uid, {}).get(a["id"])
                    if score is None:
                        row.append(Text("—", style="dim", justify="right"))
                    else:
                        pts = float(a.get("points_possible") or 0)
                        style = "red" if pts > 0 and score / pts < 0.6 else ""
                        row.append(Text(f"{score:g}", style=style, justify="right"))

                t = totals.get(uid, {"earned": 0.0, "possible": 0.0})
                earned, possible = t["earned"], t["possible"]
                if show_total:
                    row.append(Text(f"{earned:g} / {possible:g}", style="bold", justify="right"))
                else:
                    pct = (100.0 * earned / possible) if possible > 0 else 0.0
                    style = "bold red" if pct < 60 else ("bold yellow" if pct < 70 else "bold green")
                    row.append(Text(f"{pct:.1f}%", style=style, justify="right"))

                table.add_row(*row, key=str(uid))

            # Pin the Student column so it stays visible while scrolling.
            table.fixed_columns = 1

    return GradebookApp()


def render_gradebook_textual(gradebook: dict, show_total: bool = False) -> None:
    """Render the gradebook as an interactive Textual DataTable with a sticky Student column.

    Arrow keys move the cursor / scroll the assignment columns; the Student
    column stays pinned on the left. Press ``q`` or Ctrl-C to quit.
    """
    try:
        import textual  # noqa: F401  (imported just to probe availability)
    except ImportError:
        print("Error: textual is not installed. Run: pip install textual", flush=True)
        return
    _build_gradebook_app(gradebook, show_total=show_total).run()


def cmd_ls_gradebook(api: CanvasAPI, args) -> int:
    """Show the course gradebook as a formatted table."""
    # Filter assignments: only published, optionally by name filter
    assignments = [a for a in api.list_assignments() if a.get("published")]
    if args.assignment:
        wanted = {s.strip() for s in args.assignment.split(",") if s.strip()}
        assignments = [a for a in assignments if a["name"] in wanted]
    if not assignments:
        print("No (published, matching) assignments found.")
        return 1

    students = api.list_students()
    if not students:
        print("No students enrolled in this course.")
        return 1

    assignment_ids = [a["id"] for a in assignments]
    submissions = api.list_all_submissions(assignment_ids=assignment_ids)

    gradebook = build_gradebook(students, assignments, submissions)

    if args.json:
        # JSON output: compact per-student records
        out = []
        score_map = gradebook["scores"]
        assignment_points = {a["id"]: float(a.get("points_possible") or 0) for a in assignments}
        for s in sorted(students, key=_student_sort_key):
            t = gradebook["totals"][s["id"]]
            pct = (100.0 * t["earned"] / t["possible"]) if t["possible"] > 0 else 0.0
            out.append({
                "id": s["id"],
                "name": s.get("sortable_name") or s.get("name"),
                "scores": {
                    a["name"]: {
                        "score": score_map.get(s["id"], {}).get(a["id"]),
                        "points_possible": assignment_points[a["id"]],
                    }
                    for a in assignments
                },
                "earned": t["earned"],
                "possible": t["possible"],
                "final_percent": pct,
            })
        print(json.dumps(out, indent=2))
        return 0

    if getattr(args, "tui", False):
        render_gradebook_textual(gradebook, show_total=args.total)
    elif getattr(args, "pager", False):
        render_gradebook_with_pager(gradebook, show_total=args.total)
    else:
        render_gradebook_table(gradebook, show_total=args.total)
    return 0


def cmd_ls_assignments(api: CanvasAPI, args) -> int:
    """List assignments in the course."""
    assignments = api.list_assignments()
    if args.json:
        print(json.dumps(assignments, indent=2))
    else:
        for a in assignments:
            status = "published" if a.get("published") else "draft"
            print(f"{a['id']:>8}  [{status:>9}]  {a['name']}")
    return 0


def cmd_ls_pages(api: CanvasAPI, args) -> int:
    """List pages in the course."""
    pages = api.list_pages()
    if args.json:
        print(json.dumps(pages, indent=2))
    else:
        for p in pages:
            status = "published" if p.get("published") else "draft"
            print(f"{p['url']:<30}  [{status:>9}]  {p['title']}")
    return 0


def cmd_ls_courses(api: CanvasAPI, args) -> int:
    """List all courses."""
    courses = api.list_courses()
    if args.json:
        print(json.dumps(courses, indent=2))
    else:
        for c in courses:
            print(f"{c['id']:>8}  {c.get('name', 'N/A')}")
    return 0


def cmd_ls_syllabus(api: CanvasAPI, args) -> int:
    """Show the course syllabus."""
    course = api.get_syllabus()
    if args.json:
        print(json.dumps(course, indent=2))
    else:
        body = course.get("syllabus_body") or "(empty)"
        print(f"Course: {course.get('name', 'N/A')}")
        print(f"Syllabus length: {len(body)} characters")
    return 0


def cmd_up_assignment(api: CanvasAPI, args) -> int:
    """Upload markdown files as assignments."""
    for file in args.files:
        if not file.exists():
            print(f"Error: {file} not found")
            continue
        result = api.upload_markdown(
            file,
            points=args.points,
            publish=args.publish,
            update=not args.no_update,
        )
        action = "Updated" if api.find_assignment_by_name(result["name"]) else "Created"
        print(f"{action} assignment: {result['name']} (id={result['id']})")
    return 0


def cmd_up_page(api: CanvasAPI, args) -> int:
    """Upload markdown files as pages."""
    for file in args.files:
        if not file.exists():
            print(f"Error: {file} not found")
            continue
        result = api.upload_page(
            file,
            publish=args.publish,
            update=not args.no_update,
        )
        action = "Updated" if api.find_page_by_title(result["title"]) else "Created"
        print(f"{action} page: {result['title']} (url={result['url']})")
    return 0


def render_quiz_text(title: str, question_payloads: list[dict], total_points: float, points_per_statement: float) -> str:
    """Render quiz as plain text for terminal output."""
    import re as _re
    def strip_latex(s):
        # \(...\) -> just the math, \[...\] -> just the math
        s = _re.sub(r'\\\((.+?)\\\)', r'$\1$', s)
        s = _re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', s)
        # Strip HTML tags
        s = _re.sub(r'<[^>]+>', '', s)
        return s

    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  {title}")
    lines.append(f"  {len(question_payloads)} statements · {total_points:.1f} pts total · {points_per_statement:.4f} per statement")
    lines.append(f"{'=' * 60}")

    for i, qp in enumerate(question_payloads, 1):
        lines.append("")
        lines.append(f"Q{i}. {qp['question_name']} ({qp['points_possible']:.2f} pts)")
        lines.append(f"{'─' * 50}")
        lines.append(strip_latex(qp['question_text']))
        lines.append("")
        for ans in qp['answers']:
            text = strip_latex(ans['answer_text'])
            if 'answer_match_right' in ans:
                match = ans['answer_match_right']
                lines.append(f"  {text}  →  {match}")
            else:
                correct = ans['answer_weight'] == 100
                mark = '✓' if correct else '✗'
                lines.append(f"  [{mark}] {text}")
            comment = ans.get('answer_comment_html', '')
            if comment:
                lines.append(f"      → {strip_latex(comment)}")
        lines.append("")

    return '\n'.join(lines)


def render_quiz_html(title: str, question_payloads: list[dict], total_points: float, points_per_statement: float) -> str:
    """Render quiz question payloads as a self-contained HTML file for preview."""
    questions_html = []
    for i, qp in enumerate(question_payloads, 1):
        answers_html = []
        for ans in qp["answers"]:
            comment = ans.get("answer_comment_html", "")
            comment_block = f'<div class="comment">{comment}</div>' if comment else ""
            if "answer_match_right" in ans:
                match = ans["answer_match_right"]
                color = "#2d7d2d" if match == "True" else "#888"
                answers_html.append(
                    f'<div class="answer" style="border-left: 3px solid {color};">'
                    f'{ans["answer_text"]} &rarr; <strong>{match}</strong>'
                    f'{comment_block}</div>'
                )
            else:
                correct = ans["answer_weight"] == 100
                marker = "&#x2611;" if correct else "&#x2610;"
                color = "#2d7d2d" if correct else "#888"
                answers_html.append(
                    f'<div class="answer" style="border-left: 3px solid {color};">'
                    f'<span class="marker">{marker}</span> {ans["answer_text"]}'
                    f'{comment_block}</div>'
                )
        answers_joined = "\n".join(answers_html)
        questions_html.append(
            f'<div class="question">'
            f'<h2>Q{i}. {qp["question_name"]} '
            f'<span class="pts">({qp["points_possible"]:.2f} pts)</span></h2>'
            f'{qp["question_text"]}'
            f'<div class="answers">{answers_joined}</div>'
            f'</div>'
        )

    body = "\n".join(questions_html)
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>{title} (Preview)</title>
<script>
  window.MathJax = {{ tex: {{ inlineMath: [['\\\\(','\\\\)']], displayMath: [['\\\\[','\\\\]']] }} }};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" async></script>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 2em auto; padding: 0 1em; line-height: 1.5; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: .3em; }}
  .subtitle {{ color: #555; margin-top: -0.8em; margin-bottom: 1.5em; }}
  .question {{ margin-bottom: 2em; background: #f9f9f9; padding: 1em 1.2em; border-radius: 6px; }}
  .question h2 {{ margin-top: 0; font-size: 1.1em; }}
  .pts {{ font-weight: normal; color: #888; font-size: 0.9em; }}
  .answers {{ margin-top: 0.8em; }}
  .answer {{ padding: 0.4em 0.6em; margin: 0.3em 0; }}
  .marker {{ font-size: 1.1em; }}
  .comment {{ margin-top: 0.3em; padding: 0.3em 0.6em; background: #eef6ee; border-radius: 4px; font-size: 0.9em; color: #444; }}
  .legend {{ margin-bottom: 1.5em; padding: 0.6em 1em; background: #f0f0f0; border-radius: 4px; font-size: 0.9em; }}
</style>
</head><body>
<h1>{title}</h1>
<p class="subtitle">{len(question_payloads)} statements &middot; {total_points:.1f} points total &middot; {points_per_statement:.4f} per statement</p>
<div class="legend">&#x2611; = correct &nbsp;&nbsp; &#x2610; = incorrect &nbsp;&nbsp; <span style="background:#eef6ee;padding:0.1em 0.4em;border-radius:3px;">green box</span> = explanation shown to student</div>
{body}
</body></html>"""


def cmd_up_quiz(api: CanvasAPI, args) -> int:
    """Generate and upload a quiz from the question bank."""
    from canvas.quiz import parse_quiz_bank, sample_quiz, build_canvas_quiz_data

    if not args.file.exists():
        print(f"Error: {args.file} not found")
        return 1

    # Parse question bank
    questions = parse_quiz_bank(args.file)
    if not questions:
        print("Error: No questions found in quiz bank")
        return 1

    # Filter by question numbers if specified
    question_numbers = None
    if args.questions:
        question_numbers = [int(n) for n in args.questions.split(",")]

    # Sample statements
    num_questions = getattr(args, 'num_questions', None)
    quiz_items = sample_quiz(
        questions,
        sample_size=args.sample,
        seed=args.seed,
        question_numbers=question_numbers,
        num_questions=num_questions,
    )

    if not quiz_items:
        print("Error: No questions matched the selection")
        return 1

    # Build due date
    due_at = None
    if args.due:
        due_match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', args.due)
        if due_match:
            month, day, year = due_match.groups()
            if len(year) == 2:
                year = "20" + year
            due_at = f"{year}-{int(month):02d}-{int(day):02d}T14:00:00"

    # Compute points per statement from total
    total_statements = sum(len(stmts) for _, stmts in quiz_items)
    points_per_statement = args.points / total_statements if total_statements > 0 else 0

    # Build Canvas payloads
    quiz_data, question_payloads = build_canvas_quiz_data(
        title=args.title,
        quiz_items=quiz_items,
        points_per_statement=points_per_statement,
        due_at=due_at,
        published=args.publish,
        allowed_attempts=args.attempts,
    )

    # Dry-run: render preview without uploading
    dry_run = getattr(args, 'dry_run', None)
    if dry_run:
        if dry_run == 'text':
            print(render_quiz_text(args.title, question_payloads, args.points, points_per_statement))
        else:
            import subprocess
            import tempfile
            html = render_quiz_html(args.title, question_payloads, args.points, points_per_statement)
            with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False) as f:
                f.write(html)
                html_path = f.name
            print(f"Rendered {len(question_payloads)} statements to {html_path}")
            print(f"{args.points:.1f} points total ({points_per_statement:.4f} per statement)")
            subprocess.Popen(['open', html_path])
        return 0

    # Check if quiz exists
    existing = api.find_quiz_by_title(args.title)
    if existing:
        quiz = api.update_quiz(existing["id"], quiz_data)
        api.delete_quiz_questions(quiz["id"])
        print(f"Updated quiz: {quiz['title']} (id={quiz['id']})")
    else:
        quiz = api.create_quiz(quiz_data)
        print(f"Created quiz: {quiz['title']} (id={quiz['id']})")

    # Add questions
    for qp in question_payloads:
        result = api.create_quiz_question(quiz["id"], qp)
        q_id = result.get("id", "?")
        print(f"  Added question: {qp['question_name']} (id={q_id})")

    # Summary
    print(f"\nQuiz has {len(question_payloads)} questions, {total_statements} statements, {args.points:.1f} points total ({points_per_statement:.4f} per statement)")
    if args.seed is not None:
        print(f"Random seed: {args.seed}")

    return 0


def cmd_ls_quizzes(api: CanvasAPI, args) -> int:
    """List quizzes in the course."""
    quizzes = api.list_quizzes()
    if args.json:
        print(json.dumps(quizzes, indent=2))
    else:
        for q in quizzes:
            status = "published" if q.get("published") else "draft"
            print(f"{q['id']:>8}  [{status:>9}]  {q['title']}")
    return 0


def cmd_tex(api: Optional[CanvasAPI], args) -> int:
    """Emit LaTeX source from markdown lecture material (via pandoc).

    Writes each input file's LaTeX next to it with a .tex extension unless
    ``--stdout`` is given. With ``--pdf``, also compiles with pdflatex and
    opens the resulting PDF. No Canvas credentials are required. Requires
    ``pandoc`` on PATH (and ``pdflatex`` for ``--pdf``).
    """
    import subprocess
    from canvas.md2tex import PandocNotFoundError, PdflatexNotFoundError

    if args.pdf and (args.stdout or args.body):
        print("Error: --pdf requires a standalone .tex file (not --stdout/--body)")
        return 1

    standalone = not args.body
    extra = args.pandoc_arg
    try:
        for file in args.files:
            if not file.exists():
                print(f"Error: {file} not found")
                continue
            if args.stdout:
                print(
                    convert_to_tex(
                        file,
                        standalone=standalone,
                        extra_pandoc_args=extra,
                    ),
                    end="",
                )
                continue
            output_path = args.output if args.output else file.with_suffix(".tex")
            convert_to_tex(
                file,
                output_path=output_path,
                standalone=standalone,
                extra_pandoc_args=extra,
            )
            print(f"Wrote {output_path}")

            if args.pdf:
                pdf_path = compile_tex_to_pdf(output_path)
                print(f"Compiled {pdf_path}")
                open_file_cmd(pdf_path)

            # A single -o path only applies to the first file; subsequent
            # files fall back to the per-file default.
            if args.output:
                args.output = None
    except PandocNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except PdflatexNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except subprocess.CalledProcessError as e:
        tool = "pdflatex" if e.cmd and e.cmd[0].endswith("pdflatex") else "pandoc"
        print(f"{tool} failed with exit code {e.returncode}")
        if e.output:
            print(e.output, end="")
        if e.stderr:
            print(e.stderr, end="")
        return e.returncode
    return 0


def cmd_up_syllabus(api: CanvasAPI, args) -> int:
    """Upload a markdown file as the course syllabus."""
    if not args.file.exists():
        print(f"Error: {args.file} not found")
        return 1
    result = api.upload_syllabus(args.file)
    print(f"Updated syllabus for: {result.get('name', 'N/A')}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Canvas LMS command-line interface"
    )
    parser.add_argument(
        "--config", type=Path, help=f"Config file (default: {CONFIG_FILE})"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- ls command with subcommands ---
    ls_parser = subparsers.add_parser("ls", help="List resources")
    ls_subparsers = ls_parser.add_subparsers(dest="resource", required=True)

    # ls assignments
    ls_assign = ls_subparsers.add_parser("assignments", help="List assignments")
    ls_assign.add_argument("--json", action="store_true", help="Output as JSON")
    ls_assign.set_defaults(func=cmd_ls_assignments, needs_course=True)

    # ls pages
    ls_pages = ls_subparsers.add_parser("pages", help="List pages")
    ls_pages.add_argument("--json", action="store_true", help="Output as JSON")
    ls_pages.set_defaults(func=cmd_ls_pages, needs_course=True)

    # ls courses
    ls_courses = ls_subparsers.add_parser("courses", help="List courses")
    ls_courses.add_argument("--json", action="store_true", help="Output as JSON")
    ls_courses.set_defaults(func=cmd_ls_courses, needs_course=False)

    # ls quizzes
    ls_quizzes = ls_subparsers.add_parser("quizzes", help="List quizzes")
    ls_quizzes.add_argument("--json", action="store_true", help="Output as JSON")
    ls_quizzes.set_defaults(func=cmd_ls_quizzes, needs_course=True)

    # ls syllabus
    ls_syllabus = ls_subparsers.add_parser("syllabus", help="Show syllabus info")
    ls_syllabus.add_argument("--json", action="store_true", help="Output as JSON")
    ls_syllabus.set_defaults(func=cmd_ls_syllabus, needs_course=True)

    # ls gradebook
    ls_gradebook = ls_subparsers.add_parser(
        "gradebook",
        help="Show the course gradebook as a formatted table",
    )
    ls_gradebook.add_argument(
        "--total",
        action="store_true",
        help="Show final grade as total points (earned/possible) instead of percentage",
    )
    ls_gradebook.add_argument(
        "--assignment",
        type=str,
        default=None,
        help="Comma-separated assignment names to include (default: all published)",
    )
    ls_gradebook.add_argument(
        "--json",
        action="store_true",
        help="Output raw gradebook data as JSON",
    )
    ls_gradebook.add_argument(
        "--pager",
        action="store_true",
        help="Pipe through `less -SR` for horizontal scrolling of wide tables (arrow keys to scroll, q to quit)",
    )
    ls_gradebook.add_argument(
        "--tui",
        action="store_true",
        help="Open an interactive Textual TUI with a sticky Student column (arrow keys to scroll, q to quit)",
    )
    ls_gradebook.set_defaults(func=cmd_ls_gradebook, needs_course=True)

    # --- up command with subcommands ---
    up_parser = subparsers.add_parser("up", help="Upload resources")
    up_subparsers = up_parser.add_subparsers(dest="resource", required=True)

    # Shared upload arguments
    def add_upload_args(p):
        p.add_argument("files", type=Path, nargs="+", help="Markdown file(s)")
        p.add_argument("--publish", action="store_true", help="Publish immediately")
        p.add_argument("--no-update", action="store_true", help="Create new instead of updating")

    # up assignment
    up_assign = up_subparsers.add_parser("assignment", help="Upload as assignment")
    add_upload_args(up_assign)
    up_assign.add_argument("--points", type=float, default=3.0, help="Points possible")
    up_assign.set_defaults(func=cmd_up_assignment, needs_course=True)

    # up page
    up_page = up_subparsers.add_parser("page", help="Upload as page")
    add_upload_args(up_page)
    up_page.set_defaults(func=cmd_up_page, needs_course=True)

    # up quiz
    up_quiz = up_subparsers.add_parser("quiz", help="Generate and upload quiz from question bank")
    up_quiz.add_argument("file", type=Path, help="Quiz bank markdown file")
    up_quiz.add_argument("--title", required=True, help="Quiz title")
    up_quiz.add_argument("--sample", type=int, default=5, help="Statements per question (default: 5)")
    up_quiz.add_argument("--seed", type=int, default=None, help="Random seed")
    up_quiz.add_argument("--questions", type=str, default=None, help="Comma-separated question numbers (default: all)")
    up_quiz.add_argument("--num-questions", type=int, default=None, dest="num_questions", help="Randomly select this many questions from the bank (default: all)")
    up_quiz.add_argument("--points", type=float, default=10.0, help="Total points for the quiz (default: 10.0)")
    up_quiz.add_argument("--due", type=str, default=None, help="Due date (M/D/YY)")
    up_quiz.add_argument("--attempts", type=int, default=1, help="Allowed attempts (default: 1, use -1 for unlimited)")
    up_quiz.add_argument("--publish", action="store_true", help="Publish immediately")
    up_quiz.add_argument("--dry-run", nargs='?', const='html', choices=['html', 'text'], help="Preview without uploading: 'html' (default) opens browser, 'text' prints to terminal")
    up_quiz.set_defaults(func=cmd_up_quiz, needs_course=True)

    # up syllabus
    up_syllabus = up_subparsers.add_parser("syllabus", help="Upload syllabus")
    up_syllabus.add_argument("file", type=Path, help="Markdown file")
    up_syllabus.set_defaults(func=cmd_up_syllabus, needs_course=True)

    # --- tex command: emit LaTeX source from markdown ---
    tex_parser = subparsers.add_parser(
        "tex", help="Emit LaTeX source from markdown lecture material"
    )
    tex_parser.add_argument(
        "files", type=Path, nargs="+", help="Markdown file(s)"
    )
    tex_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .tex path (single file; default: alongside input with .tex)",
    )
    tex_parser.add_argument(
        "--body",
        action="store_true",
        help="Emit body fragment only (no \\documentclass preamble)",
    )
    tex_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write LaTeX to stdout instead of files",
    )
    tex_parser.add_argument(
        "--pandoc-arg",
        action="append",
        default=None,
        help="Extra argument forwarded to pandoc (repeatable). "
             "Example: --pandoc-arg=--template=mytemplate.tex",
    )
    tex_parser.add_argument(
        "--pdf",
        action="store_true",
        help="After conversion, compile with pdflatex and open the PDF",
    )
    tex_parser.set_defaults(func=cmd_tex, needs_course=False, offline=True)

    args = parser.parse_args()

    # Dry-run mode and offline commands don't need Canvas credentials
    if getattr(args, "dry_run", None) or getattr(args, "offline", False):
        return args.func(None, args)

    # Load config
    config = get_config(args.config)

    # Check required config
    required = ["api_url", "api_token"]
    if getattr(args, "needs_course", True):
        required.append("course_id")

    missing = [k for k in required if k not in config]
    if missing:
        print(f"Error: Missing config: {', '.join(missing)}")
        print(f"Set in {CONFIG_FILE} or via environment variables:")
        print("  CANVAS_API_URL, CANVAS_API_TOKEN, CANVAS_COURSE_ID")
        return 1

    api = CanvasAPI(
        config["api_url"],
        config["api_token"],
        config.get("course_id", ""),
        theme_color=config.get("theme_color", DEFAULT_THEME_COLOR),
    )

    return args.func(api, args)


if __name__ == "__main__":
    raise SystemExit(main())
