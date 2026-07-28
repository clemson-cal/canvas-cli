# canvas-cli monorepo

Markdown-first course-authoring tools for [Canvas LMS](https://www.instructure.com/canvas), split into a general-purpose core and opt-in plugin packages.

| Package | What it is |
|---|---|
| [`packages/canvas-cli`](packages/canvas-cli) | The core CLI and Python API: sync markdown pages, assignments, and syllabi to Canvas (LaTeX math, image uploads, PDF embeds), list resources, and view the gradebook. Defines the `canvas_cli.commands` entry-point group that plugins register into. |
| [`packages/canvas-auto-quiz`](packages/canvas-auto-quiz) | Plugin adding `canvas up quiz`: write pools of T/F statements in markdown and sample balanced random subsets into Canvas quizzes. |

The core stays institution- and workflow-agnostic; opinionated authoring formats live in plugins. Installing a plugin package is all it takes for its subcommands to appear in the `canvas` CLI.

## Development

```bash
pip install -e packages/canvas-cli -e packages/canvas-auto-quiz pytest
pytest packages/canvas-cli/tests packages/canvas-auto-quiz/tests
```

Requires Python 3.10+.

## License

MIT — see [LICENSE](LICENSE).
