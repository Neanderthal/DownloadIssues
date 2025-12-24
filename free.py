#!/usr/bin/env python3
"""
Script to clean up non-essential files from a directory.
Removes static files, compiled Python, templates, and other non-core files.
Keeps only Python source and essential configuration files needed to rebuild
the development/test environment from scratch.

What gets removed:
- Static files (HTML, CSS, JS, images, fonts)
- Compiled Python files (.pyc, .pyo)
- Documentation files (unless in FILES_TO_KEEP)
- Specific directories (static, templates, __pycache__)
- Empty directories after cleanup
- Write-protected files (permissions changed before deletion)

What gets kept:
- Python source files (.py)
- Configuration files (.json, pyproject.toml, requirements.txt, etc.)
- Essential project files (README.md, .env.example, .gitignore, etc.)

Usage:
    python free.py [directory]              # Dry-run mode (default)
    python free.py [directory] --execute    # Actually remove files
    python free.py --help                   # Show help
"""

import os
import shutil
import sys
import stat
from pathlib import Path

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
DIRS_TO_KEEP = []


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

    # Remove directories in removal list (static, templates, __pycache__, etc.)
    if dir_name in DIRS_TO_REMOVE:
        return True

    # Keep other directories (they may contain Python code)
    return False


def handle_remove_readonly(func, path, exc_info):
    """
    Error handler for shutil.rmtree to handle read-only files.
    Removes the read-only flag and retries the operation.
    """
    # Change the file to be writable
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    # Retry the operation
    func(path)


def cleanup_project(target_dir, dry_run=True):
    """
    Clean up the project directory.

    Args:
        target_dir: Path to the directory to clean up
        dry_run: If True, only print what would be removed without actually removing
    """
    base_dir = Path(target_dir).resolve()
    if not base_dir.exists():
        print(f"Base directory not found: {base_dir}")
        return

    if not base_dir.is_dir():
        print(f"Target is not a directory: {base_dir}")
        return

    removed_files = []
    removed_dirs = []
    kept_files = []

    print(f"Cleaning directory: {base_dir}\n")

    # Walk through the directory tree
    for root, dirs, files in os.walk(base_dir, topdown=False):
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
                        print(f"Removed file: {file_path.relative_to(base_dir)}")
                    except PermissionError:
                        # Handle write-protected files
                        try:
                            os.chmod(file_path, stat.S_IWRITE | stat.S_IREAD)
                            file_path.unlink()
                            print(f"Removed protected file: {file_path.relative_to(base_dir)}")
                        except Exception as e:
                            print(f"Error removing {file_path}: {e}")
                    except Exception as e:
                        print(f"Error removing {file_path}: {e}")
                else:
                    print(
                        f"Would remove file: {file_path.relative_to(base_dir)}"
                    )
            else:
                kept_files.append(file_path)

        # Remove directories
        for dir_name in dirs[:]:  # Create a copy to modify during iteration
            dir_path = root_path / dir_name

            if should_remove_dir(dir_path):
                removed_dirs.append(dir_path)
                if not dry_run:
                    try:
                        shutil.rmtree(dir_path, onerror=handle_remove_readonly)
                        print(
                            f"Removed directory: {dir_path.relative_to(base_dir)}"
                        )
                        dirs.remove(dir_name)  # Don't descend into removed dir
                    except Exception as e:
                        print(f"Error removing {dir_path}: {e}")
                else:
                    print(
                        f"Would remove directory: {dir_path.relative_to(base_dir)}"
                    )
                    dirs.remove(dir_name)  # Don't descend into would-be-removed dir

    # Remove empty directories
    if not dry_run:
        for root, dirs, files in os.walk(base_dir, topdown=False):
            root_path = Path(root)

            # Skip if in a protected directory
            if any(keep_dir in root_path.parts for keep_dir in DIRS_TO_KEEP):
                continue

            # Skip the base directory itself
            if root_path == base_dir:
                continue

            # Remove if directory is empty
            try:
                if not any(root_path.iterdir()):
                    root_path.rmdir()
                    removed_dirs.append(root_path)
                    print(f"Removed empty directory: {root_path.relative_to(base_dir)}")
            except Exception:
                pass  # Directory not empty or other error, skip

    # Print summary
    print("\n" + "=" * 80)
    print("CLEANUP SUMMARY")
    print("=" * 80)
    print(f"Files to remove: {len(removed_files)}")
    print(f"Directories to remove: {len(removed_dirs)}")
    print(f"Files to keep: {len(kept_files)}")

    if dry_run:
        print("\nThis was a DRY RUN. No files were actually removed.")
        print("Run with --execute to actually remove files.")
    else:
        print("\nCleanup completed!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Clean up non-essential files from a project directory."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default="ascui",
        help="Directory to clean up (default: ascui)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually remove files (default is dry-run)",
    )

    args = parser.parse_args()

    if args.execute:
        confirm = input("This will permanently delete files. Are you sure? (yes/no): ")
        if confirm.lower() != "yes":
            print("Cleanup cancelled.")
            sys.exit(0)

    cleanup_project(args.directory, dry_run=not args.execute)
