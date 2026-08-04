# canvas-md

A markdown-first course-authoring CLI for [Canvas LMS](https://www.instructure.com/canvas). Write your lectures, homework, and syllabus in plain markdown and push them to Canvas with a single command. LaTeX math, embedded images, and PDF handouts are handled for you.

Built for instructors who prefer version-controlled markdown over Canvas's rich-text editor.

## Features

- **Markdown → Canvas HTML** with full LaTeX math support (inline `$...$` and display `$$...$$`), auto-uploaded images, and embedded PDF previews.
- **Pages, Assignments, Syllabus** — sync any of them from a `.md` file. Existing entries are updated in place by title / name.
- **Gradebook viewer** — terminal table, `less -SR` pager, or interactive Textual TUI with a sticky Student column.
- **Institution-agnostic** — API URL, token, course ID, and theme color live in a per-course `.canvas.json`.
- **Extensible** — plugin packages can add their own `canvas` subcommands (see [Plugins](#plugins)).

## Installation

```bash
pip install canvas-md

# With the Textual TUI for the gradebook
pip install "canvas-md[tui]"

# From source (editable, recommended while iterating)
pip install -e /path/to/canvas-md/packages/canvas-md
```

Requires Python 3.10+.

Optional system dependency: **less** — used by `canvas ls gradebook --pager` (standard on macOS and most Linux distros).

## Configuration

Create a `.canvas.json` file in the root of each course directory:

```json
{
    "api_url": "https://YOUR-INSTITUTION.instructure.com",
    "api_token": "YOUR-TOKEN",
    "course_id": "123456",
    "theme_color": "#522d80"
}
```

Generate an API token from *Account → Settings → Approved Integrations → New Access Token* in Canvas. The `course_id` is the number in the URL when you view the course.

`theme_color` is optional and controls the accent color used for h2 headings, table headers, and links in rendered HTML. It defaults to `#2C3E50` (a neutral dark blue-gray).

All settings can also be provided via environment variables, which override the config file:

```
CANVAS_API_URL
CANVAS_API_TOKEN
CANVAS_COURSE_ID
CANVAS_THEME_COLOR
```

**Keep `.canvas.json` out of version control.** Add it to `.gitignore`.

## CLI reference

### List resources

```bash
canvas ls courses                # all courses you can see
canvas ls assignments            # course assignments
canvas ls pages                  # course pages
canvas ls quizzes                # course quizzes
canvas ls syllabus               # syllabus summary
canvas ls gradebook              # formatted gradebook table
canvas ls gradebook --pager      # horizontally scrollable via less -SR
canvas ls gradebook --tui        # interactive Textual TUI (needs [tui] extra)
canvas ls gradebook --total      # show points instead of percentages
canvas ls gradebook --assignment "HW 1,HW 2"   # filter to these assignments
canvas ls <resource> --json      # raw JSON output
```

### Upload a markdown page

```bash
canvas up page lectures/lecture-05.md
canvas up page lectures/lecture-05.md --publish
```

Extracts the page title from the first `# heading` line. Existing pages with the same title are updated (pass `--no-update` to always create a new one).

### Upload a markdown assignment

```bash
canvas up assignment hw/hw3.md --publish
```

The assignment name comes from the first `# heading`. These special lines are parsed out of the markdown:

- `**Due**: M/D/YY` — due date (time defaults to 2:00 PM local).
- `**Points**: N` — overrides the `--points` flag.

### Upload the syllabus

```bash
canvas up syllabus syllabus.md
```

### Markdown → standalone HTML (no Canvas)

```bash
md2html lectures/lecture-05.md                   # writes lecture-05.html
md2html lectures/lecture-05.md --standalone      # full page with <style>
md2html lectures/lecture-05.md --theme-color "#522d80"
```

## Markdown conventions

### Due dates and points

In a homework/assignment file:

```markdown
# Problem Set 3

**Due**: 2/14/26
**Points**: 10

## Problem 1
...
```

### Math

Inline: `$f(x) = x^2$` · Display: `$$\nabla \cdot \mathbf{E} = 4\pi \rho$$`.

The converter protects math blocks from markdown processing so `\mathbf`, `\_`, and friends render correctly. Display math stays as `$$...$$` (Canvas renders it natively); inline math is rewritten to `\(...\)` for Canvas compatibility.

### Images and PDF handouts

```markdown
![alt text](figures/diagram.png)
[Handout (PDF)](handouts/problem-set-3.pdf)
```

Local images are uploaded to the course `images/` folder; PDF links are uploaded to `uploads/` and embedded as an in-page iframe preview alongside a download link.

### Internal links between pages

Use the full Canvas page slug from `canvas ls pages`:

```markdown
See [Lecture 5](https://YOUR-INSTITUTION.instructure.com/courses/123456/pages/lecture-5-title-slug)
```

## Plugins

Other packages can add subcommands to the `canvas` CLI. Installing a plugin is enough — its commands appear automatically:

- [`canvas-auto-quiz`](https://github.com/clemson-cal/canvas-md) — adds `canvas up quiz`: write pools of T/F statements in markdown and sample them into Canvas quizzes.

To write your own plugin, declare an entry point in the `canvas_md.commands` group:

```toml
[project.entry-points."canvas_md.commands"]
mycommand = "my_package.cli:register"
```

Your `register(ctx)` function receives a `canvas_md.cli.CLIContext` with the top-level, `ls`, and `up` subparser objects. Attach a parser and call `set_defaults(func=<handler>, needs_course=<bool>)`; the handler is invoked as `func(api, args) -> int` with a configured `CanvasAPI` (or `api=None` when `args.dry_run` is truthy, in which case no credentials are loaded).

## Python API

The CLI is a thin wrapper over a public Python API:

```python
from canvas_md import CanvasAPI, get_config, convert
from pathlib import Path

config = get_config()  # reads .canvas.json + env vars from cwd
api = CanvasAPI(
    config["api_url"],
    config["api_token"],
    config["course_id"],
    theme_color=config.get("theme_color", "#2C3E50"),
)

# Upload a page
api.upload_page(Path("lectures/lecture-05.md"), publish=True)

# Convert markdown to Canvas-ready HTML without uploading
html = convert(Path("lectures/lecture-05.md"), theme_color="#522d80")
```

## Per-course workflow

1. Create a course directory with a `.canvas.json` file (gitignored).
2. Put lectures in `lectures/lecture-NN.md`, homework in `hw/hwN.md`, and a `syllabus.md`.
3. After editing a lecture or homework file, upload it:

    ```bash
    canvas up page lectures/lecture-05.md
    canvas up assignment hw/hw3.md
    ```

The same installed CLI works across any number of course directories — just cd into each one; `.canvas.json` selects the course.

## License

MIT — see [LICENSE](LICENSE).
