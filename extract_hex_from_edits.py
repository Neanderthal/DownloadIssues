#!/usr/bin/env python3
"""
Extract hex data from GitHub issue edit history and prepare for decryption.

This script reads edit history JSON files (created by download_issues.py)
and extracts hex data from the diff field of each edit, saving them as
.hex files ready to be processed by decrypt-restore.sh.

Usage:
    python extract_hex_from_edits.py <edit_history_file.json> [options]

Examples:
    python extract_hex_from_edits.py data/projects/issues/edit_history/0014-103-edits.json
    python extract_hex_from_edits.py data/projects/issues/edit_history/0014-103-edits.json --output extracted/
    python extract_hex_from_edits.py data/projects/issues/edit_history/0014-103-edits.json --edit-index 0
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


def clean_hex_data(text: str) -> str:
    """
    Extract and clean hex data from diff text.
    Removes any non-hex characters and whitespace.
    """
    # Remove common markdown formatting if present
    lines = text.split('\n')
    hex_lines = []

    for line in lines:
        # Skip empty lines
        if not line.strip():
            continue

        # Skip markdown headers, code blocks, and other formatting
        if line.strip().startswith('#'):
            continue
        if line.strip().startswith('```'):
            continue
        if line.strip().startswith('---'):
            continue
        if line.strip().startswith('*'):
            continue

        # Clean the line - keep only hex characters
        cleaned = ''.join(c for c in line if c in '0123456789abcdefABCDEF')

        if cleaned:
            hex_lines.append(cleaned)

    return '\n'.join(hex_lines)


def generate_part_suffix(index: int) -> str:
    """
    Generate part suffix in format: part_aa, part_ab, etc.
    Uses lowercase letters like the split command does.
    aa, ab, ac, ... az, ba, bb, bc, ... zz
    """
    # Convert index to base-26 using lowercase letters (like split command)
    first = index // 26
    second = index % 26
    return f"part_{chr(ord('a') + first)}{chr(ord('a') + second)}"


def extract_hex_from_edit_history(
    json_file: Path,
    output_dir: Path,
    edit_index: int = None,
    prefix: str = None,
    reverse_order: bool = True
) -> List[Path]:
    """
    Extract hex data from edit history JSON file.

    Args:
        json_file: Path to the edit history JSON file
        output_dir: Directory to save extracted .hex files
        edit_index: Optional - extract only specific edit by index (0-based)
        prefix: Optional custom prefix for output files
        reverse_order: Process edits oldest-first (default: True)
                      GitHub returns newest first, but split parts need oldest first

    Returns:
        List of created .hex file paths
    """
    # Load JSON file
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}", file=sys.stderr)
        return []

    issue_number = data.get('issue_number', 'unknown')
    title = data.get('title', '')
    edits = data.get('edits', [])

    if not edits:
        print("No edits found in the file.", file=sys.stderr)
        return []

    # Determine output prefix
    if not prefix:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"issue_{issue_number:04d}_{timestamp}"

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    created_files = []

    # Filter edits if specific index requested
    if edit_index is not None:
        if edit_index < 0 or edit_index >= len(edits):
            print(f"Error: Edit index {edit_index} out of range (0-{len(edits)-1})", file=sys.stderr)
            return []
        edits_to_process = [(edit_index, edits[edit_index])]
    else:
        # Optionally reverse the edits list to process oldest first
        # (GitHub returns newest first, but split parts need oldest first)
        if reverse_order:
            edits_to_process = list(enumerate(reversed(edits)))
        else:
            edits_to_process = list(enumerate(edits))

    total_edits = len(edits_to_process)

    for idx, (edit_idx, edit) in enumerate(edits_to_process):
        diff = edit.get('diff', '')

        if not diff:
            print(f"Skipping edit {edit_idx}: no diff data")
            continue

        # Clean and extract hex data
        hex_data = clean_hex_data(diff)

        if not hex_data:
            print(f"Skipping edit {edit_idx}: no hex data found after cleaning")
            continue

        # Generate filename
        if total_edits == 1:
            # Single edit - no part suffix
            filename = output_dir / f"{prefix}.tar.gz.gpg.hex"
        else:
            # Multiple edits - use part suffixes
            part_suffix = generate_part_suffix(idx)
            filename = output_dir / f"{prefix}.tar.gz.gpg.{part_suffix}.hex"

        # Save hex data
        try:
            filename.write_text(hex_data, encoding='utf-8')
            created_files.append(filename)

            # Get edit metadata
            created_at = edit.get('createdAt', 'unknown')
            editor = edit.get('editor', {}).get('login', 'unknown')

            print(f"✓ Saved edit {edit_idx} -> {filename.name}")
            print(f"  Created: {created_at}, Editor: {editor}")

        except Exception as e:
            print(f"Error saving {filename}: {e}", file=sys.stderr)

    return created_files


def main():
    parser = argparse.ArgumentParser(
        description="Extract hex data from GitHub issue edit history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract all edits from an issue
  python extract_hex_from_edits.py data/projects/issues/edit_history/0014-103-edits.json

  # Extract to specific directory
  python extract_hex_from_edits.py 0014-103-edits.json --output /tmp/extracted/

  # Extract only the first edit (index 0)
  python extract_hex_from_edits.py 0014-103-edits.json --edit-index 0

  # Use custom prefix for output files
  python extract_hex_from_edits.py 0014-103-edits.json --prefix mybackup
        """
    )

    parser.add_argument(
        'json_file',
        type=Path,
        help='Path to edit history JSON file'
    )

    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=Path('extracted'),
        help='Output directory for .hex files (default: ./extracted/)'
    )

    parser.add_argument(
        '-i', '--edit-index',
        type=int,
        help='Extract only specific edit by index (0-based)'
    )

    parser.add_argument(
        '-p', '--prefix',
        type=str,
        help='Custom prefix for output files (default: issue_NNNN_timestamp)'
    )

    parser.add_argument(
        '-l', '--list',
        action='store_true',
        help='List all edits without extracting'
    )

    parser.add_argument(
        '--no-reverse',
        action='store_true',
        help='Keep GitHub order (newest first) instead of reversing to oldest first'
    )

    args = parser.parse_args()

    # Validate input file exists
    if not args.json_file.exists():
        print(f"Error: File not found: {args.json_file}", file=sys.stderr)
        sys.exit(1)

    # List mode - just show edits
    if args.list:
        try:
            with open(args.json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            issue_number = data.get('issue_number', 'unknown')
            title = data.get('title', '')
            edits = data.get('edits', [])

            print(f"\nIssue #{issue_number}: {title}")
            print(f"Total edits: {len(edits)}\n")

            for idx, edit in enumerate(edits):
                created_at = edit.get('createdAt', 'unknown')
                editor = edit.get('editor', {}).get('login', 'unknown')
                diff_len = len(edit.get('diff', ''))

                print(f"  [{idx}] {created_at} by {editor} ({diff_len} chars)")

            sys.exit(0)

        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)

    # Extract mode
    print(f"\n📦 Extracting hex data from: {args.json_file.name}\n")

    created_files = extract_hex_from_edit_history(
        args.json_file,
        args.output,
        args.edit_index,
        args.prefix,
        reverse_order=not args.no_reverse
    )

    if created_files:
        print(f"\n✅ Extracted {len(created_files)} file(s) to: {args.output.absolute()}")
        print(f"\nTo decrypt and restore, run:")

        if len(created_files) == 1:
            # Single file
            basename = created_files[0].stem  # removes .hex
            print(f"  cd {args.output.absolute()}")
            print(f"  ../decrypt-restore.sh {basename}")
        else:
            # Multiple parts
            basename = created_files[0].stem.replace('.tar.gz.gpg.part_aa', '')
            print(f"  cd {args.output.absolute()}")
            print(f"  ../decrypt-restore.sh {basename}")
    else:
        print("\n⚠️  No files were extracted", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
