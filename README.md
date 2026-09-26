# CodeWrap

**CodeWrap** is a professional CLI tool that gathers source code context into a single Markdown file, ready to be fed into an LLM (GPT, Claude, etc.). It walks your project, respects `.gitignore`, skips binary files, and reports token counts via `tiktoken`.

![CodeWrap CLI Preview](docs/assets/cli_preview.png)

## Features

- **Full project scan** — wrap an entire codebase or explicit targets (files, `folder:py,toml` rules) into one Markdown document.
- **Git-aware modes:**
  - `--modified` (`-m`) — only files with uncommitted changes (untracked files included).
  - `--diff` (`-d`) — smart diff: unified diff for modified files, full content for new ones.
  - `--since <date>` (`-s`) — files committed since a date; with `-d`, the diff since that date.
- **Exclusions** — repeatable `-x/--exclude` git-style globs on top of `.gitignore` and built-in defaults.
- **Honest token counting** — totals are measured over the final document with `tiktoken`; choose the encoding by target model (`-e claude`, `-e gpt-4o`) and the summary states exactly what was used (or marks a rough estimate and why).
- **Auto-rename protection** — optional `--rename` (`-r`) mode appends incremental suffixes (`_1.md`, `_2.md`) to prevent accidental overwrites.
- **Smart filtering** — honors `.gitignore` plus built-in exclusions (`.venv/`, `__pycache__/`, `node_modules/`, binary assets, previous outputs).
- **Clipboard integration** — copy generated Markdown straight to the clipboard (`-c` / `--copy`).

## Installation

Requires Python 3.10+.

```bash
# With uv
uv tool install codewrap

# Or with pip
pip install codewrap
```

For clipboard support on Linux, a system backend such as `xclip` or `wl-clipboard` may be required.

## Quick Start

```bash
# Wrap current Git repository (tracked files auto-detected)
codewrap

# Wrap another project root
codewrap C:\Projects\myapp

# Explicit targets: everything under src/ that is .py/.toml, plus one file
codewrap "src:py,toml" pyproject.toml

# Everything except tests and lock files
codewrap -x "tests/**" -x "*.lock"

# Only uncommitted changes, copied to clipboard
codewrap -m -c

# Smart diff of uncommitted changes (diff for modified, full content for new files)
codewrap -d -c

# Diff of everything committed in the last 3 days
codewrap -d -s "3 days ago"

# Count tokens for Claude instead of GPT-4o
codewrap -e claude .

# Prevent overwriting existing context file by auto-renaming (_1.md)
codewrap -r
```

The result is saved as `<project>_context.md` next to the project root (or in current working directory with `--cwd` / `-w`).

Source options (`-m`, `-s`, `-f`, target arguments) are mutually exclusive — combining them fails fast instead of applying hidden precedence.

## Target Syntax

Targets are plain positional arguments (use `-f/--files-list` for long lists):

| Argument | Meaning |
| --- | --- |
| `src` | everything under `src/` |
| `"src:py"` | all `.py` files under `src/` |
| `"src:py,toml"` | all `.py` and `.toml` files under `src/` |
| `src/utils.py` | a single file |

A single existing directory argument is treated as the project root; two or more arguments are treated as targets relative to the current directory.

## Global Settings

```bash
codewrap config                   # view global configuration table
codewrap config tokenizers        # view encodings, model aliases, and notes
codewrap config set --tokenizer claude --copy
codewrap config show --json       # export raw JSON for scripting
codewrap config reset             # restore all defaults
```

Session-only flags (`-r`, `-w`, `-c`, `-e`) affect a single run without altering persistent global settings.

## Output Format

The generated Markdown groups each file into a fenced block tagged with its extension:

````markdown
# Project Context: my-project

## File: src/main.py
```python
...file content...
```
````

Diff modes produce `` ```diff `` blocks instead.

## Development & Testing

```bash
git clone https://github.com/goloveshko/codewrap.git
cd codewrap
uv sync

uv run ruff check .
uv run mypy src/
uv run pytest
```

## Support & Feedback

Developed with ❤️ by Sergey Goloveshko.

- **Telegram Support Bot**: [@itz2bot](https://t.me/itz2bot?start=github_codewrap)
- **Portfolio**: [goloveshko.github.io](https://goloveshko.github.io)
- **GitHub Issues**: [Report a bug](https://github.com/goloveshko/codewrap/issues)

## License

This project is licensed under the [MIT License](LICENSE).