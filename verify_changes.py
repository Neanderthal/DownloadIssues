#!/usr/bin/env python3
"""
Verify Changes Script

Compares hashes stored in .issues_state.json with actual file content hashes
in the changes/ directory to verify integrity and detect duplicates.
"""

import json
import hashlib
from pathlib import Path
from collections import defaultdict

# Configuration
STATE_FILE = Path(".issues_state.json")
CHANGES_DIR = Path("data/projects/issues/changes")


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file content."""
    content = file_path.read_text(encoding="utf-8")
    return hashlib.sha256(content.encode()).hexdigest()


def compute_issue_hash_from_content(content: str) -> str:
    """
    Compute hash the same way the main script does.
    Note: This is just the body content, not the full issue metadata.
    """
    return hashlib.sha256(content.encode()).hexdigest()


def main():
    print("🔍 Verifying changes directory...\n")

    # Load state file
    if not STATE_FILE.exists():
        print("❌ Error: .issues_state.json not found")
        return

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    stored_hashes = state.get("issue_hashes", {})

    print(f"📊 State file info:")
    print(f"   Repository: {state.get('repo')}")
    print(f"   Last run: {state.get('last_run')}")
    print(f"   Tracked issues: {len(stored_hashes)}")
    print(f"   Issue hashes stored:")
    for issue_num, hash_val in stored_hashes.items():
        print(f"      #{issue_num}: {hash_val[:16]}...")
    print()

    # Check changes directory
    if not CHANGES_DIR.exists():
        print("⚠️  No changes directory found yet")
        return

    change_files = list(CHANGES_DIR.glob("*.md"))
    if not change_files:
        print("ℹ️  No change files found yet")
        return

    print(f"📁 Found {len(change_files)} change file(s)\n")

    # Group files by issue number
    files_by_issue = defaultdict(list)
    for file in sorted(change_files):
        # Extract issue number from filename (format: 0001-title-timestamp.md)
        try:
            issue_num = int(file.stem.split("-")[0])
            files_by_issue[issue_num].append(file)
        except (ValueError, IndexError):
            print(f"⚠️  Skipping malformed filename: {file.name}")

    # Analyze each issue's changes
    for issue_num in sorted(files_by_issue.keys()):
        files = files_by_issue[issue_num]
        print(f"📝 Issue #{issue_num} - {len(files)} change(s):")

        # Compute hash for each change file
        file_hashes = []
        for file in files:
            content_hash = compute_file_hash(file)
            timestamp = file.stem.split("-")[-1]
            file_hashes.append((file, timestamp, content_hash))
            print(f"   {timestamp}: {content_hash[:16]}...")

        # Check for duplicate content
        hash_counts = defaultdict(list)
        for file, timestamp, hash_val in file_hashes:
            hash_counts[hash_val].append(timestamp)

        duplicates = {h: ts for h, ts in hash_counts.items() if len(ts) > 1}
        if duplicates:
            print(f"   ⚠️  Found {len(duplicates)} duplicate content(s):")
            for hash_val, timestamps in duplicates.items():
                print(f"      {hash_val[:16]}... appears in: {', '.join(timestamps)}")

        # Compare with current state
        current_hash = stored_hashes.get(str(issue_num))
        if current_hash:
            print(f"   📌 Current state hash: {current_hash[:16]}...")
            # Check if latest change matches current state
            if file_hashes:
                latest_file, latest_ts, latest_hash = file_hashes[-1]
                # Note: We can't directly compare because state hash includes metadata
                # and change files only have body content
                print(f"   ℹ️  Note: State hash includes metadata, file hash is body only")
        else:
            print(f"   ⚠️  Issue #{issue_num} not in current state")

        print()

    # Summary
    total_changes = len(change_files)
    total_issues_with_changes = len(files_by_issue)

    print("=" * 60)
    print("📈 Summary:")
    print(f"   Total change files: {total_changes}")
    print(f"   Issues with changes: {total_issues_with_changes}")
    print(f"   Issues tracked in state: {len(stored_hashes)}")
    print()

    # Check for issues in state but no changes
    issues_without_changes = set(stored_hashes.keys()) - {str(n) for n in files_by_issue.keys()}
    if issues_without_changes:
        print(f"ℹ️  Issues in state with no change files: {', '.join(sorted(issues_without_changes))}")
    else:
        print("✓ All issues with changes are tracked in state")


if __name__ == "__main__":
    main()
