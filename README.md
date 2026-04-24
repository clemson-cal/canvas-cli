# canvas-cli

A markdown-first course-authoring CLI for [Canvas LMS](https://www.instructure.com/canvas). Write your lectures, homework, and quizzes in plain markdown and push them to Canvas with a single command. LaTeX math, embedded images, and PDF handouts are handled for you.

Built for instructors who prefer version-controlled markdown over Canvas's rich-text editor.

## Features

- **Markdown → Canvas HTML** with full LaTeX math support (inline `$...$` and display `$$...$$`), auto-uploaded images, and embedded PDF previews.
- **Pages, Assignments, Syllabus** — sync any of them from a `.md` file. Existing entries are updated in place by title / name.
- **Quiz bank** — write T/F statement pools in markdown; sample random subsets into a Canvas quiz with explanations shown as per-answer comments.
- **Gradebook viewer** — terminal table, `less -SR` pager, or interactive Textual TUI with a sticky Student column.
- **LaTeX export** — the same markdown can be compiled to a standalone PDF via pandoc + pdflatex.
- **Institution-agnostic** — API URL, token, course ID, and theme color live in a per-course `.canvas.json`.

## Installation

```bash
# From the package source (editable, recommended while iterating)
pip install -e /path/to/canvas-cli/python

# With the Textual TUI for the gradebook
pip install -e "/path/to/canvas-cli/python[tui]"
```

Optional system dependencies (only needed for specific features):

- **pandoc** — required for `canvas tex` / `md2tex` (install via `brew install pandoc`, `apt install pandoc`, or `choco install pandoc`).
- **pdflatex** — required for `canvas tex --pdf` (install MacTeX / TeX Live / MiKTeX).
- **less** — required for `canvas ls gradebook --pager` (standard on macOS and most Linux distros).

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

### Generate and upload a quiz from a quiz bank

```bash
canvas up quiz quiz-bank.md --title "Quiz 1" --points 10 --sample 5 --due 2/14/26
canvas up quiz quiz-bank.md --title "Quiz 2" --questions 3,4,7 --seed 42
canvas up quiz quiz-bank.md --title "Preview" --dry-run            # open HTML preview
canvas up quiz quiz-bank.md --title "Preview" --dry-run text       # print to terminal
```

Flags:

- `--title` — quiz title (required).
- `--sample N` — T/F statements sampled per question (default 5, enforces a balanced T/F ratio).
- `--seed S` — random seed for reproducible sampling.
- `--questions A,B,C` — select specific question numbers from the bank.
- `--num-questions N` — randomly select N questions from the bank.
- `--points P` — total points for the quiz (default 10).
- `--due M/D/YY` — due date (2:00 PM).
- `--attempts N` — allowed attempts (default 1; use `-1` for unlimited).
- `--publish` — publish immediately (default: draft).
- `--dry-run [html|text]` — preview without uploading.

### Export markdown to LaTeX / PDF

```bash
canvas tex lectures/lecture-05.md                # writes lecture-05.tex
canvas tex lectures/lecture-05.md --pdf          # also compiles the PDF and opens it
canvas tex lectures/lecture-05.md --stdout       # print .tex to stdout
canvas tex lectures/lecture-05.md --body         # body fragment only (no preamble)
canvas tex ... --pandoc-arg=--template=mine.tex  # forward extra args to pandoc
```

Also available as a standalone `md2tex` command.

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

### Quiz bank format

```markdown
## Question 1: Gauss's law

A point charge $q$ sits at the center of a cubical Gaussian surface of side $L$.

- [x] The flux through the cube equals $4\pi q$.
- [x] The flux through any single face is $\tfrac{4\pi q}{6}$.
- [ ] The flux depends on $L$.
- [ ] Moving the charge off-center changes the total flux.

### Explanations

- **True** — Gauss's law in Gaussian units: $\oint \mathbf{E} \cdot d\mathbf{A} = 4\pi q_{enc}$.
- **True** — By symmetry, each of the six faces sees an equal share.
- **False** — Total flux depends only on enclosed charge, not geometry.
- **False** — As long as the charge stays inside, the total flux is unchanged.
```

- `## Question N: Title` starts a new question. Questions are numbered in the file; `--questions 1,3,5` picks by number.
- The scenario is everything after the heading up to the first `- [ ]` / `- [x]` checkbox.
- `- [x]` is a true statement; `- [ ]` is false.
- `### Explanations` pairs explanations to statements by position. Each becomes a per-answer comment shown after the student submits.
- One bank question becomes one Canvas *multiple-answers* question; `--sample N` draws a random subset, keeping a balanced T/F ratio so the denominator is consistent.

## Python API

The CLI is a thin wrapper over a public Python API:

```python
from canvas import CanvasAPI, get_config, convert, parse_quiz_bank
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

# Parse a quiz bank
questions = parse_quiz_bank(Path("quiz-bank.md"))
for q in questions:
    print(q.number, q.title, len(q.statements), "statements")
```

## Per-course workflow

1. Create a course directory with a `.canvas.json` file (gitignored).
2. Put lectures in `lectures/lecture-NN.md`, homework in `hw/hwN.md`, a `quiz-bank.md`, and a `syllabus.md`.
3. After editing a lecture or homework file, upload it:

    ```bash
    canvas up page lectures/lecture-05.md
    canvas up assignment hw/hw3.md
    ```

4. Generate quizzes from the bank:

    ```bash
    canvas up quiz quiz-bank.md --title "Quiz 3" --sample 5 --due 2/28/26
    ```

The same installed CLI works across any number of course directories — just cd into each one; `.canvas.json` selects the course.

## License

MIT — see [LICENSE](LICENSE).
