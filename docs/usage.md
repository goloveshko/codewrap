# CodeWrap – Git History Processing Guide

This guide explains how to collect a list of files modified or added in the last N days and then process them with **CodeWrap** (`main.py`) to generate a Markdown context file with highlighted code blocks.

---

## 1. Generate the file list from Git

To get a sorted, unique list of file names that were touched in the last N days, run this command from the root of your Git repository:

```bash
git log --since="N days ago" --name-only --pretty=format: | sort -u > changed_files.txt
```

**Example** for the last 10 days:
```bash
git log --since="10 days ago" --name-only --pretty=format: | sort -u > changed_files.txt
```

- `--name-only` outputs only file paths (no commit messages).
- `--pretty=format:` removes extra headers.
- `sort -u` removes duplicates.

The file `changed_files.txt` will contain one relative path per line (e.g., `src/main.cpp`).

---

## 2. (Optional) Manual editing

You may edit `changed_files.txt` to remove any files you do not wish to include.  
Each line should be a path relative to the project root – exactly as produced by `git log`.  
Save the file after editing.

---

## 3. Run CodeWrap with the file list

Navigate to the directory where `main.py` is located (or use the full path).  
Then execute:

```bash
python main.py /path/to/project --files-list changed_files.txt --no-tree --output result.md
```

If you are already inside the project root, you can use `.`:

```bash
python main.py . --files-list changed_files.txt --no-tree --output result.md
```

### Explanation of options:
- `directory` – the root folder of your project (where `changed_files.txt` paths are relative to).
- `--files-list` – path to the file with the list of files (the script looks for it in the project directory first).
- `--no-tree` – disables generation of the directory tree (recommended when processing a specific list).
- `--output` – name of the output Markdown file (saved inside the project directory by default).

> **Note:** If you omit `--output`, a name will be auto‑generated from the project folder name.

---

## 4. Result

The output file (e.g., `result.md`) will contain:
- A header with the project name.
- For each file, a Markdown fenced code block with the appropriate language tag (based on file extension).
- A token count comment (for LLM context awareness).

Example snippet:

````markdown
## File: src/main.cpp
<!-- Tokens: 123 -->
```cpp
#include <iostream>
int main() { ... }
```
````

---

## 5. Full automation (optional)

You can combine all steps into a single script. For example, a Bash script:

```bash
#!/bin/bash
DAYS=10
git log --since="$DAYS days ago" --name-only --pretty=format: | sort -u > changed_files.txt
# (edit changed_files.txt if needed)
python main.py . --files-list changed_files.txt --no-tree --output "context_$(date +%Y-%m-%d).md"
```

Or a PowerShell script (Windows):

```powershell
$days = 10
git log --since="$days days ago" --name-only --pretty=format: | Sort-Object -Unique > changed_files.txt
python main.py . --files-list changed_files.txt --no-tree --output "context_$(Get-Date -Format yyyy-MM-dd).md"
```

---

## Common issues

| Problem | Solution |
|---------|----------|
| `changed_files.txt` not found | Make sure the file is in the project directory or provide an absolute path with `--files-list`. |
| Some files are skipped | Check that the paths in the list are relative to the project root. Also verify that the files exist and are not ignored by `.gitignore` (use `--no-respect-gitignore` if needed). |
| No output file created | Ensure you have write permissions in the project folder. The script creates the output file in the project directory (unless an absolute path is given). |

---

For more help, run:

```bash
python main.py --help
```