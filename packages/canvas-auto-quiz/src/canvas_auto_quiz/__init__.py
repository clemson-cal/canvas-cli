"""canvas-auto-quiz — quiz-bank plugin for canvas-cli.

Write pools of true/false statements in markdown, then sample balanced random
subsets into a Canvas quiz with per-answer explanation comments.

Installing this package adds the ``canvas up quiz`` subcommand to canvas-cli
(via the ``canvas_cli.commands`` entry-point group).

Public API:
    Question, Statement    — parsed quiz-bank dataclasses.
    parse_quiz_bank        — parse the quiz-bank markdown format.
    sample_quiz            — sample balanced T/F subsets from each question.
    build_canvas_quiz_data — build Canvas API payloads from sampled items.
"""

__version__ = "0.1.0"

from canvas_auto_quiz.quiz import (
    Question,
    Statement,
    parse_quiz_bank,
    sample_quiz,
    build_canvas_quiz_data,
)

__all__ = [
    "__version__",
    "Question",
    "Statement",
    "parse_quiz_bank",
    "sample_quiz",
    "build_canvas_quiz_data",
]
