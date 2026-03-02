#!/usr/bin/env python3
"""
Rename change files to match md5s.list naming convention
"""

import hashlib
from pathlib import Path
from collections import defaultdict

# Configuration
MD5_LIST_FILE = Path("data/md5.txt")
CHANGES_DIR = Path("data/projects/issues/changes")


def compute_md5(file_path: Path) -> str:
    """Compute MD5 hash of a file."""
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


def parse_md5_list(file_path: Path) -> dict:
    """Parse md5s.list file and return dict of hash -> filename."""
    hash_to_filename = {}
    if not file_path.exists():
        return hash_to_filename

    content = file_path.read_text(encoding="utf-8")
    for line in content.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            hash_val, filename = parts
            # Clean up filename (remove ./ prefix)
            filename = filename.strip().lstrip("./")
            hash_to_filename[hash_val.strip()] = filename

    return hash_to_filename


def main():
    print("🔄 Renaming change files...\n")

    # Parse md5s.list
    if not MD5_LIST_FILE.exists():
        print(f"❌ Error: {MD5_LIST_FILE} not found")
        return

    hash_to_filename = parse_md5_list(MD5_LIST_FILE)
    print(f"📋 Loaded {len(hash_to_filename)} reference hashes from {MD5_LIST_FILE}\n")

    # Check changes directory
    if not CHANGES_DIR.exists():
        print(f"❌ Error: {CHANGES_DIR} not found")
        return

    change_files = list(CHANGES_DIR.glob("*.md"))
    if not change_files:
        print(f"⚠️  No .md files found in {CHANGES_DIR}")
        return

    print(f"📁 Found {len(change_files)} change file(s)\n")

    # Track renamed files and duplicates
    renamed_count = 0
    skipped_count = 0
    duplicate_count = 0

    # Track which target filenames are already used
    used_names = defaultdict(list)

    for file in sorted(change_files):
        file_md5 = compute_md5(file)

        # Find matching filename from md5s.list
        target_name = hash_to_filename.get(file_md5)

        if target_name:
            # Check if this is a duplicate (same hash already renamed)
            if target_name in used_names:
                # This is a duplicate - add a counter
                duplicate_count += 1
                base_name = Path(target_name).stem
                extension = Path(target_name).suffix
                new_name = f"{base_name}.dup{duplicate_count}{extension}"
                new_path = CHANGES_DIR / new_name
                print(f"🔄 {file.name}")
                print(f"   → {new_name} (duplicate of {target_name})")
                file.rename(new_path)
                used_names[target_name].append(new_path)
                renamed_count += 1
            else:
                # First occurrence - use the original name
                new_path = CHANGES_DIR / target_name
                print(f"✅ {file.name}")
                print(f"   → {target_name}")
                file.rename(new_path)
                used_names[target_name].append(new_path)
                renamed_count += 1
        else:
            print(f"⚠️  {file.name}")
            print(f"   No match found (MD5: {file_md5})")
            skipped_count += 1

    # Summary
    print("\n" + "=" * 70)
    print("📊 Summary:\n")
    print(f"   Total files: {len(change_files)}")
    print(f"   Renamed: {renamed_count}")
    print(f"   Duplicates handled: {duplicate_count}")
    print(f"   Skipped (no match): {skipped_count}")

    if renamed_count > 0:
        print(f"\n✅ Successfully renamed {renamed_count} file(s)")

    if duplicate_count > 0:
        print(f"\nℹ️  Duplicate files were renamed with .dup suffix")


if __name__ == "__main__":
    main()
