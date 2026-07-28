# CLAUDE.md

Monorepo for markdown-first Canvas LMS course-authoring tools: `packages/canvas-cli` (generic core; import name `canvas_cli`) and `packages/canvas-auto-quiz` (quiz-bank plugin registered via the `canvas_cli.commands` entry-point group). Generic features belong in core; opinionated personal-workflow features belong in plugin packages.

## Project planning note: canvas-cli.md

`canvas-cli.md` at the repo root is the project's planning and task-tracking note. It is version-controlled here and simultaneously appears in the owner's Obsidian vault via a symlink (`~/Work/Obsidian/Projects/canvas-cli.md` → this file).

- **It must remain a regular file at this path** — the vault symlink points here. Never replace it with a symlink, and don't move or rename it without updating the vault link.
- It is the *planning layer*: goals, next actions, and a dated decision log. Treat it as **non-exhaustive** — record significant tasks and decisions, not every micro-step.
- When finishing meaningful work, update it: check off completed `- [ ]` items, add newly discovered next actions, and append a dated entry to **Log** for decisions git history doesn't capture (why something was removed, where a feature belongs, dead ends). Newest log entries first.
- Preserve its Obsidian conventions: YAML frontmatter, `- [ ]` checkbox tasks (parsed by the vault's Tasks plugin), and any `[[wiki-links]]`.
