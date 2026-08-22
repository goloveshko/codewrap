#!/usr/bin/env bash
set -e

echo "🔨 Building CodeWrap package..."
uv build

echo "🚀 Installing CodeWrap globally in editable mode..."
uv tool install --editable . --force

echo "✅ Success! CodeWrap is ready to use:"
codewrap -h