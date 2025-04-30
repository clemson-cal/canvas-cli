# Canvas CLI Tool

A command-line interface for interacting with the Canvas LMS API. This tool simplifies common Canvas tasks for instructors and teaching assistants.

## Features

- List courses, assignments, files, students, and assignment groups
- Set and view configuration options
- Create and edit assignments from Markdown files with YAML frontmatter
- Upload files to Canvas
- Create assignment groups
- Download and display gradebook information

## Installation

```bash
pip install git+https://github.com/clemson-cal/canvas-cli.git
```
(Coming soon... for now just check out the repository and use the script)

Required dependencies:
- canvasapi
- typer
- rich
- pyyaml
- markdown

## Getting Started

You will need a Canvas API key. Go to Account > Settings > New Access Token. Commands in the `set` category create or modify a .canvas file in the current directory.

```bash
python canvas.py set api_url https://your-institution.instructure.com
python canvas.py set api_key your-canvas-api-key
python canvas.py list courses # find the ID of your course, e.g. 123456
python canvas,pu set course 123456
```

## Usage Examples

### View Configuration

```bash
python canvas.py show api_url
python canvas.py show course
```

### List Items

```bash
python canvas.py list courses
python canvas.py list assignments
python canvas.py list files
python canvas.py list students
python canvas.py list assignment_groups
```

### Create Assignment

Create a Markdown file with YAML frontmatter like:

```markdown
---
name: Assignment Title
points_possible: 100
assignment_group_id: 12345
due_at: January 15, 2023 23:59
---

# Assignment Title

Instructions go here...
```

Then create the assignment:

```bash
python canvas.py create assignment assignment.md --publish
```

### Upload File

```bash
python canvas.py create file path/to/file.pdf
```

### Create Assignment Group

```bash
python canvas.py create assignment_group "Homework"
```

## Markdown and LaTeX Support

The tool supports Markdown formatting and preserves LaTeX math expressions (enclosed in `\(` and `\)`) when creating assignments.
