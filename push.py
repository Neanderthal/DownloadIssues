#!/usr/bin/env python3
"""
Push encrypted data to a git hosting provider (GitHub or GitFlic).

Workflow (GitHub):
  1. tar.gz -> GPG encrypt -> hex encode -> split into chunks
  2. Create issue with chunk[0] as body, label 'data-transfer'
  3. PATCH issue body with chunk[1..N] (creates edit history)
  4. Post metadata JSON as first comment
  5. Add 'complete' label

Workflow (GitFlic):
  1. tar.gz -> GPG encrypt -> hex encode -> split into chunks
  2. Create issue with metadata JSON as body
  3. Post chunk[0..N] as sequential comments

Usage:
    python push.py <file_or_folder> [-k KEY] [--provider P] [--dry-run]
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(override=True)

from lib.config import (
    PROVIDER, GPG_KEY, TRANSFER_LABEL, HEX_CHARS_PER_CHUNK,
    get_repo_for_provider,
)
from lib.provider import get_provider
from lib.crypto import full_encrypt_pipeline, generate_part_suffix
from lib.metadata import generate_metadata_comment, generate_issue_title


def main():
    parser = argparse.ArgumentParser(
        description="Push encrypted data to git hosting issues",
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
        "--provider", type=str, default=None,
        help=f"Provider: github or gitflic (default: {PROVIDER})",
    )
    parser.add_argument(
        "--repo", type=str, default=None,
        help="Override repo/project from env",
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
        help="Seconds between uploads (default: 2.0)",
    )
    parser.add_argument(
        "-o", "--output", type=str, default=None,
        help="Output directory for dry-run hex files",
    )

    args = parser.parse_args()

    provider_name = args.provider or PROVIDER
    provider = get_provider(provider_name)
    repo = get_repo_for_provider(provider_name, args.repo)

    if not repo and not args.dry_run:
        print(f"Error: repo/project not configured for {provider_name}.",
              file=sys.stderr)
        sys.exit(1)

    input_path = Path(args.input_path)
    if not input_path.exists():
        print(f"Error: '{input_path}' not found", file=sys.stderr)
        sys.exit(1)

    filename = input_path.name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Step 1: Encrypt pipeline
    print(f"Encrypting '{input_path}'...")
    print(f"  Provider: {provider_name}")
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
        _dry_run(chunks, metadata, filename, timestamp, args)
        return

    # Build metadata comment body
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

    if provider.chunks_in_comments:
        _push_gitflic(provider, repo, chunks, comment_body,
                      filename, timestamp, args)
    else:
        _push_github(provider, repo, chunks, comment_body,
                     filename, timestamp, args)


def _push_github(provider, repo, chunks, metadata_body, filename, timestamp, args):
    """GitHub flow: body edits for chunks, comment for metadata."""
    issue_url = None

    if args.issue:
        issue_number = args.issue
        print(f"\nResuming to existing issue #{issue_number}")
        start_chunk = 0
    else:
        title = generate_issue_title(filename, timestamp)
        print(f"\nCreating issue: {title}")
        issue_data = provider.create_issue(
            repo, title, chunks[0], labels=[TRANSFER_LABEL])
        issue_number = issue_data["number"]
        issue_url = issue_data.get("html_url")
        print(f"  Created issue #{issue_number}: {issue_url}")
        print(f"  Chunk 0/{len(chunks)-1} (body) uploaded")
        start_chunk = 1

    for i in range(start_chunk, len(chunks)):
        if args.delay > 0 and i > start_chunk:
            print(f"  Waiting {args.delay}s...")
            time.sleep(args.delay)
        print(f"  Uploading chunk {i}/{len(chunks)-1} ({len(chunks[i])} chars)...")
        provider.update_issue_body(repo, issue_number, chunks[i])

    print("Posting metadata comment...")
    provider.add_issue_comment(repo, issue_number, metadata_body)

    try:
        provider.add_issue_labels(repo, issue_number, ["complete"])
    except Exception as e:
        print(f"Warning: Could not add 'complete' label: {e}", file=sys.stderr)

    print(f"\nDone! Issue #{issue_number} has {len(chunks)} chunk(s) + metadata")
    if issue_url:
        print(f"URL: {issue_url}")


def _push_gitflic(provider, repo, chunks, metadata_body, filename, timestamp, args):
    """GitFlic flow: metadata in body, chunks as comments."""
    issue_url = None

    if args.issue:
        issue_number = args.issue
        print(f"\nResuming to existing issue #{issue_number}")
    else:
        title = generate_issue_title(filename, timestamp)
        print(f"\nCreating issue: {title}")
        issue_data = provider.create_issue(repo, title, metadata_body)
        issue_number = issue_data["number"]
        issue_url = issue_data.get("html_url")
        print(f"  Created issue #{issue_number}: {issue_url}")
        print(f"  Metadata stored in issue body")

    for i, chunk in enumerate(chunks):
        if args.delay > 0 and i > 0:
            print(f"  Waiting {args.delay}s...")
            time.sleep(args.delay)
        print(f"  Uploading chunk {i}/{len(chunks)-1} as comment "
              f"({len(chunk)} chars)...")
        provider.add_issue_comment(repo, issue_number, chunk)

    print(f"\nDone! Issue #{issue_number} has metadata + {len(chunks)} chunk comment(s)")
    if issue_url:
        print(f"URL: {issue_url}")


def _dry_run(chunks, metadata, filename, timestamp, args):
    """Save chunks locally without API calls."""
    import json

    output_dir = Path(args.output) if args.output else Path(".")
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{filename}_{timestamp}"

    for i, chunk in enumerate(chunks):
        suffix = generate_part_suffix(i)
        hex_file = output_dir / f"{prefix}.tar.gz.gpg.{suffix}.hex"
        hex_file.write_text(chunk, encoding='utf-8')
        print(f"  Saved: {hex_file}")

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


if __name__ == "__main__":
    main()
