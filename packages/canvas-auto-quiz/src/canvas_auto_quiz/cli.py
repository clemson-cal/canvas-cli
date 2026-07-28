#!/usr/bin/env python3
"""The ``canvas up quiz`` subcommand, registered into canvas-cli as a plugin."""

import re
from pathlib import Path

from canvas_auto_quiz.quiz import parse_quiz_bank, sample_quiz, build_canvas_quiz_data


def render_quiz_text(title: str, question_payloads: list[dict], total_points: float, points_per_statement: float) -> str:
    """Render quiz as plain text for terminal output."""
    def strip_latex(s):
        # \(...\) -> just the math, \[...\] -> just the math
        s = re.sub(r'\\\((.+?)\\\)', r'$\1$', s)
        s = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', s)
        # Strip HTML tags
        s = re.sub(r'<[^>]+>', '', s)
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


def cmd_up_quiz(api, args) -> int:
    """Generate and upload a quiz from the question bank."""
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
            import tempfile
            import webbrowser
            html = render_quiz_html(args.title, question_payloads, args.points, points_per_statement)
            with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False) as f:
                f.write(html)
                html_path = f.name
            print(f"Rendered {len(question_payloads)} statements to {html_path}")
            print(f"{args.points:.1f} points total ({points_per_statement:.4f} per statement)")
            webbrowser.open(f"file://{html_path}")
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


def register(ctx) -> None:
    """canvas-cli plugin hook: add the ``canvas up quiz`` subcommand.

    ``ctx`` is a ``canvas_cli.cli.CLIContext``.
    """
    up_quiz = ctx.up_subparsers.add_parser("quiz", help="Generate and upload quiz from question bank")
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
