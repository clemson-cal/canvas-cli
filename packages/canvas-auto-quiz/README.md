# canvas-auto-quiz

A quiz-bank plugin for [canvas-md](https://pypi.org/project/canvas-md/). Write pools of true/false statements in markdown, then sample balanced random subsets into a [Canvas LMS](https://www.instructure.com/canvas) quiz — with explanations shown to students as per-answer comments.

## Installation

```bash
pip install canvas-auto-quiz

# From source (editable)
pip install -e /path/to/canvas-md/packages/canvas-auto-quiz
```

Installing the package is all it takes: the `canvas up quiz` subcommand appears automatically (registered through canvas-md's `canvas_md.commands` entry-point group). Configuration — API URL, token, course ID — comes from the same `.canvas.json` / environment variables as canvas-md itself.

## Usage

```bash
canvas up quiz quiz-bank.md --title "Quiz 1" --points 10 --sample 5 --due 2/14/26
canvas up quiz quiz-bank.md --title "Quiz 2" --questions 3,4,7 --seed 42
canvas up quiz quiz-bank.md --title "Preview" --dry-run            # open HTML preview
canvas up quiz quiz-bank.md --title "Preview" --dry-run text       # print to terminal
```

Flags:

- `--title` — quiz title (required). Re-running with the same title updates the existing quiz in place.
- `--sample N` — T/F statements sampled per question (default 5, enforces a balanced T/F ratio).
- `--seed S` — random seed for reproducible sampling.
- `--questions A,B,C` — select specific question numbers from the bank.
- `--num-questions N` — randomly select N questions from the bank.
- `--points P` — total points for the quiz (default 10).
- `--due M/D/YY` — due date (2:00 PM).
- `--attempts N` — allowed attempts (default 1; use `-1` for unlimited).
- `--publish` — publish immediately (default: draft).
- `--dry-run [html|text]` — preview without uploading (no Canvas credentials needed).

## Quiz bank format

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
- LaTeX math in `$...$` / `$$...$$` is converted to Canvas-native delimiters.

## Python API

```python
from canvas_auto_quiz import parse_quiz_bank, sample_quiz, build_canvas_quiz_data
from pathlib import Path

questions = parse_quiz_bank(Path("quiz-bank.md"))
items = sample_quiz(questions, sample_size=5, seed=42)
quiz_data, question_payloads = build_canvas_quiz_data(
    title="Quiz 1", quiz_items=items, points_per_statement=0.4,
)
```

## License

MIT — see [LICENSE](LICENSE).
