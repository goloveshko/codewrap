#!/usr/bin/env bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
cd "$PROJECT_ROOT"

echo "🔍 1/5. Running Ruff Linter..."
uv run ruff check .

echo "🎨 2/5. Checking Code Formatting..."
uv run ruff format --check .

echo "🧪 3/5. Running Mypy Type Checker..."
uv run mypy src

echo "🚦 4/5. Running Pytest Suite..."
uv run pytest

echo "📦 5/5. Testing Package Build..."
uv build

echo -e "\n✅ All Quality Checks & Tests Passed Successfully! Ready for Release!"