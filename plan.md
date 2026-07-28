---
status: active
due:
local_path: ~/Work/Codes/canvas-cli
url: https://github.com/clemson-cal/canvas-cli
---

# canvas-cli

## Goal

Complete the tool and publish it on PyPI.

## Next actions

- [ ] Pick a new distribution name for the core (`canvas-cli` is taken on PyPI); candidates checked available 2026-07-28: `canvas-md`, `md2canvas`, `canvas-course`, `canvas-author`, `canvas-teach`, `canvas-coursekit`, `canvas-courseware`
- [ ] Test publish both packages to TestPyPI, then real release
- [x] Check name availability on PyPI: `canvas-cli` and `canvas-auto-quiz`
- [ ] Reinstall local editable copies (old layout is gone): `python3.11 -m pip install -e packages/canvas-cli -e packages/canvas-auto-quiz`
- [ ] Update any personal scripts importing `from canvas import ...` → `canvas_cli` / `canvas_auto_quiz`
- [x] Write/verify `pyproject.toml` metadata (license, classifiers, entry points)
- [x] README with install + usage examples

## Log

- 2026-07-28 — PyPI name check: `canvas-cli` is **taken** (Canvas Medical's
  EMR CLI, v1.3.4, by Beau Gunderson — also installs a `canvas` console
  command). `canvas-auto-quiz` is available. Core needs a new distribution
  name before publishing; the import name `canvas_cli` can stay regardless.
- 2026-07-28 — Removed `canvas-cli-backup`; the GitHub repo is now the only
  canonical copy. (Older copies in Google Drive under `Teaching/` may still
  exist — delete when next in there.)
- 2026-07-28 — Restructured into a monorepo (pushed as `75286a1`), separating
  publishable features from personal-workflow ones:
  - `packages/canvas-cli` (v0.3.0) — generic core: pages/assignments/syllabus
    sync, md2html, gradebook, `CanvasAPI`. Import package renamed
    `canvas` → `canvas_cli` (the bare name was too collision-prone to publish).
  - `packages/canvas-auto-quiz` (v0.1.0) — the T/F quiz-bank feature, now a
    plugin: installing it adds `canvas up quiz` via the `canvas_cli.commands`
    entry-point group. Same mechanism available for future idiosyncratic tools.
  - **Removed** the LaTeX export (`canvas tex` / `md2tex`) — it was a thin
    pandoc wrapper, not worth a package. If quiz-PDF export comes back, it
    belongs in canvas-auto-quiz.
  - Now requires Python ≥ 3.10 (macOS system python is 3.9 — use Homebrew 3.11).
  - Added pytest suites (12 tests: config, HTML converter, quiz parsing/sampling).
- 2026-07-25 — Project note created. Repo lives at `~/Work/Codes/canvas-cli`
  (there is also `canvas-cli-backup` alongside it, and older copies in Google
  Drive under `Teaching/` — worth consolidating so only one is canonical).

## Links & materials

- Local repo: `~/Work/Codes/canvas-cli`
- GitHub: https://github.com/clemson-cal/canvas-cli
