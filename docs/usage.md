# CodeWrap – Git Integration & Workflow Guide

This guide demonstrates how to gather code context from Git repositories using **CodeWrap** (`codewrap`).

CodeWrap features built-in Git intelligence as well as support for processing custom file lists.

---

## 1. Native Git Commands (Zero Setup)

You don't need manual shell scripts to process Git changes. CodeWrap provides built-in Git options:

### A. Process Only Modified / Uncommitted Files (`-m`)
To gather context only for files that were modified, staged, or added recently:
```bash
codewrap -m -c
```
*(Option `-c` automatically copies the resulting Markdown directly to your clipboard)*

### B. Process Files Changed Since a Specific Date or Commit (`--since`)
To gather files changed within the last N days or since a specific commit:
```bash
# Changed in the last 3 days
codewrap --since "3 days ago" -c

# Changed since commit HEAD~5
codewrap --since "HEAD~5" -c
```

### C. Generate Unified Git Diff for Code Reviews (`--diff`)
Instead of sending full file contents, generate a compact `git diff` context block (saves up to 90% of LLM tokens):
```bash
codewrap --diff -c
```

### D. Auto-Detection
If you run `codewrap` inside a Git repository without arguments or presets, it **automatically detects Git** and processes all tracked files while ignoring binary files and `.gitignore` entries.

---

## 2. Processing Custom File Lists (`-f` / `--files-list`)

If you want to manually curate a list of files, generate a list and pass it via `-f`:

### Extract File List:
```bash
# Bash (Linux / macOS)
git log --since="7 days ago" --name-only --pretty=format: | sort -u | grep -v '^$' > changed_files.txt

# PowerShell (Windows)
git log --since="7 days ago" --name-only --pretty=format: | Where-Object { $_ -ne "" } | Sort-Object -Unique > changed_files.txt
```

### Run CodeWrap with the List:
```bash
codewrap . -f changed_files.txt -c -n
```

---

## 3. Automation Scripts

### Bash Script (`process_git.sh`):
```bash
#!/usr/bin/env bash
DAYS=${1:-7}

echo "Gathering files changed in the last $DAYS days..."
codewrap --since="$DAYS days ago" -c -n
```

### PowerShell Script (`process_git.ps1`):
```powershell
param (
    [int]$Days = 7
)

Write-Host "Gathering files changed in the last $Days days..." -ForegroundColor Cyan
codewrap --since="$Days days ago" -c -n
```

---

## Useful Command Reference

| Option | Short | Description |
| :--- | :--- | :--- |
| `--modified` | `-m` | Gather uncommitted/modified Git files |
| `--since` | | Gather files changed since date/commit |
| `--diff` | | Generate unified git diff block |
| `--files-list` | `-f` | Process files from a line-separated text file |
| `--copy` | `-c` | Copy result directly to clipboard |
| `--numbered` | `-n` | Auto-number output file if duplicate exists (`_1.md`) |
| `--cwd` | `-w` | Save output in execution folder instead of project root |
| `--bind` | `-b` | Bind saved preset to current folder (Zero-Clutter) |