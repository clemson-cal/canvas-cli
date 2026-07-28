#!/usr/bin/env python3
"""Convert markdown to Canvas-compatible HTML."""

import argparse
import re
from pathlib import Path
from typing import Optional

import markdown


#: Default theme color used for headings, table headers, and links when no
#: ``theme_color`` is configured. Chosen to be neutral/professional; override
#: via ``theme_color`` in ``.canvas.json`` or the ``--theme-color`` CLI flag.
DEFAULT_THEME_COLOR = "#2C3E50"


STANDALONE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: Georgia, 'Times New Roman', serif;
            max-width: 65ch;
            margin: 40px auto;
            padding: 0 20px;
            line-height: 1.6;
            color: #333;
        }}
        h1 {{
            border-bottom: 2px solid #333;
            padding-bottom: 10px;
        }}
        h2 {{
            margin-top: 30px;
            color: {theme_color};
        }}
        h3 {{
            color: #666;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px 12px;
            text-align: left;
        }}
        th {{
            background-color: {theme_color};
            color: white;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        ul {{
            margin: 10px 0;
        }}
        a {{
            color: {theme_color};
        }}
    </style>
</head>
<body>
{content}
</body>
</html>
"""


def _protect_math(md_content: str):
    """Protect all math blocks from markdown processing.

    Extracts both display ($$...$$) and inline ($...$) math, skipping
    content inside fenced code blocks and inline code spans.

    Returns (modified_markdown, math_blocks) where math_blocks is a list
    of ('display', raw_match) or ('inline', inner_content) tuples.
    """
    math_blocks = []

    # Temporarily protect code so we don't extract $ inside it
    code_blocks = []
    def protect_code(match):
        code_blocks.append(match.group(0))
        return f"\x00CODE{len(code_blocks) - 1}\x00"
    md_content = re.sub(r'```.*?```', protect_code, md_content, flags=re.DOTALL)
    md_content = re.sub(r'`[^`]+`', protect_code, md_content)

    # Extract display math first (greedy precedence over inline)
    def extract_display(match):
        math_blocks.append(('display', match.group(0)))
        return f"\x00MATH{len(math_blocks) - 1}\x00"
    md_content = re.sub(r'\$\$(.+?)\$\$', extract_display, md_content, flags=re.DOTALL)

    # Extract inline math
    def extract_inline(match):
        math_blocks.append(('inline', match.group(1)))
        return f"\x00MATH{len(math_blocks) - 1}\x00"
    md_content = re.sub(r'\$(.+?)\$', extract_inline, md_content)

    # Restore code blocks (markdown still needs to process them)
    for i, block in enumerate(code_blocks):
        md_content = md_content.replace(f"\x00CODE{i}\x00", block)

    return md_content, math_blocks


def _restore_math(html: str, math_blocks: list, canvas: bool) -> str:
    """Restore math blocks into HTML with appropriate delimiters.

    For Canvas: display math stays as $$...$$, inline becomes \\(...\\).
    For standalone: both types are restored with their original $ delimiters.
    """
    for i, (math_type, content) in enumerate(math_blocks):
        if math_type == 'display':
            replacement = content
        elif canvas:
            replacement = f'\\({content}\\)'
        else:
            replacement = f'${content}$'
        html = html.replace(f"\x00MATH{i}\x00", replacement)
    return html


def apply_inline_styles(html: str, theme_color: str = DEFAULT_THEME_COLOR) -> str:
    """Apply inline styles for Canvas compatibility.

    Args:
        html: The HTML content to style.
        theme_color: The accent color (hex) used for h2, table headers, and links.
    """
    styles = {
        "h1": "border-bottom: 2px solid #333; padding-bottom: 10px;",
        "h2": f"margin-top: 30px; color: {theme_color};",
        "h3": "color: #666;",
        "table": "border-collapse: collapse; width: 100%; margin: 20px 0;",
        "th": f"border: 1px solid #ddd; padding: 8px 12px; text-align: left; background-color: {theme_color}; color: white;",
        "td": "border: 1px solid #ddd; padding: 8px 12px; text-align: left;",
    }

    for tag, style in styles.items():
        html = re.sub(rf"<{tag}>", f'<{tag} style="{style}">', html)

    # Links need special handling (have attributes)
    html = re.sub(r"<a ", f'<a style="color: {theme_color};" ', html)

    return html


def resolve_local_files(html: str, md_dir: Path, upload_image=None, upload_file=None) -> str:
    """Resolve local file references in HTML.

    Handles two cases:
      - <img src="...">: local images are uploaded and src is replaced
      - <a href="local.pdf">: PDFs are uploaded and replaced with a Canvas iframe embed

    Args:
        html: The HTML content.
        md_dir: Directory of the source markdown file (for resolving relative paths).
        upload_image: Optional callable(Path) -> str that uploads an image and returns a URL.
        upload_file: Optional callable(Path) -> dict that uploads a file and returns the
            Canvas file record (with 'id' and 'url' keys).
    """
    def replace_img(match):
        prefix = match.group(1)
        src = match.group(2)
        if src.startswith(("http://", "https://", "//")):
            return match.group(0)
        img_path = (md_dir / src).resolve()
        if not img_path.exists():
            return match.group(0)
        if upload_image:
            url = upload_image(img_path)
            return f'<img {prefix}src="{url}"'
        return match.group(0)

    html = re.sub(r'<img ([^>]*)src="([^"]+)"', replace_img, html)

    def replace_link(match):
        full_tag = match.group(0)
        href = match.group(1)
        link_text = match.group(2)
        if href.startswith(("http://", "https://", "//")):
            return full_tag
        file_path = (md_dir / href).resolve()
        if not file_path.exists():
            return full_tag
        if upload_file and file_path.suffix.lower() == ".pdf":
            result = upload_file(file_path)
            download_url = result["url"]
            preview_url = re.sub(r"/files/(\d+)/download.*", r"/files/\1/preview", download_url)
            return (
                f'<a href="{download_url}">{link_text}</a>'
                f'\n<iframe src="{preview_url}" width="100%" height="600" '
                f'style="border: none;" allowfullscreen="true"></iframe>'
            )
        return full_tag

    html = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>([^<]+)</a>', replace_link, html)

    return html


def convert(
    md_path: Path,
    output_path: Optional[Path] = None,
    standalone: bool = False,
    upload_image=None,
    upload_file=None,
    theme_color: str = DEFAULT_THEME_COLOR,
) -> str:
    """Convert a markdown file to HTML.

    Args:
        md_path: Path to the markdown file.
        output_path: Optional path for the output HTML file.
        standalone: If True, output a full HTML page with <style> block.
        upload_image: Optional callable(Path) -> str that uploads an image
            and returns a URL. Used for Canvas integration.
        upload_file: Optional callable(Path) -> dict that uploads a file
            and returns the Canvas file record. Used for PDF embeds.
        theme_color: Hex color used for accent styling (h2, table headers,
            links). Defaults to a neutral dark blue-gray; override via
            ``.canvas.json`` (``theme_color`` key) or ``--theme-color`` on
            the CLI to match your institution's palette.

    Returns:
        The generated HTML content.
    """
    md_content = md_path.read_text(encoding="utf-8")

    # Protect all math (display and inline) from markdown processing,
    # which would escape &, eat backslashes in \\, and interpret _ as emphasis.
    md_content, math_blocks = _protect_math(md_content)

    md_converter = markdown.Markdown(extensions=["tables", "smarty", "fenced_code"])
    html_content = md_converter.convert(md_content)

    # Restore math with appropriate delimiters for the output format
    html_content = _restore_math(html_content, math_blocks, canvas=not standalone)

    # Resolve local file references (images and PDFs)
    md_dir = md_path.resolve().parent
    html_content = resolve_local_files(html_content, md_dir, upload_image, upload_file)

    if standalone:
        # Extract title from first h1
        title = md_path.stem
        for line in md_content.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break
        full_html = STANDALONE_TEMPLATE.format(
            title=title,
            content=html_content,
            theme_color=theme_color,
        )
    else:
        styled_content = apply_inline_styles(html_content, theme_color=theme_color)
        wrapper_style = "max-width: 65ch; margin: 0 auto; line-height: 1.6; color: #333;"
        full_html = f'<div style="{wrapper_style}">\n{styled_content}\n</div>'

    if output_path:
        output_path.write_text(full_html, encoding="utf-8")

    return full_html


def main():
    parser = argparse.ArgumentParser(
        description="Convert markdown to HTML (Canvas-compatible by default)"
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Input markdown file",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output HTML file (default: same name with .html extension)",
    )
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Output a full HTML page with <style> block (for browser viewing)",
    )
    parser.add_argument(
        "--theme-color",
        default=DEFAULT_THEME_COLOR,
        help=f"Accent hex color for h2/tables/links (default: {DEFAULT_THEME_COLOR})",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        return 1

    output_path = args.output or input_path.with_suffix(".html")

    convert(
        input_path,
        output_path,
        standalone=args.standalone,
        theme_color=args.theme_color,
    )
    print(f"Converted {input_path.name} -> {output_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
