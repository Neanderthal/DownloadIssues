#!/usr/bin/env python3
"""
Push encrypted data to GitHub Issues.

Workflow:
  1. tar.gz -> GPG encrypt -> hex encode -> split into 62,464-char chunks
  2. Generate MD5 for each chunk + full archive
  3. Create issue with chunk[0] as body, label 'data-transfer'
  4. PATCH issue body with chunk[1], chunk[2], ... (delay between edits)
  5. Post metadata JSON as first comment
  6. Add 'complete' label

Usage:
    python push.py <file_or_folder> [-k KEY] [--issue N] [--dry-run] [--delay 2]
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(override=True)

from lib.config import (
    GITHUB_REPO, GPG_KEY, TRANSFER_LABEL, HEX_CHARS_PER_CHUNK,
)
from lib.github_api import (
    create_issue,
    update_issue_body,
    add_issue_comment,
    add_issue_labels,
)
from lib.crypto import full_encrypt_pipeline, generate_part_suffix
from lib.metadata import generate_metadata_comment, generate_issue_title


def main():
    parser = argparse.ArgumentParser(
        description="Push encrypted data to GitHub Issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input_path", type=str,
        help="File or folder to encrypt and push",
    )
    parser.add_argument(
        "-k", "--key", type=str, default=GPG_KEY,
        help=f"GPG key for encryption (default: {GPG_KEY})",
    )
    parser.add_argument(
        "--repo", type=str, default=None,
        help=f"GitHub repo (default: {GITHUB_REPO or '$GITHUB_REPO'})",
    )
    parser.add_argument(
        "--issue", type=int, default=None, metavar="N",
        help="Resume pushing to existing issue number",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Encrypt and save hex locally without API calls",
    )
    parser.add_argument(
        "--delay", type=float, default=2.0,
        help="Seconds between issue edits (default: 2.0)",
    )
    parser.add_argument(
        "-o", "--output", type=str, default=None,
        help="Output directory for dry-run hex files",
    )

    args = parser.parse_args()

    repo = args.repo or GITHUB_REPO
    if not repo and not args.dry_run:
        print("Error: GITHUB_REPO not configured.", file=sys.stderr)
        sys.exit(1)

    input_path = Path(args.input_path)
    if not input_path.exists():
        print(f"Error: '{input_path}' not found", file=sys.stderr)
        sys.exit(1)

    filename = input_path.name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Step 1: Encrypt pipeline
    print(f"Encrypting '{input_path}'...")
    print(f"  GPG key: {args.key}")
    print(f"  Chunk size: {HEX_CHARS_PER_CHUNK} hex chars")

    chunks, metadata = full_encrypt_pipeline(
        str(input_path), args.key, HEX_CHARS_PER_CHUNK
    )

    total_chars = sum(len(c) for c in chunks)
    print(f"  Generated {len(chunks)} chunk(s), {total_chars} total hex chars")
    print(f"  Archive MD5: {metadata['archive_md5']}")

    # Dry run: save locally and exit
    if args.dry_run:
        output_dir = Path(args.output) if args.output else Path(".")
        output_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"{filename}_{timestamp}"

        for i, chunk in enumerate(chunks):
            suffix = generate_part_suffix(i)
            hex_file = output_dir / f"{prefix}.tar.gz.gpg.{suffix}.hex"
            hex_file.write_text(chunk, encoding='utf-8')
            print(f"  Saved: {hex_file}")

        # Save metadata as manifest
        import json
        manifest = {
            "version": 1,
            "filename": filename,
            "timestamp": timestamp,
            "gpg_key": args.key,
            **metadata,
        }
        manifest_file = output_dir / f"{prefix}.manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(f"  Saved: {manifest_file}")
        print(f"\nDry run complete. Files saved to {output_dir.absolute()}")
        return

    # Step 2: Create or resume issue
    issue_url = None
    if args.issue:
        issue_number = args.issue
        print(f"\nResuming to existing issue #{issue_number}")
        start_chunk = 0  # User handles which chunk to start from
    else:
        title = generate_issue_title(filename, timestamp)
        print(f"\nCreating issue: {title}")

        issue_data = create_issue(
            repo, title, chunks[0], labels=[TRANSFER_LABEL]
        )
        issue_number = issue_data["number"]
        issue_url = issue_data["html_url"]
        print(f"  Created issue #{issue_number}: {issue_url}")
        print(f"  Chunk 0/{len(chunks)-1} (body) uploaded")
        start_chunk = 1

    # Step 3: Push remaining chunks as body edits
    for i in range(start_chunk, len(chunks)):
        if args.delay > 0 and i > start_chunk:
            print(f"  Waiting {args.delay}s...")
            time.sleep(args.delay)

        print(f"  Uploading chunk {i}/{len(chunks)-1} "
              f"({len(chunks[i])} chars)...")
        update_issue_body(repo, issue_number, chunks[i])

    # Step 4: Post metadata comment
    print("Posting metadata comment...")
    parts_meta = metadata["parts"]
    comment_body = generate_metadata_comment(
        filename=filename,
        timestamp=timestamp,
        gpg_key=args.key,
        total_parts=len(chunks),
        parts=parts_meta,
        archive_md5=metadata["archive_md5"],
        total_hex_chars=total_chars,
    )
    add_issue_comment(repo, issue_number, comment_body)

    # Step 5: Add complete label
    try:
        add_issue_labels(repo, issue_number, ["complete"])
    except Exception as e:
        print(f"Warning: Could not add 'complete' label: {e}", file=sys.stderr)

    print(f"\nDone! Issue #{issue_number} has {len(chunks)} chunk(s) + metadata")
    if issue_url:
        print(f"URL: {issue_url}")


if __name__ == "__main__":
    main()
