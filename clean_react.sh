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

echo "Cleaning React/Node.js project: $ROOT"
echo

# Dependencies
echo "=== Removing node_modules ==="
find "$ROOT" -type d -name "node_modules" -prune -exec rm -rf {} + 2>/dev/null || true

# Build outputs
echo "=== Removing build outputs ==="
for dir in build dist .next out .nuxt .output .turbo storybook-static; do
    find "$ROOT" -type d -name "$dir" -prune -exec rm -rf {} + 2>/dev/null || true
done

# Lock files
echo "=== Removing lock files ==="
find "$ROOT" -maxdepth 2 -type f \( \
    -name "package-lock.json" -o \
    -name "yarn.lock" -o \
    -name "pnpm-lock.yaml" -o \
    -name "bun.lockb" \
\) -delete 2>/dev/null || true

# Caches
echo "=== Removing caches ==="
for dir in .cache .parcel-cache; do
    find "$ROOT" -type d -name "$dir" -prune -exec rm -rf {} + 2>/dev/null || true
done
find "$ROOT" -type f \( -name "*.tsbuildinfo" -o -name ".eslintcache" -o -name ".stylelintcache" \) -delete 2>/dev/null || true

# Test / coverage
echo "=== Removing coverage ==="
for dir in coverage .nyc_output; do
    find "$ROOT" -type d -name "$dir" -prune -exec rm -rf {} + 2>/dev/null || true
done

# Logs
echo "=== Removing logs ==="
find "$ROOT" -type f -name "*.log" -delete 2>/dev/null || true

# Dot directories (git, IDE, etc.)
echo "=== Removing dot directories ==="
find "$ROOT" -maxdepth 1 -type d -name ".*" -exec rm -rf {} + 2>/dev/null || true

# Env files
echo "=== Removing .env files ==="
find "$ROOT" -type f -name ".env*" -delete 2>/dev/null || true

# Source maps
echo "=== Removing source maps ==="
find "$ROOT" -type f -name "*.map" -delete 2>/dev/null || true

# OS junk
echo "=== Removing OS artifacts ==="
find "$ROOT" -type f \( -name ".DS_Store" -o -name "Thumbs.db" \) -delete 2>/dev/null || true

echo
echo "Done."
