# CodeWrap

**CodeWrap** is a professional CLI tool that gathers source code context into a single Markdown file, ready to be fed into an LLM (GPT, Claude, etc.). It walks your project, respects `.gitignore`, skips binary files, and reports approximate token counts via `tiktoken`.

![CodeWrap CLI Preview](docs/assets/cli_preview.png)

## Features

- **Full project scan** — wrap an entire codebase or targeted subsets (`folder:ext1,ext2`, single files) into one Markdown document.
- **Git-aware modes:**
  - `--modified` (`-m`) — only files with uncommitted changes.
  - `--since <ref>` (`-s`) — files changed since a date or commit.
  - `--diff` (`-d`) — unified Git diff as context.
  - `--patch` (`-pt`) — smart patch: diffs for modified files, full content for newly staged ones.
- **Presets & Zero-Clutter bindings** — save reusable scan configurations, bind them to folders, or use a local `.codewrap.json`.
- **Accurate token counting** — customizable LLM `tokenizer` (`o200k_base` by default, `cl100k_base`, etc.) with graceful fallback estimates.
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
codewrap .

# Wrap specific target rules: Python and TOML files only
codewrap . --target "src:py,toml" --target "pyproject.toml"

# Only uncommitted changes and copy directly to clipboard
codewrap . --modified -c

# Files changed in the last 3 days
codewrap . --since "3 days ago"

# Unified diff of uncommitted changes as context
codewrap . --diff

# Smart patch: diffs for modified + full content for staged new files
codewrap . --patch

# Prevent overwriting existing context file by auto-renaming (_1.md)
codewrap . -r
```

The result is saved as `<project>_context.md` next to the project root (or in current working directory with `--cwd` / `-w`), and the approximate token count is printed when done.

## Target Rules

Targets are passed via `--target` (`-t`) using the syntax `path:extensions`:

| Rule | Meaning |
| --- | --- |
| `"src:py"` | all `.py` files under `src/` |
| `"src:py,toml"` | all `.py` and `.toml` files under `src/` |
| `"src/utils.py"` | a single file |
| `"tests"` | everything under `tests/` (no extension filter) |

## Presets and Local Configuration

```bash
# Save current options as a named preset
codewrap . --target "src:py" --save-preset myproj

# Reuse a preset
codewrap . --preset myproj

# Bind a preset to current folder — future bare runs auto-load it
codewrap . --preset myproj --bind
codewrap .   # <- automatically uses 'myproj'

# Create a local .codewrap.json config for the repository
codewrap . --init-config
```

Presets are stored in `~/.codewrap/presets/*.json`. A custom location can be set per run via `--presets-dir` (`-pd`).

## Global Settings

```bash
codewrap config                   # view global configuration table
codewrap config tokenizers        # view supported LLM tokenizers and models
codewrap config set --rename --copy
codewrap config show --json       # export raw JSON for scripting
codewrap config reset             # restore all defaults
```

Session-only flags (`--rename`, `--cwd`, `--copy`, `--presets-dir`) affect a single run without altering persistent global settings.

## Output Format

The generated Markdown groups each file into a fenced block tagged with its extension:

````markdown
# Project Context: my-project

## File: src/main.py
```python
...file content...
```
````

Diff modes produce `` ```diff `` blocks instead. Token counts are computed using `tiktoken`.

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