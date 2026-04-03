"""GitFlic REST provider for data transfer operations."""

import sys
from typing import Optional, List, Dict, Any, Tuple

import requests

from lib.config import GITFLIC_TOKEN, GITFLIC_API_URL
from lib.crypto import clean_hex_data


class GitFlicProvider:
    """GitFlic implementation of the GitProvider protocol.

    Key difference from GitHub: no edit history API.
    Chunks are stored as comments; metadata goes in the issue body.
    """

    chunks_in_comments = True

    def __init__(self, token: Optional[str] = None):
        self._token = token or GITFLIC_TOKEN

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        return headers

    def _split_repo(self, repo: str) -> Tuple[str, str]:
        """Split 'owner/project' into (owner, project)."""
        parts = repo.split("/", 1)
        if len(parts) != 2:
            raise ValueError(
                f"GITFLIC_PROJECT must be 'owner/project', got: {repo!r}")
        return parts[0], parts[1]

    def _base(self, repo: str) -> str:
        owner, project = self._split_repo(repo)
        return f"{GITFLIC_API_URL}/project/{owner}/{project}"

    # -- Issue CRUD --

    def fetch_open_issues(self, repo: str,
                          labels: Optional[str] = None) -> List[Dict[str, Any]]:
        base = self._base(repo)
        headers = self._headers()
        issues: List[Dict[str, Any]] = []
        page = 0

        while True:
            params: Dict[str, Any] = {"page": page, "size": 50}
            try:
                resp = requests.get(
                    f"{base}/issue", headers=headers, params=params, timeout=30)
            except requests.RequestException as e:
                print(f"Error fetching issues: {e}", file=sys.stderr)
                return issues

            if resp.status_code != 200:
                print(f"Error fetching issues: {resp.status_code} {resp.text}",
                      file=sys.stderr)
                return issues

            data = resp.json()

            # Handle GitFlic pagination: _embedded or direct list
            if isinstance(data, list):
                batch = data
            elif isinstance(data, dict):
                embedded = data.get("_embedded", {})
                # Try common list key names
                batch = (embedded.get("issueModelList")
                         or embedded.get("issueList")
                         or embedded.get("issues")
                         or embedded.get("items")
                         or [])
            else:
                break

            if not batch:
                break

            # Filter to open issues only
            for issue in batch:
                status = issue.get("status", {})
                status_id = status.get("id", "") if isinstance(status, dict) else status
                if status_id in ("OPEN", "IN_PROGRESS"):
                    # Normalize to common format
                    issues.append(self._normalize_issue(issue))

            # Check pagination
            if isinstance(data, dict):
                page_info = data.get("page", {})
                total_pages = page_info.get("totalPages", 1)
                if page + 1 >= total_pages:
                    break
            elif len(batch) < 50:
                break

            page += 1

        return issues

    def _normalize_issue(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize GitFlic issue to common format used by pull.py/push.py."""
        labels_raw = issue.get("labels", [])
        labels = [
            {"name": l.get("value", l.get("name", ""))}
            for l in labels_raw
        ] if labels_raw else []

        return {
            "number": issue.get("localId", issue.get("id")),
            "title": issue.get("title", ""),
            "body": issue.get("description", ""),
            "labels": labels,
            "updated_at": issue.get("updatedAt", ""),
            "created_at": issue.get("createdAt", ""),
            "_raw": issue,
        }

    def create_issue(self, repo: str, title: str, body: str,
                     labels: Optional[List[str]] = None) -> Dict[str, Any]:
        base = self._base(repo)
        headers = self._headers()

        payload: Dict[str, Any] = {
            "title": title,
            "description": body,
            "status": {"id": "OPEN"},
            "assignedUsers": [],
        }

        resp = requests.post(
            f"{base}/issue", headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        raw = resp.json()

        result = self._normalize_issue(raw)
        # Build html_url for display
        owner, project = self._split_repo(repo)
        result["html_url"] = (
            f"https://gitflic.ru/project/{owner}/{project}"
            f"/issue/{result['number']}")
        return result

    def update_issue_body(self, repo: str, issue_number: int,
                          body: str) -> Dict[str, Any]:
        base = self._base(repo)
        headers = self._headers()

        payload = {"description": body}
        resp = requests.put(
            f"{base}/issue/{issue_number}/edit",
            headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return self._normalize_issue(resp.json())

    def add_issue_comment(self, repo: str, issue_number: int,
                          body: str) -> Dict[str, Any]:
        base = self._base(repo)
        headers = self._headers()

        resp = requests.post(
            f"{base}/issue-discussion/{issue_number}/create",
            headers=headers, json={"note": body}, timeout=30)
        resp.raise_for_status()
        raw = resp.json()

        return {
            "id": raw.get("id"),
            "body": raw.get("message", raw.get("note", "")),
        }

    def get_issue_comments(self, repo: str,
                           issue_number: int) -> List[Dict[str, Any]]:
        base = self._base(repo)
        headers = self._headers()
        comments: List[Dict[str, Any]] = []
        page = 0

        while True:
            params: Dict[str, Any] = {"page": page, "size": 50}
            try:
                resp = requests.get(
                    f"{base}/issue-discussion/{issue_number}",
                    headers=headers, params=params, timeout=30)
            except requests.RequestException as e:
                print(f"Error fetching comments: {e}", file=sys.stderr)
                return comments

            if resp.status_code != 200:
                print(f"Error fetching comments: {resp.status_code} {resp.text}",
                      file=sys.stderr)
                return comments

            data = resp.json()

            if isinstance(data, list):
                batch = data
            elif isinstance(data, dict):
                embedded = data.get("_embedded", {})
                batch = (embedded.get("IssueDiscussionList")
                         or embedded.get("issueDiscussionList")
                         or embedded.get("discussions")
                         or embedded.get("items")
                         or [])
            else:
                break

            if not batch:
                break

            for c in batch:
                comments.append({
                    "id": c.get("id"),
                    "body": c.get("message", c.get("note", "")),
                    "created_at": c.get("createdAt", ""),
                })

            if isinstance(data, dict):
                page_info = data.get("page", {})
                total_pages = page_info.get("totalPages", 1)
                if page + 1 >= total_pages:
                    break
            elif len(batch) < 50:
                break

            page += 1

        return comments

    def add_issue_labels(self, repo: str, issue_number: int,
                         labels: List[str]) -> None:
        # GitFlic has no REST API for labels.
        # Labels must be pre-created in the web UI and referenced by UUID.
        # We silently skip this — issues are identified by title prefix instead.
        pass

    def close_issue(self, repo: str, issue_number: int) -> Dict[str, Any]:
        base = self._base(repo)
        headers = self._headers()

        payload = {"status": {"id": "CLOSED"}}
        resp = requests.put(
            f"{base}/issue/{issue_number}/edit",
            headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return self._normalize_issue(resp.json())

    # -- Chunk retrieval (GitFlic: chunks are in comments) --

    def fetch_chunks(self, repo: str,
                     issue_number: int) -> Tuple[List[str], Optional[str]]:
        """Fetch hex chunks from issue comments + issue body.

        On GitFlic the body holds metadata and comments hold chunks.
        """
        # Get issue body
        base = self._base(repo)
        headers = self._headers()
        try:
            resp = requests.get(
                f"{base}/issue/{issue_number}",
                headers=headers, timeout=30)
            resp.raise_for_status()
            issue_data = resp.json()
        except requests.RequestException as e:
            print(f"Error fetching issue: {e}", file=sys.stderr)
            return [], None

        issue_body = issue_data.get("description", "")

        # Get all comments (these contain the hex chunks)
        comments = self.get_issue_comments(repo, issue_number)

        raw_chunks: List[str] = []
        for comment in comments:
            body = comment.get("body", "")
            if body:
                hex_data = clean_hex_data(body)
                if hex_data:
                    raw_chunks.append(hex_data)

        return raw_chunks, issue_body
