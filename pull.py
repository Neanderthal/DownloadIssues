#!/usr/bin/env python3
"""
Pull data from GitHub Issues: download + verify + decrypt in one step.

Replaces the manual sequence:
  download_issues.py -> extract_hex_from_edits.py -> decrypt-restore.sh -> compare_md5.py

Usage:
    python pull.py list                     # show available data-transfer issues
    python pull.py issue <N> [-o DIR]       # pull + verify + decrypt one issue
    python pull.py all [-o DIR]             # pull all [DT] issues
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from lib.config import GITHUB_REPO, TRANSFER_LABEL, TITLE_PREFIX, EXTRACTED_DIR
from lib.github_api import (
    fetch_open_issues,
    fetch_issue_edit_history,
    get_issue_comments,
    add_issue_labels,
)
from lib.crypto import clean_hex_data, full_decrypt_pipeline, generate_part_suffix
from lib.integrity import verify_part_md5s
from lib.metadata import find_metadata_in_comments


def cmd_list(args):
    """List available data-transfer issues."""
    repo = args.repo or GITHUB_REPO
    if not repo:
        print("Error: GITHUB_REPO not configured.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching issues from {repo}...")

    # Fetch all open issues (filter by label if possible, but also check title)
    issues = fetch_open_issues(repo)

    dt_issues = []
    for issue in issues:
        title = issue.get("title", "")
        labels = [l["name"] for l in issue.get("labels", [])]
        if title.startswith(TITLE_PREFIX) or TRANSFER_LABEL in labels:
            dt_issues.append(issue)

    if not dt_issues:
        # Also show all issues as fallback info
        print(f"\nNo issues with '{TITLE_PREFIX}' prefix or "
              f"'{TRANSFER_LABEL}' label found.")
        if issues:
            print(f"\nAll {len(issues)} open issue(s):")
            for issue in issues:
                labels = ", ".join(l["name"] for l in issue.get("labels", []))
                label_str = f" [{labels}]" if labels else ""
                print(f"  #{issue['number']:4d}  {issue['title']}{label_str}")
        return

    print(f"\nFound {len(dt_issues)} data-transfer issue(s):\n")
    for issue in dt_issues:
        number = issue["number"]
        title = issue["title"]
        labels = ", ".join(l["name"] for l in issue.get("labels", []))
        updated = issue.get("updated_at", "")[:10]
        body_len = len(issue.get("body") or "")
        label_str = f" [{labels}]" if labels else ""
        print(f"  #{number:4d}  {title}{label_str}")
        print(f"         updated: {updated}  body: {body_len} chars")


def extract_chunks_from_issue(repo, issue_number, verbose=True):
    """
    Fetch edit history and extract hex chunks from an issue.
    Data format: reversed(edits) + current_body = full hex data.

    Returns list of hex chunk strings (cleaned).
    """
    if verbose:
        print(f"Fetching edit history for issue #{issue_number}...")

    edits, current_body = fetch_issue_edit_history(repo, issue_number)

    if verbose:
        print(f"  Found {len(edits)} edit(s), body: {len(current_body or '')} chars")

    # edits are returned newest-first by GitHub; reverse to get oldest-first.
    # The newest edit (edits[0]) contains the current version of the body,
    # so we only append the body separately when there are no edits.
    chunks = []

    if edits:
        for edit in reversed(edits):
            diff = edit.get("diff", "")
            if diff:
                hex_data = clean_hex_data(diff)
                if hex_data:
                    chunks.append(hex_data)
    elif current_body:
        # No edits: single-chunk issue, body is the only data
        body_hex = clean_hex_data(current_body)
        if body_hex:
            chunks.append(body_hex)

    if verbose:
        total_chars = sum(len(c) for c in chunks)
        print(f"  Extracted {len(chunks)} chunk(s), {total_chars} total hex chars")

    return chunks


def cmd_issue(args):
    """Pull, verify, and decrypt a single issue."""
    repo = args.repo or GITHUB_REPO
    if not repo:
        print("Error: GITHUB_REPO not configured.", file=sys.stderr)
        sys.exit(1)

    issue_number = args.number
    output_dir = args.output or EXTRACTED_DIR
    output_dir = Path(output_dir)

    print(f"Pulling issue #{issue_number} from {repo}\n")

    # Step 1: Check for metadata in comments
    metadata = None
    try:
        comments = get_issue_comments(repo, issue_number)
        metadata = find_metadata_in_comments(comments)
        if metadata:
            print(f"Found metadata: {metadata.get('filename', '?')} "
                  f"({metadata.get('total_parts', '?')} parts, "
                  f"archive MD5: {metadata.get('archive_md5', '?')[:12]}...)")
        else:
            print("No metadata comment found (legacy issue)")
    except Exception as e:
        print(f"Warning: Could not fetch comments: {e}", file=sys.stderr)

    # Step 2: Extract hex chunks
    chunks = extract_chunks_from_issue(repo, issue_number)

    if not chunks:
        print("\nNo hex data found in this issue.", file=sys.stderr)
        sys.exit(1)

    # Step 3: Verify MD5 if metadata available
    verified = False
    if metadata and "parts" in metadata:
        print("\nVerifying MD5 checksums...")
        ok, errors = verify_part_md5s(chunks, metadata["parts"])
        if ok:
            print("  All checksums match!")
            verified = True
        else:
            print("  MD5 verification FAILED:", file=sys.stderr)
            for err in errors:
                print(f"    {err}", file=sys.stderr)
            if not args.force:
                print("\nUse --force to proceed despite verification failure.",
                      file=sys.stderr)
                sys.exit(1)
            print("  Proceeding anyway (--force)")

    # Step 4: Decrypt or save as legacy
    if metadata:
        filename = metadata.get("filename", f"issue_{issue_number}")
        timestamp = metadata.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
    else:
        filename = f"issue_{issue_number:04d}"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    issue_output = output_dir / f"{filename}_{timestamp}"

    if args.hex_only:
        # Save hex files without decrypting
        save_hex_chunks(chunks, issue_output, filename, timestamp)
        return

    try:
        print(f"\nDecrypting to {issue_output}/...")
        full_decrypt_pipeline(chunks, str(issue_output))
        print(f"Extracted to: {issue_output.absolute()}")

        # Step 5: Add verified label if verification passed
        if verified and not args.no_label:
            try:
                add_issue_labels(repo, issue_number, ["verified"])
                print("Added 'verified' label to issue")
            except Exception as e:
                print(f"Warning: Could not add label: {e}", file=sys.stderr)

    except Exception as e:
        print(f"\nDecryption failed: {e}", file=sys.stderr)
        print("Saving hex files for manual decryption...")
        save_hex_chunks(chunks, output_dir, filename, timestamp)
        sys.exit(1)


def save_hex_chunks(chunks, output_dir, filename, timestamp):
    """Save hex chunks to individual files (legacy fallback)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{filename}_{timestamp}"

    if len(chunks) == 1:
        hex_file = output_dir / f"{prefix}.tar.gz.gpg.hex"
        hex_file.write_text(chunks[0], encoding='utf-8')
        print(f"  Saved: {hex_file}")
    else:
        for i, chunk in enumerate(chunks):
            suffix = generate_part_suffix(i)
            hex_file = output_dir / f"{prefix}.tar.gz.gpg.{suffix}.hex"
            hex_file.write_text(chunk, encoding='utf-8')
            print(f"  Saved: {hex_file}")

    print(f"\nTo decrypt manually:")
    print(f"  cd {output_dir.absolute()}")
    print(f"  ../decrypt-restore.sh {prefix}")


def cmd_all(args):
    """Pull all data-transfer issues."""
    repo = args.repo or GITHUB_REPO
    if not repo:
        print("Error: GITHUB_REPO not configured.", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output or EXTRACTED_DIR

    issues = fetch_open_issues(repo)
    dt_issues = [
        i for i in issues
        if i.get("title", "").startswith(TITLE_PREFIX)
        or TRANSFER_LABEL in [l["name"] for l in i.get("labels", [])]
    ]

    if not dt_issues:
        print("No data-transfer issues found.")
        return

    print(f"Found {len(dt_issues)} data-transfer issue(s)\n")

    for issue in dt_issues:
        number = issue["number"]
        title = issue["title"]
        labels = [l["name"] for l in issue.get("labels", [])]

        if "verified" in labels:
            print(f"Skipping #{number} ({title}) - already verified")
            continue

        print(f"{'='*60}")
        print(f"Processing #{number}: {title}")
        print(f"{'='*60}")

        # Reuse cmd_issue logic
        args.number = number
        try:
            cmd_issue(args)
        except SystemExit:
            print(f"\nFailed to process #{number}, continuing...")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Pull encrypted data from GitHub Issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo", type=str, default=None,
        help=f"GitHub repo (default: {GITHUB_REPO or '$GITHUB_REPO'})",
    )

    subparsers = parser.add_subparsers(dest="command")

    # list
    list_parser = subparsers.add_parser("list", help="List data-transfer issues")
    list_parser.set_defaults(func=cmd_list)

    # issue
    issue_parser = subparsers.add_parser("issue",
                                         help="Pull a single issue")
    issue_parser.add_argument("number", type=int, help="Issue number")
    issue_parser.add_argument("-o", "--output", type=str, default=None,
                              help="Output directory")
    issue_parser.add_argument("--force", action="store_true",
                              help="Proceed even if MD5 verification fails")
    issue_parser.add_argument("--hex-only", action="store_true",
                              help="Save hex files without decrypting")
    issue_parser.add_argument("--no-label", action="store_true",
                              help="Don't add 'verified' label after success")
    issue_parser.set_defaults(func=cmd_issue)

    # all
    all_parser = subparsers.add_parser("all", help="Pull all [DT] issues")
    all_parser.add_argument("-o", "--output", type=str, default=None,
                            help="Output directory")
    all_parser.add_argument("--force", action="store_true",
                            help="Proceed even if MD5 verification fails")
    all_parser.add_argument("--hex-only", action="store_true",
                            help="Save hex files without decrypting")
    all_parser.add_argument("--no-label", action="store_true",
                            help="Don't add 'verified' label after success")
    all_parser.set_defaults(func=cmd_all)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
