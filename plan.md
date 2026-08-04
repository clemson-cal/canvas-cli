---
status: active
due:
local_path: ~/Work/Codes/canvas-md
url: https://github.com/clemson-cal/canvas-md
---

# canvas-md

## Goal

Complete the tool and publish it on PyPI. **Publishing is deferred** until the
feature set stabilizes against the needs of the current teaching assignment —
real course use is the design input, so the API should not be frozen by a
release before then.

## Next actions

Publishing is **blocked pending real-course use** (see Goal). The naming and
packaging groundwork is done, so the release itself is a short task whenever the
feature set settles; until then, drive changes from teaching needs.

- [x] Pick a new distribution name for the core: **`canvas-md`** (import `canvas_md`)
- [x] Rename the local repo directory `~/Work/Codes/canvas-cli` → `~/Work/Codes/canvas-md` (required exiting the editor/session)
- [x] Rename the GitHub repo `clemson-cal/canvas-cli` → `clemson-cal/canvas-md` and update the `origin` remote (done 2026-08-04; GitHub redirects the old URL)
- [x] Re-point the Obsidian vault link after the directory rename: `~/Work/Obsidian/Projects/canvas-md.md` → `~/Work/Codes/canvas-md/plan.md`
- [ ] ⏸ Test publish both packages to TestPyPI, then real release — deferred until features stabilize (see Goal)
- [x] Check name availability on PyPI: `canvas-cli` and `canvas-auto-quiz`
- [x] Reinstall local editable copies (paths changed) — via pipx, not bare pip (see 2026-08-04 log)
- [ ] Update any personal scripts importing `from canvas import ...` → `canvas_md` / `canvas_auto_quiz`
- [x] Write/verify `pyproject.toml` metadata (license, classifiers, entry points)
- [x] README with install + usage examples

## Log

- 2026-08-04 — **Deferred the PyPI release.** Holding off until the feature set
  stabilizes with respect to the requirements of the current teaching
  assignment. Rationale: publishing fixes the CLI surface and the
  `canvas_md.commands` plugin contract in public, and real course use is the
  best source of signal on what those should be — better to absorb breaking
  changes before anyone can depend on them. Nothing about the release is
  blocked technically: names are reserved-by-availability (not claimed), the
  metadata is written, and the rename is done, so this is a scheduling decision
  only. Risk accepted: `canvas-md` / `canvas-auto-quiz` are *available*, not
  registered — someone else could take either name in the meantime. If that
  becomes a worry, cut an early placeholder release to claim them.
- 2026-08-04 — Finished the rename cutover after restarting the session: local
  directory is now `~/Work/Codes/canvas-md`, the vault symlink resolves, and
  `origin` points at `clemson-cal/canvas-md`. No `canvas_cli` / `canvas-cli`
  references remain outside this note's history. All 12 tests pass.
  Local install is now **pipx**, not bare pip — `PIP_REQUIRE_VIRTUALENV=true`
  is set globally, so `pip install -e` into Homebrew python is refused. Used
  `pipx install -e packages/canvas-md` plus
  `pipx inject --editable canvas-md packages/canvas-auto-quiz`, matching how
  `astrobib` is installed. Injecting the plugin into the *same* pipx venv is
  what makes the `canvas_md.commands` entry-point discoverable — `canvas up
  quiz` is registered. Note pipx built the venv with Python 3.14.6, while the
  test venv uses 3.11; both work. pytest is deliberately **not** injected into
  the pipx venv — tests run from a separate throwaway venv.
- 2026-08-04 — Named the project **canvas-md**. Distribution `canvas-cli` →
  `canvas-md`, import package `canvas_cli` → `canvas_md`, plugin entry-point
  group `canvas_cli.commands` → `canvas_md.commands`, directory
  `packages/canvas-cli` → `packages/canvas-md`. Rejected alternatives:
  `md2canvas` (understates the non-conversion features), `canvas-author`,
  `canvas-course` (generic, reads like an official Instructure library).
  Deliberately **kept** the console command as bare `canvas` for muscle memory
  — accepting that it collides on PATH with Canvas Medical's `canvas-cli`,
  which installs a `canvas` command too. `md2html` likewise stays unprefixed.
  The plugin keeps its own name `canvas-auto-quiz` (already free on PyPI);
  plugins only need to match the entry-point group, not the core's prefix.
  Re-verified 2026-08-04 that `canvas-md` and `canvas-auto-quiz` are free.
  Package metadata URLs now point at `clemson-cal/canvas-md` **ahead of** the
  actual GitHub rename — rename the repo before publishing, or the links 404.
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

- Local repo: `~/Work/Codes/canvas-md`
- GitHub: https://github.com/clemson-cal/canvas-md
