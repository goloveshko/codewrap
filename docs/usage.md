# CodeWrap – Git Integration & Workflow Guide

This guide demonstrates how to gather code context from Git repositories using **CodeWrap** (`codewrap`).

CodeWrap features built-in Git intelligence as well as support for processing custom file lists.

---

## 1. Native Git Commands (Zero Setup)

You don't need manual shell scripts to process Git changes. CodeWrap provides built-in Git options:

### A. Process Only Modified / Uncommitted Files (`-m`)
To gather context only for files that were modified, staged, or newly created (untracked files are included):
```bash
codewrap -m -c
```
*(Option `-c` automatically copies the resulting Markdown directly to your clipboard)*

### B. Process Files Committed Since a Date (`--since` / `-s`)
To gather files touched by commits within the last N days (dates only — `git log --since` syntax):
```bash
codewrap -s "3 days ago" -c
```

### C. Generate a Compact Diff (`--diff` / `-d`)
Instead of sending full file contents, generate smart diff context (saves up to 90% of LLM tokens):
```bash
# Uncommitted changes: unified diff for modified files, full content for new ones
codewrap -d -c

# Everything committed in the last 3 days: diff against the last commit before that date
codewrap -d -s "3 days ago" -c
```

### D. Auto-Detection
If you run `codewrap` inside a Git repository without arguments, it **automatically detects Git** and processes all tracked files while ignoring binary files and `.gitignore` entries.

---

## 2. Targets and File Lists

Pass files or folders as plain arguments; use `path:ext1,ext2` to filter by extension:
```bash
codewrap src/a.py "tests:py,toml"      # explicit targets
codewrap -x "tests/**" -x "*.lock"     # everything except these globs
codewrap -f changed_files.txt          # one path (or 'path:ext' rule) per line, '#' comments allowed
```

Generate a list with Git yourself if you need custom selection logic:
```bash
# Bash (Linux / macOS)
git log --since="7 days ago" --name-only --pretty=format: | sort -u | grep -v '^$' > changed_files.txt

# PowerShell (Windows)
git log --since="7 days ago" --name-only --pretty=format: | Where-Object { $_ -ne "" } | Sort-Object -Unique > changed_files.txt
```

---

## 3. Token Counting

Token totals are measured over the final assembled document with `tiktoken`. Pick the encoding by target model with `-e` (or persist it via `codewrap config set --tokenizer claude`):

```bash
codewrap -e claude .      # cl100k_base — closest approximation for Claude
codewrap -e gpt-4o .      # o200k_base (default) — exact for GPT-4o / o1 / o3
codewrap config tokenizers  # show encodings, aliases, and notes
```

The summary always states the encoding used; if tiktoken cannot load it (e.g. first run without network), the count is marked as a rough estimate instead of failing silently.

---

## 4. Filtering, Size Caps and Skip Reporting

CodeWrap skips files that don't belong in an LLM context:

```bash
codewrap                          # skips binaries and files over the default 512kb cap
codewrap --max-file-size 2mb      # raise the cap for a single run
codewrap --max-file-size 0        # disable the size cap entirely
codewrap config set --max-file-size 1mb   # persist a new default
```

Binary detection combines the extension list with content sniffing (NUL bytes, UTF-8 validity and control-character ratio over an 8KB sample), so a mislabeled or extension-less binary is still caught.

Every skipped file is reported: the generated document opens with a short legend and ends with an **Excluded files** table giving each file's size and a reason code:

- `BINARY` — binary or media asset
- `EXCLUDED` — matched `.gitignore` or a `-x/--exclude` pattern
- `LARGE` — over the `--max-file-size` cap
- `UNREADABLE` — could not be read from disk

Only files you deliberately excluded with `-x` appear as `EXCLUDED`; `.gitignore` and built-in defaults are skipped silently to keep the table meaningful.

---

## 5. Splitting Large Outputs (`--split`)

Many chat UIs handle several smaller files better than one huge paste. `--split` packs whole file sections into budgeted parts:

```bash
codewrap --split 50000     # a bare number = up to 50,000 tokens per part
codewrap --split 256kb     # a size suffix = up to 256KB of bytes per part
```

- If everything fits in one budget, the normal single `<name>_context.md` is written as usual.
- Otherwise a `<name>_context/` folder holds `part_01.md`, `part_02.md`, … plus a `manifest.md` index (files, tokens and size per part). Paste the parts one by one, in order.
- The bundle folder is never re-scanned on later runs, and stale parts are cleared automatically.
- `--split` does not apply to a raw `--since` diff (`-d -s`), which is a single diff block; use smart diff (`-d`) or a normal scan instead.

---

## Useful Command Reference

| Option | Short | Description |
| :--- | :--- | :--- |
| `PATH` / targets | | One path = project root to scan; multiple = explicit `file`, `folder` or `folder:ext` targets |
| `--modified` | `-m` | Gather uncommitted Git files (modified, staged, and untracked) |
| `--since` | `-s` | Gather files committed since a date (with `-d`: diff since that date) |
| `--diff` | `-d` | Smart diff mode: unified diff for modified, full content for new files |
| `--exclude` | `-x` | Exclude git-style glob (repeatable) |
| `--files-list` | `-f` | Process files from a line-separated text file |
| `--encoding` | `-e` | Count tokens for a target model: `claude`, `gpt-4o`, or an encoding name |
| `--output` | `-o` | Custom output Markdown path |
| `--copy` | `-c` | Copy result directly to clipboard |
| `--rename` | `-r` | Auto-rename output file if duplicate exists (`_1.md`) |
| `--cwd` | `-w` | Save output in terminal execution folder instead of project root |
| `--max-file-size` | | Skip files over this size, e.g. `512kb`, `2mb` (bare number = bytes; `0` disables; default `512kb`) |
| `--split` | | Split big outputs into a folder of budgeted parts + manifest (bare number = tokens, e.g. `50000`; or a size, e.g. `256kb`) |

Source options (`-m`, `-s`, `-f`, target arguments) are mutually exclusive — combining them is a usage error (exit code 2), not a silent precedence rule.
