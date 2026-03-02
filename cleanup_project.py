#!/usr/bin/env python3
"""
Script to clean up non-essential files from the project.
Removes static files, compiled Python, templates, and other non-core files.
Keeps only Python source and essential configuration files.
"""

import os
import shutil
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent / "ascui"

# Directories to completely remove
DIRS_TO_REMOVE = [
    "static",
    "templates",
    "__pycache__",
]

# File extensions to remove
EXTENSIONS_TO_REMOVE = [
    ".pyc",
    ".pyo",
    ".html",
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".ttf",
    ".woff",
    ".woff2",
    ".eot",
    ".docx",
    ".doc",
    ".pem",
    ".xml",
    ".ps1",
    ".sh",
    ".md",
    ".conf",
]

# Files to keep (exact matches in any directory)
FILES_TO_KEEP = [
    "manage.py",
    "pyproject.toml",
    "poetry.lock",
    "README.md",
    "CLAUDE.md",
    "requirements.txt",
    ".env.example",
    ".gitignore",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose-test.yml",
    "docker-compose-rabbitmq.yml",
    "docker-compose-redis.yml",
]

# Directories to keep entirely (won't be scanned for cleanup)
DIRS_TO_KEEP = [
    ".git",
    ".venv",
    "venv",
    "env",
]


def should_remove_file(file_path: Path) -> bool:
    """Determine if a file should be removed."""
    # Keep files in the keep list
    if file_path.name in FILES_TO_KEEP:
        return False

    # Keep Python source files
    if file_path.suffix == ".py":
        return False

    # Keep JSON config files
    if file_path.suffix == ".json":
        return False

    # Remove files with extensions in removal list
    if file_path.suffix in EXTENSIONS_TO_REMOVE:
        return True

    # Remove remaining files (non-Python, non-config)
    return True


def should_remove_dir(dir_path: Path) -> bool:
    """Determine if a directory should be completely removed."""
    dir_name = dir_path.name

    # Keep protected directories
    if dir_name in DIRS_TO_KEEP:
        return False

    # Remove directories in removal list
    if dir_name in DIRS_TO_REMOVE:
        return True

    return False


def cleanup_project(dry_run=True):
    """
    Clean up the project directory.

    Args:
        dry_run: If True, only print what would be removed without actually removing
    """
    if not BASE_DIR.exists():
        print(f"Base directory not found: {BASE_DIR}")
        return

    removed_files = []
    removed_dirs = []
    kept_files = []

    # Walk through the directory tree
    for root, dirs, files in os.walk(BASE_DIR, topdown=False):
        root_path = Path(root)

        # Skip if in a protected directory
        if any(keep_dir in root_path.parts for keep_dir in DIRS_TO_KEEP):
            continue

        # Remove files
        for file in files:
            file_path = root_path / file

            if should_remove_file(file_path):
                removed_files.append(file_path)
                if not dry_run:
                    try:
                        file_path.unlink()
                        print(f"Removed file: {file_path.relative_to(BASE_DIR.parent)}")
                    except Exception as e:
                        print(f"Error removing {file_path}: {e}")
                else:
                    print(f"Would remove file: {file_path.relative_to(BASE_DIR.parent)}")
            else:
                kept_files.append(file_path)

        # Remove directories
        for dir_name in dirs[:]:  # Create a copy to modify during iteration
            dir_path = root_path / dir_name

            if should_remove_dir(dir_path):
                removed_dirs.append(dir_path)
                if not dry_run:
                    try:
                        shutil.rmtree(dir_path)
                        print(f"Removed directory: {dir_path.relative_to(BASE_DIR.parent)}")
                        dirs.remove(dir_name)  # Don't descend into removed dir
                    except Exception as e:
                        print(f"Error removing {dir_path}: {e}")
                else:
                    print(f"Would remove directory: {dir_path.relative_to(BASE_DIR.parent)}")
                    dirs.remove(dir_name)  # Don't descend into would-be-removed dir

    # Also clean up root level non-Python files
    root_files_to_check = [
        "tree.txt",
        "bck.combined.tar.gz",
        "combined.gpg",
        "combined_all.hex",
        "decrypted_file.tar.gz",
        "decrypted_reassembled.tar.gz",
        "key.asc",
        "md5s.list",
        "tree.txt.hex_20251224_214806.tar.gz.gpg",
    ]

    for file_name in root_files_to_check:
        file_path = BASE_DIR.parent / file_name
        if file_path.exists():
            removed_files.append(file_path)
            if not dry_run:
                try:
                    file_path.unlink()
                    print(f"Removed root file: {file_name}")
                except Exception as e:
                    print(f"Error removing {file_path}: {e}")
            else:
                print(f"Would remove root file: {file_name}")

    # Print summary
    print("\n" + "="*80)
    print("CLEANUP SUMMARY")
    print("="*80)
    print(f"Files to remove: {len(removed_files)}")
    print(f"Directories to remove: {len(removed_dirs)}")
    print(f"Files to keep: {len(kept_files)}")

    if dry_run:
        print("\nThis was a DRY RUN. No files were actually removed.")
        print("Run with --execute to actually remove files.")
    else:
        print("\nCleanup completed!")


if __name__ == "__main__":
    import sys

    # Check for execute flag
    execute = "--execute" in sys.argv

    if execute:
        confirm = input("This will permanently delete files. Are you sure? (yes/no): ")
        if confirm.lower() != "yes":
            print("Cleanup cancelled.")
            sys.exit(0)

    cleanup_project(dry_run=not execute)
