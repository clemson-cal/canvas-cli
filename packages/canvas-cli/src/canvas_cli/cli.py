#!/usr/bin/env python3
"""canvas command-line interface: subcommands, gradebook rendering, plugins."""

import argparse
import json
import sys
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import Optional

from canvas_cli.api import CONFIG_FILE, CanvasAPI, get_config
from canvas_cli.md2html import DEFAULT_THEME_COLOR


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


def cmd_up_syllabus(api: CanvasAPI, args) -> int:
    """Upload a markdown file as the course syllabus."""
    if not args.file.exists():
        print(f"Error: {args.file} not found")
        return 1
    result = api.upload_syllabus(args.file)
    print(f"Updated syllabus for: {result.get('name', 'N/A')}")
    return 0


#: Entry-point group scanned for plugin subcommands. A plugin package declares
#:
#:     [project.entry-points."canvas_cli.commands"]
#:     quiz = "canvas_auto_quiz.cli:register"
#:
#: in its pyproject.toml, and its ``register(ctx)`` function is called with a
#: :class:`CLIContext` when the ``canvas`` command starts up.
PLUGIN_GROUP = "canvas_cli.commands"


@dataclass
class CLIContext:
    """Argument-parser hooks handed to each plugin's ``register(ctx)``.

    A plugin attaches its subcommands with ``ctx.up_subparsers.add_parser(...)``
    (or ``ls_subparsers``, or top-level ``subparsers``) and must call
    ``set_defaults(func=<handler>, needs_course=<bool>)`` on every parser it
    creates. The handler is invoked as ``func(api, args) -> int`` with a
    configured :class:`CanvasAPI` — or ``api=None`` when ``args.dry_run`` is
    truthy, in which case no Canvas credentials are required or loaded.
    """
    parser: argparse.ArgumentParser
    subparsers: argparse._SubParsersAction
    ls_subparsers: argparse._SubParsersAction
    up_subparsers: argparse._SubParsersAction


def _load_plugins(ctx: CLIContext) -> None:
    """Discover and register plugin subcommands via package entry points."""
    for ep in entry_points(group=PLUGIN_GROUP):
        try:
            register = ep.load()
            register(ctx)
        except Exception as e:  # a broken plugin must not take down the CLI
            print(f"warning: failed to load plugin '{ep.name}': {e}", file=sys.stderr)


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

    # up syllabus
    up_syllabus = up_subparsers.add_parser("syllabus", help="Upload syllabus")
    up_syllabus.add_argument("file", type=Path, help="Markdown file")
    up_syllabus.set_defaults(func=cmd_up_syllabus, needs_course=True)

    # --- plugin subcommands (canvas-auto-quiz, etc.) ---
    _load_plugins(CLIContext(
        parser=parser,
        subparsers=subparsers,
        ls_subparsers=ls_subparsers,
        up_subparsers=up_subparsers,
    ))

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
