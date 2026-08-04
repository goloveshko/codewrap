# CodeWrap Developer & Build Guide

This document provides guidelines for local development, linting, type checking, building distribution packages, and publishing `codewrap`.

---

## 🛠 1. Environment Setup

The project uses `uv` as its primary package and project manager.

### Installing Dependencies
Clone the repository and set up the virtual environment with a single command:

```bash
uv sync
```

This command automatically creates `.venv`, fetches the correct Python version (specified in `.python-version`), and installs all core and dev dependencies matching `uv.lock`.

---

## 🧪 2. Code Quality & Testing

Before committing changes, ensure your code passes static analysis and type checks.

### Linting & Formatting (Ruff)
```bash
# Check code with Ruff
uv run ruff check .

# Automatically fix safe lint issues
uv run ruff check . --fix

# Verify code formatting
uv run ruff format --check .
```

### Type Checking (Mypy)
```bash
uv run mypy src
```

---

## 🚀 3. Local Execution During Development

You can run the CLI during development in two ways:

### Option A: Direct execution via `uv run` (No installation needed)
```bash
# Display help
uv run codewrap --help

# Scan directory with targets and save preset
uv run codewrap . -t "src:py,toml" -s my_preset -n
```

### Option B: Install globally in your local environment
To make the `codewrap` executable available system-wide:

```bash
uv tool install . --force
```

*(Re-run this command whenever you update source code to sync local binary)*.

---

## 📦 4. Building Distribution Artifacts

Build Wheel (`.whl`) and Source Tarball (`.tar.gz`) packages:

```bash
uv build
```

Artifacts will be generated in the `dist/` directory:
* `dist/codewrap-X.Y.Z-py3-none-any.whl`
* `dist/codewrap-X.Y.Z.tar.gz`

### Cleaning Build Artifacts
```bash
# Linux / macOS
rm -rf dist/ build/ *.egg-info

# Windows (PowerShell)
Remove-Item -Recurse -Force dist, build, *.egg-info -ErrorAction SilentlyContinue
```

---

## 🌐 5. Publishing (PyPI & GitHub)

### Publishing to PyPI via `uv`
```bash
uv publish --token <YOUR_PYPI_TOKEN>
```

### Publishing to GitHub Releases
1. Create and push a version tag:
   ```bash
   git tag -a v0.2.0 -m "Release v0.2.0"
   git push origin v0.2.0
   ```
2. Attach the generated binaries from `dist/` to your GitHub Release.