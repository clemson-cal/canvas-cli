"""canvas-md — markdown-first course authoring for Canvas LMS.

Public API (stable surface for plugin packages):
    CanvasAPI           — thin client for the Canvas REST API.
    get_config          — load ``.canvas.json`` / environment config.
    convert             — markdown → Canvas-ready HTML (from ``canvas_md.md2html``).
    parse_datetime      — course-author date string → Canvas ISO8601.
    DEFAULT_THEME_COLOR — fallback accent color for rendered HTML.

CLI entry points installed by this package:
    canvas    — ``python -m canvas_md`` equivalent (ls / up subcommands)
    md2html   — markdown → HTML standalone conversion

Plugin packages can add ``canvas`` subcommands by declaring an entry point in
the ``canvas_md.commands`` group; see ``canvas_md.cli.CLIContext``.
"""

__version__ = "0.3.0"

from canvas_md.api import CanvasAPI, get_config
from canvas_md.dates import parse_datetime, SYNTAX_HELP as DATE_SYNTAX_HELP
from canvas_md.md2html import convert, DEFAULT_THEME_COLOR

__all__ = [
    "__version__",
    "CanvasAPI",
    "get_config",
    "convert",
    "parse_datetime",
    "DATE_SYNTAX_HELP",
    "DEFAULT_THEME_COLOR",
]
