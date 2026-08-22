#!/usr/bin/env bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
cd "$PROJECT_ROOT"

echo "🔨 Building CodeWrap package in: $PROJECT_ROOT"
uv build

echo "🚀 Installing CodeWrap globally in editable mode..."
uv tool install --editable . --force

echo "✅ Success! CodeWrap is ready to use:"
codewrap -h