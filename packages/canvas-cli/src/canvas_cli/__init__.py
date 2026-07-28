"""canvas-cli — markdown-first course authoring for Canvas LMS.

Public API (stable surface for plugin packages):
    CanvasAPI           — thin client for the Canvas REST API.
    get_config          — load ``.canvas.json`` / environment config.
    convert             — markdown → Canvas-ready HTML (from ``canvas_cli.md2html``).
    DEFAULT_THEME_COLOR — fallback accent color for rendered HTML.

CLI entry points installed by this package:
    canvas    — ``python -m canvas_cli`` equivalent (ls / up subcommands)
    md2html   — markdown → HTML standalone conversion

Plugin packages can add ``canvas`` subcommands by declaring an entry point in
the ``canvas_cli.commands`` group; see ``canvas_cli.cli.CLIContext``.
"""

__version__ = "0.3.0"

from canvas_cli.api import CanvasAPI, get_config
from canvas_cli.md2html import convert, DEFAULT_THEME_COLOR

__all__ = [
    "__version__",
    "CanvasAPI",
    "get_config",
    "convert",
    "DEFAULT_THEME_COLOR",
]
