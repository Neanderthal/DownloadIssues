#!/usr/bin/env python3
"""
Compare MD5 hashes from md5s.list with files in changes/ folder
"""

import hashlib
from pathlib import Path

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
    """Parse md5s.list file and return dict of filename -> hash."""
    md5_dict = {}
    if not file_path.exists():
        return md5_dict

    content = file_path.read_text(encoding="utf-8")
    for line in content.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            hash_val, filename = parts
            # Clean up filename (remove ./ prefix)
            filename = filename.strip().lstrip("./")
            md5_dict[filename] = hash_val.strip()

    return md5_dict


def main():
    print("🔍 Comparing MD5 hashes...\n")

    # Parse md5s.list
    if not MD5_LIST_FILE.exists():
        print(f"❌ Error: {MD5_LIST_FILE} not found")
        return

    reference_hashes = parse_md5_list(MD5_LIST_FILE)
    print(f"📋 Loaded {len(reference_hashes)} reference hashes from {MD5_LIST_FILE}")
    print(f"   Sample entries:")
    for i, (filename, hash_val) in enumerate(list(reference_hashes.items())[:3]):
        print(f"      {filename}: {hash_val}")
    print()

    # Check changes directory
    if not CHANGES_DIR.exists():
        print(f"❌ Error: {CHANGES_DIR} not found")
        return

    change_files = list(CHANGES_DIR.glob("*.md"))
    if not change_files:
        print(f"⚠️  No .md files found in {CHANGES_DIR}")
        return

    print(f"📁 Found {len(change_files)} change file(s)\n")

    # Compute MD5 for each change file
    matches = []
    non_matches = []

    for file in sorted(change_files):
        file_md5 = compute_md5(file)
        print(f"📄 {file.name}")
        print(f"   MD5: {file_md5}")

        # Check if this hash exists in reference list
        found = False
        for ref_filename, ref_hash in reference_hashes.items():
            if ref_hash == file_md5:
                print(f"   ✅ MATCH: {ref_filename}")
                matches.append((file.name, ref_filename, file_md5))
                found = True
                break

        if not found:
            print(f"   ❌ NO MATCH in reference list")
            non_matches.append((file.name, file_md5))

        print()

    # Summary
    print("=" * 70)
    print("📊 Summary:\n")
    print(f"   Reference hashes: {len(reference_hashes)}")
    print(f"   Change files: {len(change_files)}")
    print(f"   Matches: {len(matches)}")
    print(f"   Non-matches: {len(non_matches)}")
    print()

    if matches:
        print("✅ Matched files:")
        for change_file, ref_file, hash_val in matches:
            print(f"   {change_file} ↔ {ref_file}")
            print(f"      {hash_val}")

    if non_matches:
        print(f"\n❌ Non-matched files ({len(non_matches)}):")
        for change_file, hash_val in non_matches[:5]:  # Show first 5
            print(f"   {change_file}: {hash_val}")
        if len(non_matches) > 5:
            print(f"   ... and {len(non_matches) - 5} more")


if __name__ == "__main__":
    main()
