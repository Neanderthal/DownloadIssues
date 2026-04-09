#!/usr/bin/env bash
set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <directory>"
    exit 1
fi

ROOT="$(realpath "$1")"

if [ ! -d "$ROOT" ]; then
    echo "Error: '$ROOT' is not a directory"
    exit 1
fi

echo "=== Removing ascui/static/ ==="
rm -rf "$ROOT/ascui/static"

echo "=== Removing __pycache__ directories and .pyc files ==="
find "$ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$ROOT" -type f -name "*.pyc" -delete 2>/dev/null || true

echo "=== Removing .docx and .xlsx files ==="
find "$ROOT" -type f \( -name "*.docx" -o -name "*.xlsx" \) -delete 2>/dev/null || true

echo "=== Removing dot directories (.git, .vscode, .venv, etc.) ==="
find "$ROOT" -maxdepth 1 -type d -name ".*" -exec rm -rf {} + 2>/dev/null || true

echo "Done."
