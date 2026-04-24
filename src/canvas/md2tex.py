#!/usr/bin/env python3
"""Convert markdown lecture material to LaTeX source via pandoc.

This module is a thin wrapper around ``pandoc`` rather than a hand-rolled
converter: pandoc already handles the tricky bits of markdown to LaTeX
(tables, smart quotes, raw inline LaTeX, nested lists, footnotes, etc.) far
better than we ever would, and math inside ``$...$`` / ``$$...$$`` passes
through unchanged via the ``tex_math_dollars`` extension.

Pandoc is invoked as a subprocess. We extract the first ``# Title`` line and
any ``**Date**: ...`` line from the source and pass them to pandoc as
``--metadata`` so the standalone document gets ``\\title{}`` / ``\\date{}``
without duplicating them in the body. Remaining headings are shifted down
one level (``##`` -> ``\\section``) so the document structure lines up with
what the lectures expect.

Install pandoc:
    macOS:   brew install pandoc
    Ubuntu:  apt install pandoc
"""

import argparse
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


# Pandoc input/output flavours. Single-backslash lets authors write
# \( \) style math in the markdown if they prefer; dollars gives them
# $...$ and $$...$$.
_FROM_FORMAT = "markdown+tex_math_dollars+tex_math_single_backslash"
_TO_FORMAT = "latex"


class PandocNotFoundError(RuntimeError):
    """Raised when pandoc is not installed on the system."""


class PdflatexNotFoundError(RuntimeError):
    """Raised when pdflatex is not installed on the system."""


def _require_pandoc() -> str:
    path = shutil.which("pandoc")
    if path is None:
        raise PandocNotFoundError(
            "pandoc executable not found on PATH.\n"
            "Install it with:\n"
            "  macOS:   brew install pandoc\n"
            "  Ubuntu:  apt install pandoc\n"
            "  Windows: choco install pandoc"
        )
    return path


def _normalize_inline_math(md: str) -> str:
    """Strip stray whitespace just inside inline ``$...$`` math.

    Pandoc's ``tex_math_dollars`` extension (correctly) requires that the
    opening ``$`` not be followed by whitespace, and the closing ``$`` not be
    preceded by whitespace — that's how it avoids treating "$5 each" as math.
    Authors occasionally slip a space in anyway (e.g. ``($ x = 0$)``), which
    causes pandoc to render the span as literal dollars and leave commands
    like ``\\mathbf`` stranded in text mode. Since these are physics lectures
    where stray ``$`` is vanishingly unlikely, it's safe to collapse the
    interior whitespace so pandoc treats the span as math.

    Display math ``$$...$$`` is left alone.
    """
    def repl(m: "re.Match[str]") -> str:
        return "$" + m.group(1).strip() + "$"

    # (?<!\$)  — don't match inside display math
    # \$(?!\$) — single opening $
    # ([^$\n]+?) — content (no unescaped $, no newline)
    # \$(?!\$) — single closing $
    return re.sub(r"(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)", repl, md)


def _extract_metadata(md: str):
    """Pull the first ``# Title`` and any ``**Date**: ...`` line out of the
    markdown so we can feed them to pandoc as metadata. Returns ``(title,
    date, stripped_md)``. Lines consumed for metadata are removed from the
    body so they don't render twice.
    """
    title: Optional[str] = None
    date = ""
    kept: list[str] = []
    for line in md.split("\n"):
        if title is None:
            m = re.match(r"^#\s+(.*)$", line)
            if m:
                title = m.group(1).strip()
                continue
        m = re.match(r"^\s*\*\*Date\*\*:\s*(.+?)\s*$", line)
        if m:
            date = m.group(1).strip()
            continue
        kept.append(line)
    return title, date, "\n".join(kept)


def convert(
    md_path: Path,
    output_path: Optional[Path] = None,
    standalone: bool = True,
    extra_pandoc_args: Optional[list[str]] = None,
) -> str:
    """Convert a markdown file to LaTeX via pandoc.

    Args:
        md_path: Path to the markdown file.
        output_path: If provided, the generated LaTeX is written here.
        standalone: If True (default), emit a full ``\\documentclass{article}``
            document that pdflatex can compile directly. If False, emit the
            body fragment only (suitable for ``\\input{}``).
        extra_pandoc_args: Additional CLI flags forwarded to pandoc — e.g.
            ``["--template", "my-template.tex"]`` to use a custom preamble.

    Returns:
        The LaTeX source as a string.

    Raises:
        PandocNotFoundError: if the ``pandoc`` binary is not on PATH.
        subprocess.CalledProcessError: if pandoc exits non-zero (its stderr
            is surfaced unchanged).
    """
    pandoc = _require_pandoc()

    md = md_path.read_text(encoding="utf-8")
    md = _normalize_inline_math(md)
    title, date, body_md = _extract_metadata(md)
    if title is None:
        title = md_path.stem

    cmd: list[str] = [
        pandoc,
        f"--from={_FROM_FORMAT}",
        f"--to={_TO_FORMAT}",
        # Shift '##' down to \section so the document structure mirrors what
        # we emitted before (the first '# Title' is consumed as metadata).
        "--shift-heading-level-by=-1",
        # Resolve relative images/links as if pandoc were run from the
        # source markdown's directory.
        f"--resource-path={md_path.resolve().parent}",
    ]
    if standalone:
        cmd.append("--standalone")
        cmd.extend(["--metadata", f"title={title}"])
        if date:
            cmd.extend(["--metadata", f"date={date}"])
    if extra_pandoc_args:
        cmd.extend(extra_pandoc_args)

    result = subprocess.run(
        cmd,
        input=body_md,
        capture_output=True,
        text=True,
        check=True,
    )
    tex = result.stdout

    if output_path is not None:
        output_path.write_text(tex, encoding="utf-8")

    return tex


def compile_to_pdf(tex_path: Path) -> Path:
    """Run pdflatex on a ``.tex`` file and return the produced ``.pdf`` path.

    Uses ``-interaction=nonstopmode`` so the run completes even on minor
    issues. Raises :class:`subprocess.CalledProcessError` with a trimmed
    transcript on hard failure, or :class:`PdflatexNotFoundError` if pdflatex
    isn't on PATH.
    """
    if shutil.which("pdflatex") is None:
        raise PdflatexNotFoundError(
            "pdflatex executable not found on PATH.\n"
            "Install a TeX distribution (e.g. MacTeX, TeX Live, MiKTeX) "
            "and ensure pdflatex is on PATH."
        )
    tex_path = tex_path.resolve()
    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", tex_path.name],
        cwd=tex_path.parent,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Surface the last chunk of pdflatex output (where errors land).
        tail = "\n".join(result.stdout.splitlines()[-40:])
        raise subprocess.CalledProcessError(
            result.returncode,
            ["pdflatex", tex_path.name],
            output=tail,
            stderr=result.stderr,
        )
    return tex_path.with_suffix(".pdf")


def open_file(path: Path) -> None:
    """Open a file with the system default application.

    Uses ``open`` on macOS, ``xdg-open`` on Linux, ``start`` on Windows.
    Silently does nothing if no opener is available — the caller is expected
    to handle that case via the returned ``None`` contract if needed.
    """
    import sys

    if sys.platform == "darwin":
        opener = ["open", str(path)]
    elif sys.platform.startswith("win"):
        opener = ["cmd", "/c", "start", "", str(path)]
    else:
        if shutil.which("xdg-open") is None:
            return
        opener = ["xdg-open", str(path)]
    subprocess.Popen(opener, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(
        description="Convert markdown lecture material to LaTeX source (via pandoc)."
    )
    parser.add_argument("input", type=Path, help="Input markdown file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .tex file (default: same name with .tex extension)",
    )
    parser.add_argument(
        "--body",
        action="store_true",
        help="Emit body fragment only (no \\documentclass preamble)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write LaTeX to stdout instead of a file",
    )
    parser.add_argument(
        "--pandoc-arg",
        action="append",
        default=None,
        help="Extra argument forwarded to pandoc (repeatable). "
             "Example: --pandoc-arg=--template=mytemplate.tex",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="After conversion, compile with pdflatex and open the PDF",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        return 1

    if args.pdf and (args.stdout or args.body):
        print("Error: --pdf requires a standalone .tex file (not --stdout/--body)")
        return 1

    standalone = not args.body

    try:
        if args.stdout:
            print(
                convert(
                    input_path,
                    standalone=standalone,
                    extra_pandoc_args=args.pandoc_arg,
                ),
                end="",
            )
            return 0

        output_path = args.output or input_path.with_suffix(".tex")
        convert(
            input_path,
            output_path=output_path,
            standalone=standalone,
            extra_pandoc_args=args.pandoc_arg,
        )
        print(f"Converted {input_path.name} -> {output_path.name}")

        if args.pdf:
            pdf_path = compile_to_pdf(output_path)
            print(f"Compiled {pdf_path.name}")
            open_file(pdf_path)
        return 0
    except PandocNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except PdflatexNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except subprocess.CalledProcessError as e:
        # Distinguish pandoc vs. pdflatex failure by looking at the command.
        tool = "pdflatex" if e.cmd and e.cmd[0].endswith("pdflatex") else "pandoc"
        print(f"{tool} failed with exit code {e.returncode}")
        if e.output:
            print(e.output, end="")
        if e.stderr:
            print(e.stderr, end="")
        return e.returncode


if __name__ == "__main__":
    raise SystemExit(main())
