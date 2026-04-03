#!/usr/bin/env python3
"""
Pull data from a git hosting provider: download + verify + decrypt.

Supports GitHub (edit history) and GitFlic (comments).

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

load_dotenv(override=True)

from lib.config import (
    PROVIDER, TRANSFER_LABEL, TITLE_PREFIX, EXTRACTED_DIR,
    get_repo_for_provider,
)
from lib.provider import get_provider
from lib.crypto import full_decrypt_pipeline, generate_part_suffix
from lib.metadata import find_metadata_in_comments, parse_metadata_comment


def cmd_list(args):
    """List available data-transfer issues."""
    provider_name = args.provider or PROVIDER
    provider = get_provider(provider_name)
    repo = get_repo_for_provider(provider_name, args.repo)

    if not repo:
        print(f"Error: repo/project not configured for {provider_name}.",
              file=sys.stderr)
        sys.exit(1)

    print(f"Fetching issues from {repo} ({provider_name})...")

    issues = provider.fetch_open_issues(repo)

    dt_issues = []
    for issue in issues:
        title = issue.get("title", "")
        labels = [l["name"] for l in issue.get("labels", [])]
        if title.startswith(TITLE_PREFIX) or TRANSFER_LABEL in labels:
            dt_issues.append(issue)

    if not dt_issues:
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


def extract_chunks_from_issue(provider, repo, issue_number,
                              metadata=None, verbose=True):
    """Fetch and extract hex chunks from an issue.

    Works for both providers — provider.fetch_chunks() handles the
    platform-specific retrieval (edit history vs comments).
    """
    if verbose:
        print(f"Fetching data for issue #{issue_number}...")

    raw_chunks, current_body = provider.fetch_chunks(repo, issue_number)

    if verbose:
        print(f"  Found {len(raw_chunks)} raw chunk(s), "
              f"body: {len(current_body or '')} chars")

    if metadata and "parts" in metadata:
        from lib.integrity import compute_md5_str

        md5_to_chunk = {}
        for chunk in raw_chunks:
            md5 = compute_md5_str(chunk)
            md5_to_chunk.setdefault(md5, chunk)

        chunks = []
        missing = []
        for part in metadata["parts"]:
            expected_md5 = part.get("md5", "")
            if expected_md5 in md5_to_chunk:
                chunks.append(md5_to_chunk[expected_md5])
            else:
                missing.append(
                    f"{part.get('suffix', '?')} "
                    f"({part.get('hex_chars', '?')} chars)")

        ignored = len(raw_chunks) - len(md5_to_chunk)
        extra = len(md5_to_chunk) - len(chunks)
        verified = len(missing) == 0

        if verbose:
            if ignored:
                print(f"  Ignored {ignored} duplicate(s)")
            if extra:
                print(f"  Ignored {extra} unrecognised chunk(s)")
            if missing:
                print(f"  MISSING chunks: {', '.join(missing)}")
            status = ("all parts found" if verified
                      else f"{len(missing)} part(s) missing")
            total = sum(len(c) for c in chunks)
            print(f"  Matched {len(chunks)}/{len(metadata['parts'])} parts "
                  f"({total} hex chars) — {status}")

        return chunks, verified
    else:
        seen = set()
        chunks = []
        for chunk in raw_chunks:
            if chunk not in seen:
                seen.add(chunk)
                chunks.append(chunk)

        if verbose:
            total = sum(len(c) for c in chunks)
            print(f"  Extracted {len(chunks)} chunk(s), {total} total hex chars")

        return chunks, False


def _get_metadata(provider, repo, issue_number):
    """Get metadata — from comments (GitHub) or issue body (GitFlic)."""
    if provider.chunks_in_comments:
        # GitFlic: metadata is in the issue body
        _, body = provider.fetch_chunks(repo, issue_number)
        if body:
            return parse_metadata_comment(body)
        return None
    else:
        # GitHub: metadata is in the first comment
        comments = provider.get_issue_comments(repo, issue_number)
        return find_metadata_in_comments(comments)


def cmd_issue(args):
    """Pull, verify, and decrypt a single issue."""
    provider_name = args.provider or PROVIDER
    provider = get_provider(provider_name)
    repo = get_repo_for_provider(provider_name, args.repo)

    if not repo:
        print(f"Error: repo/project not configured for {provider_name}.",
              file=sys.stderr)
        sys.exit(1)

    issue_number = args.number
    output_dir = Path(args.output or EXTRACTED_DIR)

    print(f"Pulling issue #{issue_number} from {repo} ({provider_name})\n")

    # Step 1: Get metadata
    metadata = None
    try:
        metadata = _get_metadata(provider, repo, issue_number)
        if metadata:
            print(f"Found metadata: {metadata.get('filename', '?')} "
                  f"({metadata.get('total_parts', '?')} parts, "
                  f"archive MD5: {metadata.get('archive_md5', '?')[:12]}...)")
        else:
            print("No metadata found (legacy issue)")
    except Exception as e:
        print(f"Warning: Could not fetch metadata: {e}", file=sys.stderr)

    # Step 2: Extract + verify chunks
    chunks, verified = extract_chunks_from_issue(
        provider, repo, issue_number, metadata=metadata)

    if not chunks:
        print("\nNo hex data found in this issue.", file=sys.stderr)
        sys.exit(1)

    if metadata and not verified:
        if not args.force:
            print("\nUse --force to proceed despite missing chunks.",
                  file=sys.stderr)
            sys.exit(1)
        print("  Proceeding anyway (--force)")

    # Step 3: Decrypt
    if metadata:
        filename = metadata.get("filename", f"issue_{issue_number}")
        timestamp = metadata.get("timestamp",
                                 datetime.now().strftime("%Y%m%d_%H%M%S"))
    else:
        filename = f"issue_{issue_number:04d}"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    issue_output = output_dir / f"{filename}_{timestamp}"

    if args.hex_only:
        save_hex_chunks(chunks, issue_output, filename, timestamp)
    else:
        try:
            print(f"\nDecrypting to {issue_output}/...")
            full_decrypt_pipeline(chunks, str(issue_output))
            print(f"Extracted to: {issue_output.absolute()}")

            if verified and not args.no_label:
                try:
                    provider.add_issue_labels(repo, issue_number, ["verified"])
                    print("Added 'verified' label to issue")
                except Exception as e:
                    print(f"Warning: Could not add label: {e}",
                          file=sys.stderr)

        except Exception as e:
            print(f"\nDecryption failed: {e}", file=sys.stderr)
            print("Saving hex files for manual decryption...")
            save_hex_chunks(chunks, output_dir, filename, timestamp)
            sys.exit(1)

    if getattr(args, 'burn', False):
        try:
            provider.close_issue(repo, issue_number)
            print(f"Burned issue #{issue_number} (closed)")
        except Exception as e:
            print(f"Warning: Could not close issue: {e}", file=sys.stderr)


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
    provider_name = args.provider or PROVIDER
    provider = get_provider(provider_name)
    repo = get_repo_for_provider(provider_name, args.repo)

    if not repo:
        print(f"Error: repo/project not configured for {provider_name}.",
              file=sys.stderr)
        sys.exit(1)

    output_dir = args.output or EXTRACTED_DIR

    issues = provider.fetch_open_issues(repo)
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

        args.number = number
        try:
            cmd_issue(args)
        except SystemExit:
            print(f"\nFailed to process #{number}, continuing...")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Pull encrypted data from git hosting issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--provider", type=str, default=None,
        help=f"Provider: github or gitflic (default: {PROVIDER})",
    )
    parser.add_argument(
        "--repo", type=str, default=None,
        help="Override repo/project from env",
    )

    subparsers = parser.add_subparsers(dest="command")

    # list
    list_parser = subparsers.add_parser("list", help="List data-transfer issues")
    list_parser.set_defaults(func=cmd_list)

    # issue
    issue_parser = subparsers.add_parser("issue", help="Pull a single issue")
    issue_parser.add_argument("number", type=int, help="Issue number")
    issue_parser.add_argument("-o", "--output", type=str, default=None,
                              help="Output directory")
    issue_parser.add_argument("--force", action="store_true",
                              help="Proceed even if MD5 verification fails")
    issue_parser.add_argument("--hex-only", action="store_true",
                              help="Save hex files without decrypting")
    issue_parser.add_argument("--no-label", action="store_true",
                              help="Don't add 'verified' label after success")
    issue_parser.add_argument("--burn", action="store_true",
                              help="Close the issue after successful pull")
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
    all_parser.add_argument("--burn", action="store_true",
                            help="Close issues after successful pull")
    all_parser.set_defaults(func=cmd_all)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
