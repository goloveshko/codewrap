# CodeWrap – Git History & File List Processing Guide

This guide demonstrates how to extract modified or added files from Git history and generate a clean Markdown context file using **CodeWrap** (`codewrap`).

---

## 1. Extract Modified Files from Git

To get a sorted, unique list of files modified or created in the last N days, run the following command from your Git repository root:

### Linux / macOS (Bash / Zsh):
```bash
git log --since="10 days ago" --name-only --pretty=format: | sort -u | grep -v '^$' > changed_files.txt
```

### Windows (PowerShell):
```powershell
git log --since="10 days ago" --name-only --pretty=format: | Where-Object { $_ -ne "" } | Sort-Object -Unique > changed_files.txt
```

This creates `changed_files.txt` containing one relative file path per line (e.g., `src/main.cpp`).

---

## 2. (Optional) Filter the File List

You can open `changed_files.txt` in any text editor to remove unneeded files or add specific ones.  
Ensure paths remain relative to the project root.

---

## 3. Run CodeWrap with the File List

Use the `--files-list` (or `-f`) flag to feed the list to CodeWrap.

```bash
# Basic run
codewrap . -f changed_files.txt -o git_context.md

# Advanced run: Copy result to clipboard (-c) and use numbering (-n)
codewrap . -f changed_files.txt -c -n
```

If you are developing locally with `uv`:
```bash
uv run codewrap . -f changed_files.txt -c -n
```

### Useful Options for Git Workflows:
* `-f, --files-list` – Path to the list file.
* `-c, --copy` – Automatically copy generated Markdown directly to your clipboard.
* `-n, --numbered` – Auto-increment filename if output already exists (`git_context_1.md`).
* `-s, --save-preset <name>` – Save this scanning configuration as a reusable preset.
* `-w, --cwd` – Output the resulting file in the current terminal folder instead of the project root.

---

## 4. Markdown Output Format

The output Markdown contains:
- Project title header.
- Fenced code blocks with language-specific syntax highlighting.
- **Clean output:** Token metadata is reported in the terminal output to keep prompt tokens lean without polluting the LLM context.

Example snippet:

````markdown
# Project Context: MyApp

## File: src/main.cpp
```cpp
#include <iostream>
int main() { ... }
```
````

---

## 5. Full Automation Scripts

### Bash Script (`process_git.sh`):
```bash
#!/usr/bin/env bash
DAYS=${1:-7}
OUTPUT_FILE="git_context_$(date +%Y-%m-%d).md"

echo "Extracting modified files from the last $DAYS days..."
git log --since="$DAYS days ago" --name-only --pretty=format: | sort -u | grep -v '^$' > changed_files.txt

if [ ! -s changed_files.txt ]; then
    echo "No files changed in the last $DAYS days."
    exit 0
fi

codewrap . -f changed_files.txt -o "$OUTPUT_FILE" -c
rm changed_files.txt
echo "Context generated: $OUTPUT_FILE (copied to clipboard!)"
```

### PowerShell Script (`process_git.ps1`):
```powershell
param (
    [int]$Days = 7
)

$date = Get-Date -Format "yyyy-MM-dd"
$output = "git_context_$date.md"

git log --since="$Days days ago" --name-only --pretty=format: | Where-Object { $_ -ne "" } | Sort-Object -Unique > changed_files.txt

if ((Get-Item changed_files.txt).Length -eq 0) {
    Write-Host "No files changed in the last $Days days." -ForegroundColor Yellow
    Exit
}

codewrap . -f changed_files.txt -o $output -c
Remove-Item changed_files.txt
Write-Host "Context generated: $output (copied to clipboard!)" -ForegroundColor Green
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `changed_files.txt` not found | Ensure the file is inside the current directory or provide an absolute path (`-f /path/to/changed_files.txt`). |
| Ignored files missing | Files listed in `.gitignore` are excluded by default. Update `.gitignore` or check permissions if files are missing. |
| Command `codewrap` not found | Install globally via `uv tool install . --force` or run using `uv run codewrap`. |