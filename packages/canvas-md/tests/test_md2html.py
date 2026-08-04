"""Tests for the markdown → Canvas HTML converter."""

from canvas_md.md2html import convert, apply_inline_styles


def write_md(tmp_path, content):
    md = tmp_path / "doc.md"
    md.write_text(content)
    return md


def test_inline_math_converted_for_canvas(tmp_path):
    md = write_md(tmp_path, "The map $f_1(x) = \\mathbf{x}_2$ is linear.\n")
    html = convert(md)
    assert "\\(f_1(x) = \\mathbf{x}_2\\)" in html
    # Underscores inside math must not become <em> tags
    assert "<em>" not in html


def test_display_math_preserved_for_canvas(tmp_path):
    md = write_md(tmp_path, "$$\\nabla \\cdot \\mathbf{E} = 4\\pi \\rho$$\n")
    html = convert(md)
    assert "$$\\nabla \\cdot \\mathbf{E} = 4\\pi \\rho$$" in html


def test_dollar_in_code_not_treated_as_math(tmp_path):
    md = write_md(tmp_path, "Run `echo $HOME` and `ls $PWD` to see.\n")
    html = convert(md)
    assert "$HOME" in html
    assert "\\(" not in html


def test_standalone_page_has_title_and_dollar_math(tmp_path):
    md = write_md(tmp_path, "# Lecture 5\n\nInline $x^2$ math.\n")
    html = convert(md, standalone=True)
    assert "<title>Lecture 5</title>" in html
    assert "$x^2$" in html


def test_theme_color_applied_inline(tmp_path):
    styled = apply_inline_styles("<h2>Section</h2>", theme_color="#522d80")
    assert 'color: #522d80' in styled
