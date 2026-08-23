#!/usr/bin/env bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
cd "$PROJECT_ROOT"

echo "🔍 1/4. Running Ruff Linter..."
uv run ruff check .

echo "🎨 2/4. Checking Code Formatting..."
uv run ruff format --check .

echo "🧪 3/4. Running Mypy Type Checker..."
uv run mypy src

echo "📦 4/4. Testing Package Build..."
uv build

echo -e "\n✅ All Quality Checks Passed Successfully! Ready for Release!"