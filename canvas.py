import json
import os
import enum
import re
import datetime
from canvasapi import Canvas
from typer import Typer
from rich import print


CONFIG_FILE = ".canvas"
app = Typer()


#
# Enum Classes
#
class ListItem(enum.Enum):
    """Enumeration of items that can be listed from Canvas."""
    COURSES = "courses"
    ASSIGNMENTS = "assignments"
    QUIZZES = "quizzes"
    FILES = "files"
    STUDENTS = "students"
    ASSIGNMENT_GROUPS = "assignment_groups"


class DescribeItem(enum.Enum):
    QUIZ = "quiz"


class ConfigItem(enum.Enum):
    """Enumeration of configuration items that can be set or displayed."""
    COURSE = "course"
    API_URL = "api_url"
    API_KEY = "api_key"


class CreateItem(enum.Enum):
    """Enumeration of items that can be created in Canvas."""
    ASSIGNMENT = "assignment"
    ASSIGNMENT_GROUP = "assignment_group"
    FILE = "file"
    QUIZ = "quiz"


#
# Configuration Functions
#
def load_config():
    """
    Load configuration from .canvas file.

    Returns:
        dict: Configuration dictionary with API URL, key, and current course ID.

    Creates a default configuration file if none exists.
    """
    default_config = {
        "api_url": "https://your-institution.instructure.com",
        "api_key": "your-token",
        "current_course_id": None
    }
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Create default config file if it doesn't exist
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f, indent=4)
        return default_config


def save_config(config):
    """
    Save configuration to .canvas file.

    Args:
        config (dict): Configuration dictionary to save.
    """
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


def get_canvas():
    """
    Get Canvas API instance with current configuration.

    Returns:
        Canvas: Canvas API instance initialized with current API URL and key.
    """
    config = load_config()
    return Canvas(config["api_url"], config["api_key"])


def get_course():
    """
    Get the current course object from Canvas.

    Returns:
        Course: Canvas course object for the current course ID.

    Raises:
        RuntimeError: If no course is currently set in the configuration.
    """
    config = load_config()
    if config["current_course_id"] is None:
        raise RuntimeError("No course is currently set")

    canvas = get_canvas()
    return canvas.get_course(config["current_course_id"])


#
# Utility Functions
#
def parse_date(date_str):
    """
    Parse a date string in a specific format.

    Args:
        date_str (str): Date string in format "Month DD, YYYY HH:MM"

    Returns:
        datetime: Parsed datetime object
    """
    return datetime.datetime.strptime(date_str, "%B %d, %Y %H:%M")


def render_markdown(content: str):
    """
    Convert Markdown content to HTML while preserving math expressions.

    This function converts Markdown content to HTML using the Python markdown
    library. It preserves math expressions delimited by \( and \) by temporarily
    replacing them with placeholders during the conversion, then restoring them
    in the final HTML. This ensures that LaTeX math expressions aren't altered
    by the Markdown processor.

    Args:
        content (str): String containing Markdown content with possible math expressions
                 enclosed in \( and \)

    Returns:
        str: HTML conversion of the Markdown with math expressions preserved
    """
    import markdown

    # Temporarily replace math sequences to protect them
    math_expressions = []
    def save_math(match):
        math_expressions.append(match.group(0))
        return f"MATH_PLACEHOLDER_{len(math_expressions)-1}_"

    # Save math expressions
    protected_md = re.sub(r'\\\(.*?\\\)', save_math, content)

    # Convert to HTML
    html = markdown.markdown(protected_md)

    # Restore math expressions
    def restore_math(match):
        index = int(match.group(1))
        return math_expressions[index]

    return re.sub(r'MATH_PLACEHOLDER_(\d+)_', restore_math, html)


def parse_assignment_file(file_path: str):
    """
    Parse a Markdown file with YAML header into header dictionary and markdown body.

    Args:
        file_path (str): Path to the Markdown file containing the assignment details

    Returns:
        tuple: (header_dict, markdown_body) where header_dict is a dictionary of the YAML header
               and markdown_body is the Markdown content

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file doesn't have a valid YAML header
        yaml.YAMLError: If there's an error parsing the YAML
    """
    import yaml
    import re

    with open(file_path, 'r') as f:
        content = f.read()

    # Check if file has valid YAML frontmatter format (between two '---' delimiters)
    match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if not match:
        raise ValueError("Markdown file must have valid frontmatter between '---' delimiters")

    # Extract YAML header and markdown body
    header_text, markdown_body = match.groups()

    # Parse YAML header
    header = yaml.safe_load(header_text)

    # Validate required fields
    required_fields = ['name', 'points_possible']
    missing_fields = [field for field in required_fields if field not in header]
    if missing_fields:
        raise ValueError(f"Missing required fields in YAML header: {', '.join(missing_fields)}")

    return (header, markdown_body)


#
# Canvas Content Functions
#
def list_files():
    """
    List all files in the current course, showing the complete directory tree with IDs.

    Recursively traverses all folders and displays files with their IDs and sizes.
    """
    course = get_course()

    def print_folder_contents(folder, indent=""):
        """Recursively print folder contents with proper indentation."""
        # Print folder information
        print(f"{indent}📁 [bold]{folder.name}[/bold] (ID: {folder.id})")

        # Get and print subfolders recursively
        try:
            subfolders = folder.get_folders()
            for subfolder in subfolders:
                print_folder_contents(subfolder, indent + "  ")
        except Exception as e:
            print(f"{indent}  [red]Error listing subfolders:[/red] {str(e)}")

        # Get and print files in this folder
        try:
            files = folder.get_files()
            for file in files:
                size_str = f"{file.size} bytes" if hasattr(file, 'size') else "N/A"
                print(f"{indent}  📄 {file.display_name} (ID: {file.id}, Size: {size_str})")
        except Exception as e:
            print(f"{indent}  [red]Error listing files:[/red] {str(e)}")

    try:
        # Start from course root folders
        print(f"[bold]Complete directory tree for course:[/bold]")
        root_folders = course.get_folders()
        for folder in root_folders:
            print_folder_contents(folder)
    except Exception as e:
        print(f"[red]Error accessing folders:[/red] {str(e)}")


def create_assignment_group(name: str, weight: float = None, position: int = None):
    """
    Create an assignment group in the current course.

    Args:
        name (str): Name of the assignment group
        weight (float, optional): Weight of the assignment group (percentage)
        position (int, optional): Position of the assignment group in the list
    """
    course = get_course()

    # Prepare assignment group parameters
    group_params = {
        'name': name
    }

    # Add optional parameters if provided
    if weight is not None:
        group_params['group_weight'] = weight

    if position is not None:
        group_params['position'] = position

    # Create the assignment group
    try:
        group = course.create_assignment_group(**group_params)
        print(f"[green]Assignment group created successfully:[/green] {group.name} (ID: {group.id})")
        if weight is not None:
            print(f"Weight: {weight}%")
    except Exception as e:
        print(f"[red]Error creating assignment group:[/red] {str(e)}")


def submit_assignment(
    header: dict,
    markdown_body: str,
    publish: bool = False,
    edit: bool = False,
    dry_run: bool = False
):
    """
    Render markdown and submit assignment to Canvas.

    Args:
        header (dict): Dictionary containing assignment configuration
        markdown_body (str): Markdown content for the assignment description
        publish (bool, optional): Whether to publish the assignment. Defaults to False.
        edit (bool, optional): Whether this is updating an existing assignment. Defaults to False.
        dry_run (bool, optional): Whether to perform a dry run without making changes. Defaults to False.

    Returns:
        None: Prints success or error messages to the console
    """
    body_html = render_markdown(markdown_body)

    for date_keys in ['due_at', 'unlock_at', 'lock_at']:
        if date_keys in header:
            header[date_keys] = parse_date(header[date_keys])

    assignment_params = dict(description=body_html, published=publish, **header)

    if dry_run:
        print(f"[yellow]Dry run - would create assignment:[/yellow]")
        print(f"Name: {assignment_params.get('name', None)}")
        print(f"Points: {assignment_params.get('points_possible', None)}")
        print(f"Due: {assignment_params.get('due_at', None)}")
        print(f"Group: {assignment_params.get('assignment_group_id', None)}")
        print("\nHTML Content:")
        print(body_html)
        return

    course = get_course()
    existing_assignment = None

    for assignment in course.get_assignments():
        if assignment.name == header['name']:
            existing_assignment = assignment
            if not edit:
                print("[yellow]Assignment exists; use --edit to modify it[/yellow]")
                return
            else:
                break

    if existing_assignment:
        assignment = existing_assignment.edit(assignment=assignment_params)
        status = "published" if publish else "unpublished"
        print(f"[green]Assignment updated successfully:[/green] {assignment.name} (ID: {assignment.id}) - {status}")
    else:
        assignment = course.create_assignment(assignment_params)
        status = "published" if publish else "unpublished"
        print(f"[green]Assignment created successfully:[/green] {assignment.name} (ID: {assignment.id}) - {status}")


def submit_quiz(
    filename: str,
    publish: bool = False,
    edit: bool = False,
    dry_run: bool = False
):
    """
    Create or update a sample quiz in Canvas from a YAML file
    """
    import yaml

    # Parse placement exam configuration
    with open(filename, "r") as f:
        quiz = yaml.safe_load(f)

    header = {**quiz, "published": publish}
    header.pop("questions", None)
    questions = quiz["questions"]

    if dry_run:
        print(header)
        for question in questions:
            print(question)
        return

    course = get_course()
    existing_quiz = None

    for quiz in course.get_quizzes():
        if quiz.title == header['title']:
            existing_quiz = quiz
            if not edit:
                print("[yellow]Quiz exists; use --edit to modify it[/yellow]")
                return
            else:
                break

    if existing_quiz:
        quiz = existing_quiz.edit(quiz=header)
        status = "published" if publish else "unpublished"
        print(f"[green]Quiz updated successfully:[/green] {quiz.title} (ID: {quiz.id}) - {status}")
    else:
        quiz = course.create_quiz(header)
        print(f"[green]Creating new quiz[/green] {quiz.title} (ID: {quiz.id})")

    # Delete all existing questions
    for question in quiz.get_questions():
        question.delete()

    def to_canvas_api(question: dict):
        answers = question['answers']
        return {
            'question_name': question['question_name'],
            'question_text': question['question_text'],
            'question_type': 'multiple_choice_question',
            'points_possible': 1,
            'answers': [dict(text=text, weight=100 if question["correct"] == choice else 0) for choice, text in answers.items()]
        }

    for question in questions:
        quiz.create_question(question=to_canvas_api(question))

    print(f"[green]Quiz operation completed successfully with ID: {quiz.id}[/green]")


def upload_file(file_path: str, hidden: bool = True, parent_folder_id: int = None):
    """
    Upload a file to the current Canvas course.

    Args:
        file_path (str): Path to the file to upload
        hidden (bool, optional): Whether the file should be hidden from students. Defaults to True.
        parent_folder_id (int, optional): ID of parent folder to upload into. Defaults to None.
    """
    course = get_course()

    # If no parent folder specified, use course root folder
    if parent_folder_id is None:
        for folder in course.get_folders():
            if folder.name == "course files" and folder.parent_folder_id is None:
                parent_folder_id = folder.id
                print(f"Using course root folder (ID: {parent_folder_id})")
                break

    if not os.path.exists(file_path):
        print(f"[red]Error:[/red] File '{file_path}' does not exist")
        return

    # Get file size and name
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    # Prepare upload parameters
    params = {
        'name': file_name,
        'size': file_size,
    }

    # Add parent folder if specified
    if parent_folder_id:
        params['parent_folder_id'] = parent_folder_id

    # Initialize the upload
    print(f"Uploading {file_name} ({file_size} bytes)...")

    success, info = course.upload(file_path, **params)
    uploaded_file = course.get_file(info["id"])
    uploaded_file.update(hidden=hidden)

    print(f"[green]File uploaded successfully[/green]")


#
# CLI Commands
#
@app.command()
def list(what: ListItem, detail: bool = False):
    """
    Fetch and list items from Canvas.

    Args:
        what (ListItem): Type of items to list (courses, assignments, files, students, assignment_groups)
        detail (bool): Whether to display detailed information about each item
    """
    canvas = get_canvas()
    course = get_course()

    match what:
        case ListItem.COURSES:
            courses = canvas.get_courses()
            for course in courses:
                print(f"Course ID: {course.id}, Name: {course.name}")
        case ListItem.ASSIGNMENTS:
            assignments = course.get_assignments()
            for assignment in assignments:
                print(f"Assignment ID: {assignment.id}, Name: {assignment.name}, Submission Types: {assignment.submission_types}")
                if detail:
                    print(assignment.description)
        case ListItem.FILES:
            list_files()
        case ListItem.STUDENTS:
            students = course.get_users(enrollment_type='student')
            for student in students:
                print(f"Student ID: {student.id}, Name: {student.name}, Email: {getattr(student, 'email', 'N/A')}")
        case ListItem.ASSIGNMENT_GROUPS:
            groups = course.get_assignment_groups()
            for group in groups:
                weight = getattr(group, 'group_weight', 'N/A')
                print(f"Group ID: {group.id}, Name: {group.name}, Weight: {weight}")
        case ListItem.QUIZZES:
            quizzes = course.get_quizzes()
            for quiz in quizzes:
                print(f"Quiz ID: {quiz.id}, Title: {quiz.title}")
                print(f"  Points: {quiz.points_possible}")
                print(f"  Due: {quiz.due_at}")
                print(f"  Published: {quiz.published}")


@app.command()
def set(what: ConfigItem, value: str):
    """
    Set configuration values for Canvas integration.

    Args:
        what (ConfigItem): Type of configuration to set (course, api_url, api_key)
        value (str): The value to set
    """
    config = load_config()

    match what:
        case ConfigItem.COURSE:
            course_id = int(value)
            canvas = get_canvas()
            course = canvas.get_course(course_id)
            config["current_course_id"] = course_id
            save_config(config)
            print(f"Current Course ID: {course.id}, Name: {course.name}")

        case ConfigItem.API_URL:
            config["api_url"] = value
            save_config(config)
            print(f"Canvas API URL set to: {value}")

        case ConfigItem.API_KEY:
            config["api_key"] = value
            save_config(config)
            print(f"Canvas API key set successfully")


@app.command()
def show(what: ConfigItem):
    """
    Show current configuration values for Canvas integration.

    Args:
        what (ConfigItem): Type of configuration to show (course, api_url, api_key)
    """
    config = load_config()

    match what:
        case ConfigItem.COURSE:
            if config["current_course_id"] is not None:
                canvas = get_canvas()
                course = canvas.get_course(config["current_course_id"])
                print(f"Current Course ID: {course.id}, Name: {course.name}")
            else:
                print("No course is currently set")

        case ConfigItem.API_URL:
            print(f"Canvas API URL: {config['api_url']}")

        case ConfigItem.API_KEY:
            # Only show a masked version of the API key for security
            api_key = config["api_key"]
            masked_key = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:] if len(api_key) > 8 else "****"
            print(f"Canvas API key: {masked_key}")


@app.command()
def create(
    what: CreateItem,
    arg: str,
    publish: bool = False,
    edit: bool = False,
    dry_run: bool = False
):
    """
    Create a new item in Canvas based on the specified type and arguments.

    Args:
        what (CreateItem): Type of item to create (assignment, assignment_group, file)
        arg (str): For assignments: path to Markdown file; for assignment_groups: name of group; for files: path to file
        publish (bool, optional): Whether to publish the assignment immediately (assignments only). Defaults to False.
        edit (bool, optional): Whether to edit an existing assignment (assignments only). Defaults to False.
        dry_run (bool, optional): Whether to perform a dry run without making changes (assignments only). Defaults to False.
    """
    match what:
        case CreateItem.ASSIGNMENT:
            header, markdown_body = parse_assignment_file(arg)
            submit_assignment(header, markdown_body, publish, edit, dry_run)
        case CreateItem.ASSIGNMENT_GROUP:
            create_assignment_group(arg)
        case CreateItem.FILE:
            upload_file(arg, hidden=not publish)
        case CreateItem.QUIZ:
            submit_quiz(filename=arg, publish=publish, edit=edit, dry_run=dry_run)


@app.command()
def gradebook():
    """
    Download and display the course gradebook.

    Retrieves all students and their grades for all assignments in the current course.
    """
    course = get_course()
    students = course.get_users(enrollment_type=['student'])
    user_map = {student.id: student.sortable_name for student in students}

    # Get all assignments
    assignments = course.get_assignments()

    # Create an empty gradebook dictionary
    gradebook = {uid: {} for uid in user_map}

    # Collect grades for each assignment
    for assignment in assignments:
        print(assignment)
        submissions = assignment.get_submissions()
        for sub in submissions:
            uid = sub.user_id
            if uid in gradebook:
                gradebook[uid][assignment.name] = sub.score

    for uid in gradebook:
        print(user_map[uid], gradebook[uid])


@app.command()
def describe(what: DescribeItem, canvas_id: int):
    """
    Give a description of a particular Canvas item by id number

    Note: presently this function only describes quizzes, but should be
    expanded to also describe assignments, students, files, etc.
    """
    course = get_course()

    match what:
        case DescribeItem.QUIZ:
            quiz = course.get_quiz(canvas_id)

            print(f"\nQuiz: {quiz.title}")
            print(f"Points possible: {quiz.points_possible}")
            print(f"Description: {quiz.description}")
            print("\nQuestions:")

            questions = quiz.get_questions()
            for question in questions:
                print(f"\nQuestion {question.position}:")
                print(f"Type: {question.question_type}")
                print(f"Name: {question.question_name}")
                print(f"Text: {question.question_text}")
                print(f"Points: {question.points_possible}")

                if hasattr(question, 'answers') and question.answers:
                    print("Answers:")
                    for answer in question.answers:
                        correct = "✓" if answer.get('weight', 0) > 0 else " "
                        print(f"  [{correct}] {answer.get('text', 'N/A')}")


if __name__ == "__main__":
    app()
