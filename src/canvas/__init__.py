"""canvas-cli — markdown-first course authoring for Canvas LMS.

Public API:
    CanvasAPI         — thin client for the Canvas REST API.
    get_config        — load ``.canvas.json`` / environment config.
    convert           — markdown → Canvas-ready HTML (from ``canvas.md2html``).
    convert_to_tex    — markdown → LaTeX via pandoc (from ``canvas.md2tex``).
    parse_quiz_bank   — parse ``quiz-bank.md`` format into Question objects.

CLI entry points installed by this package:
    canvas    — ``python -m canvas`` equivalent (ls / up / tex subcommands)
    md2html   — markdown → HTML standalone conversion
    md2tex    — markdown → LaTeX via pandoc
"""

__version__ = "0.2.0"

from canvas.canvas import CanvasAPI, get_config
from canvas.md2html import convert, DEFAULT_THEME_COLOR
from canvas.md2tex import convert as convert_to_tex
from canvas.quiz import (
    Question,
    Statement,
    parse_quiz_bank,
    sample_quiz,
    build_canvas_quiz_data,
)

__all__ = [
    "__version__",
    "CanvasAPI",
    "get_config",
    "convert",
    "DEFAULT_THEME_COLOR",
    "convert_to_tex",
    "Question",
    "Statement",
    "parse_quiz_bank",
    "sample_quiz",
    "build_canvas_quiz_data",
]
