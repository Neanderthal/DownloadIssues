#!/usr/bin/env python3
"""
GitHub Issues Downloader

Downloads all open issues from a specified GitHub repository and saves them
as individual markdown files. Can be run periodically to keep issues in sync.
"""

import os
import re
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    import requests
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Error: Required library not found: {e}", file=sys.stderr)
    print("Install dependencies with: uv sync", file=sys.stderr)
    sys.exit(1)

# Load environment variables from .env file
load_dotenv()

# ========= CONFIGURATION =========
# Format: "owner/repo"
REPO = os.environ.get("GITHUB_REPO", "")

# Where to save issue text files
OUTPUT_DIR = Path(os.environ.get("ISSUES_DIR", "data/projects/issues"))

# Where to save changed issues
CHANGES_DIR = OUTPUT_DIR / "changes"

# Where to save edit history
EDIT_HISTORY_DIR = OUTPUT_DIR / "edit_history"

# Track state between runs
STATE_FILE = Path(".issues_state.json")

# GitHub API base URL
GITHUB_API_URL = "https://api.github.com"

# GitHub GraphQL API URL
GRAPHQL_API_URL = "https://api.github.com/graphql"
# ==================================


def slugify(text: str, max_length: int = 50) -> str:
    """Create a filesystem-friendly slug from the issue title."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text or "issue"


def get_github_token() -> Optional[str]:
    """Get GitHub token from environment."""
    return os.environ.get("GITHUB_TOKEN")


def graphql_query(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a GraphQL query against GitHub API."""
    token = get_github_token()
    if not token:
        raise ValueError("GITHUB_TOKEN required for GraphQL API")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "variables": variables,
    }

    try:
        resp = requests.post(GRAPHQL_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        if "errors" in result:
            print(f"GraphQL errors: {result['errors']}", file=sys.stderr)
            return {}

        return result.get("data", {})
    except requests.RequestException as e:
        print(f"Error making GraphQL query: {e}", file=sys.stderr)
        return {}


def fetch_issue_edit_history(repo: str, issue_number: int) -> List[Dict[str, Any]]:
    """
    Fetch edit history for a specific issue using GraphQL API.
    Returns list of edits with createdAt, diff, and editor information.
    """
    owner, repo_name = repo.split("/")

    query = """
    query ($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        issue(number: $number) {
          author { login }
          createdAt
          lastEditedAt
          editor { login }
          userContentEdits(first: 50) {
            totalCount
            nodes {
              createdAt
              editedAt
              diff
              editor { login }
            }
          }
        }
      }
    }
    """

    variables = {
        "owner": owner,
        "name": repo_name,
        "number": issue_number,
    }

    data = graphql_query(query, variables)

    if not data or "repository" not in data or not data["repository"]:
        return []

    issue_data = data["repository"].get("issue", {})
    if not issue_data:
        return []

    edits = issue_data.get("userContentEdits", {}).get("nodes", [])
    return edits


def fetch_open_issues(repo: str) -> List[Dict[str, Any]]:
    """
    Fetch all open issues for a repository.
    Note: GitHub's /issues endpoint also returns PRs; we filter them out.
    """
    token = get_github_token()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    issues = []
    page = 1
    per_page = 100

    while True:
        params = {
            "state": "open",
            "page": page,
            "per_page": per_page,
        }
        url = f"{GITHUB_API_URL}/repos/{repo}/issues"

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"Error fetching issues: {e}", file=sys.stderr)
            sys.exit(1)

        if resp.status_code != 200:
            print(f"Error fetching issues: {resp.status_code}", file=sys.stderr)
            print(f"Response: {resp.text}", file=sys.stderr)
            sys.exit(1)

        batch = resp.json()
        if not batch:
            break

        # Filter out pull requests (they have a 'pull_request' key)
        batch_issues = [issue for issue in batch if "pull_request" not in issue]
        issues.extend(batch_issues)

        if len(batch) < per_page:
            break

        page += 1

    return issues


def get_issue_hash(issue: Dict[str, Any]) -> str:
    """Generate a hash of the issue content to detect changes."""
    import hashlib

    # Include fields that we care about for change detection
    content = json.dumps({
        "title": issue.get("title", ""),
        "body": issue.get("body", ""),
        "state": issue.get("state", ""),
        "labels": [label["name"] for label in issue.get("labels", [])],
        "updated_at": issue.get("updated_at", ""),
    }, sort_keys=True)

    return hashlib.sha256(content.encode()).hexdigest()


def save_edit_history(issue_number: int, title: str, edit_history_dir: Path) -> None:
    """
    Fetch and save edit history for an issue using GraphQL API.
    Saves to a JSON file with all edit information.
    """
    if not get_github_token():
        # Skip edit history if no token (GraphQL requires auth)
        return

    try:
        edits = fetch_issue_edit_history(REPO, issue_number)

        if not edits:
            return

        slug = slugify(title)
        edit_history_dir.mkdir(parents=True, exist_ok=True)
        history_file = edit_history_dir / f"{issue_number:04d}-{slug}-edits.json"

        # Save edit history as JSON
        history_data = {
            "issue_number": issue_number,
            "title": title,
            "total_edits": len(edits),
            "fetched_at": datetime.now().astimezone().isoformat(),
            "edits": edits,
        }

        history_file.write_text(json.dumps(history_data, indent=2), encoding="utf-8")

        if len(edits) > 0:
            print(f"  📝 Saved {len(edits)} edit(s) to edit_history/")

    except Exception as e:
        print(f"  ⚠️  Could not fetch edit history: {e}", file=sys.stderr)


def save_issue_to_file(issue: Dict[str, Any], out_dir: Path, changes_dir: Path, prev_state: Dict[str, Any]) -> bool:
    """
    Save an individual issue to a markdown file.
    Returns True if the issue was changed, False otherwise.
    """
    number = issue["number"]
    title = issue.get("title", "")
    body = issue.get("body") or ""
    url = issue["html_url"]
    labels = ", ".join([label["name"] for label in issue.get("labels", [])])

    slug = slugify(title)
    filename = out_dir / f"{number:04d}-{slug}.md"

    content = f"""{body}"""

    # Check if issue has changed
    current_hash = get_issue_hash(issue)
    prev_hashes = prev_state.get("issue_hashes", {})
    prev_hash = prev_hashes.get(str(number))

    changed = prev_hash is not None and prev_hash != current_hash

    # Save current version
    filename.write_text(content, encoding="utf-8")

    if changed:
        # Save changed version with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        changes_dir.mkdir(parents=True, exist_ok=True)
        change_filename = changes_dir / f"{number:04d}-{slug}-{timestamp}.md"
        change_filename.write_text(content, encoding="utf-8")
        print(f"🔄 Changed issue #{number} -> {filename.name} (saved to changes/)")

        # Fetch and save edit history for changed issues
        save_edit_history(number, title, EDIT_HISTORY_DIR)
    else:
        print(f"✓ Saved issue #{number} -> {filename.name}")

    return changed


def load_state() -> Dict[str, Any]:
    """Load previous run state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Warning: Could not load state file: {e}", file=sys.stderr)
            return {}
    return {}


def save_state(state: Dict[str, Any]) -> None:
    """Save current run state."""
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def clean_old_issues(current_issue_numbers: List[int], out_dir: Path) -> None:
    """Remove issue files that are no longer open."""
    if not out_dir.exists():
        return

    removed_count = 0
    for file in out_dir.glob("*.md"):
        try:
            # Extract issue number from filename (format: 0001-title.md)
            issue_num = int(file.stem.split("-")[0])
            if issue_num not in current_issue_numbers:
                file.unlink()
                print(f"✗ Removed closed/deleted issue #{issue_num}")
                removed_count += 1
        except (ValueError, IndexError):
            # Skip files that don't match our naming pattern
            continue

    if removed_count > 0:
        print(f"\nRemoved {removed_count} closed/deleted issue(s)")


def sync_issues(fetch_all_edits: bool = False) -> None:
    """Fetch and sync issues once."""
    print(f"📥 Fetching open issues for {REPO}...")

    # Load previous state
    prev_state = load_state()

    # Fetch issues
    issues = fetch_open_issues(REPO)
    print(f"Found {len(issues)} open issue(s)\n")

    # Create output directories
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHANGES_DIR.mkdir(parents=True, exist_ok=True)
    EDIT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # Save all issues and track changes
    changed_count = 0
    issue_hashes = {}
    for issue in issues:
        changed = save_issue_to_file(issue, OUTPUT_DIR, CHANGES_DIR, prev_state)
        if changed:
            changed_count += 1
        elif fetch_all_edits:
            # Fetch edit history for all issues if requested
            save_edit_history(issue["number"], issue.get("title", ""), EDIT_HISTORY_DIR)
        issue_hashes[str(issue["number"])] = get_issue_hash(issue)

    # Clean up closed issues
    current_numbers = [issue["number"] for issue in issues]
    # clean_old_issues(current_numbers, OUTPUT_DIR)

    # Save state with hashes
    state = {
        "repo": REPO,
        "last_issue_count": len(issues),
        "last_run": datetime.now().astimezone().isoformat(),
        "issue_numbers": current_numbers,
        "issue_hashes": issue_hashes,
    }
    save_state(state)

    if changed_count > 0:
        print(f"\n🔄 {changed_count} issue(s) were modified")
    print(f"✅ Done! Issues saved to: {OUTPUT_DIR.absolute()}")


def watch_mode(interval: int = 3, fetch_all_edits: bool = False) -> None:
    """Continuously check for issues at specified interval."""
    print(f"🔄 Starting watch mode (checking every {interval}s)")
    print(f"   Repository: {REPO}")
    print(f"   Output: {OUTPUT_DIR.absolute()}")
    print("   Press Ctrl+C to stop\n")

    iteration = 0
    try:
        while True:
            iteration += 1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n{'='*60}")
            print(f"[{timestamp}] Check #{iteration}")
            print(f"{'='*60}")

            try:
                sync_issues(fetch_all_edits)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"❌ Error during sync: {e}", file=sys.stderr)
                print("   Will retry on next interval...")

            print(f"\n⏳ Waiting {interval} seconds before next check...")
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n👋 Stopping watch mode. Goodbye!")
        sys.exit(0)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download and monitor GitHub issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run in watch mode (continuously check for updates)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3,
        metavar="SECONDS",
        help="Interval between checks in watch mode (default: 3 seconds)",
    )
    parser.add_argument(
        "--fetch-edit-history",
        action="store_true",
        help="Fetch edit history for all issues (requires GITHUB_TOKEN)",
    )

    args = parser.parse_args()

    # Validate configuration
    if not REPO:
        print("Error: GITHUB_REPO not configured.", file=sys.stderr)
        print("Create a .env file with: GITHUB_REPO=owner/repo", file=sys.stderr)
        print(
            "Or set environment variable: export GITHUB_REPO='owner/repo'",
            file=sys.stderr,
        )
        sys.exit(1)

    if not get_github_token():
        print("⚠️  Warning: No GITHUB_TOKEN set. Rate limits will be stricter.")
        if args.fetch_edit_history:
            print("   Edit history requires GITHUB_TOKEN (GraphQL API).")
        print("   Set token with: export GITHUB_TOKEN='your_token_here'\n")

    # Run in watch mode or single run
    if args.watch:
        watch_mode(args.interval, args.fetch_edit_history)
    else:
        sync_issues(args.fetch_edit_history)


if __name__ == "__main__":
    main()
