"""GitHub REST + GraphQL provider for data transfer operations."""

import sys
from typing import Optional, List, Dict, Any, Tuple

import requests

from lib.config import GITHUB_TOKEN, GITHUB_API_URL, GRAPHQL_API_URL
from lib.crypto import clean_hex_data


class GitHubProvider:
    """GitHub implementation of the GitProvider protocol."""

    chunks_in_comments = False  # chunks live in edit history, metadata in comments

    def __init__(self, token: Optional[str] = None):
        self._token = token or GITHUB_TOKEN

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _graphql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        if not self._token:
            raise ValueError("GITHUB_TOKEN required for GraphQL API")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(
                GRAPHQL_API_URL, headers=headers,
                json={"query": query, "variables": variables}, timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            if "errors" in result:
                print(f"GraphQL errors: {result['errors']}", file=sys.stderr)
                return {}
            return result.get("data", {})
        except requests.RequestException as e:
            print(f"Error making GraphQL query: {e}", file=sys.stderr)
            return {}

    # -- Issue CRUD --

    def fetch_open_issues(self, repo: str,
                          labels: Optional[str] = None) -> List[Dict[str, Any]]:
        headers = self._headers()
        issues: List[Dict[str, Any]] = []
        page = 1
        while True:
            params: Dict[str, Any] = {"state": "open", "page": page, "per_page": 100}
            if labels:
                params["labels"] = labels
            url = f"{GITHUB_API_URL}/repos/{repo}/issues"
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
            except requests.RequestException as e:
                print(f"Error fetching issues: {e}", file=sys.stderr)
                return issues
            if resp.status_code != 200:
                print(f"Error fetching issues: {resp.status_code} {resp.text}",
                      file=sys.stderr)
                return issues
            batch = resp.json()
            if not batch:
                break
            issues.extend(i for i in batch if "pull_request" not in i)
            if len(batch) < 100:
                break
            page += 1
        return issues

    def create_issue(self, repo: str, title: str, body: str,
                     labels: Optional[List[str]] = None) -> Dict[str, Any]:
        headers = self._headers()
        url = f"{GITHUB_API_URL}/repos/{repo}/issues"
        payload: Dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def update_issue_body(self, repo: str, issue_number: int,
                          body: str) -> Dict[str, Any]:
        headers = self._headers()
        url = f"{GITHUB_API_URL}/repos/{repo}/issues/{issue_number}"
        resp = requests.patch(url, headers=headers, json={"body": body}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def add_issue_comment(self, repo: str, issue_number: int,
                          body: str) -> Dict[str, Any]:
        headers = self._headers()
        url = f"{GITHUB_API_URL}/repos/{repo}/issues/{issue_number}/comments"
        resp = requests.post(url, headers=headers, json={"body": body}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_issue_comments(self, repo: str,
                           issue_number: int) -> List[Dict[str, Any]]:
        headers = self._headers()
        url = f"{GITHUB_API_URL}/repos/{repo}/issues/{issue_number}/comments"
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def add_issue_labels(self, repo: str, issue_number: int,
                         labels: List[str]) -> None:
        headers = self._headers()
        url = f"{GITHUB_API_URL}/repos/{repo}/issues/{issue_number}/labels"
        resp = requests.post(url, headers=headers, json={"labels": labels}, timeout=30)
        resp.raise_for_status()

    def close_issue(self, repo: str, issue_number: int) -> Dict[str, Any]:
        headers = self._headers()
        url = f"{GITHUB_API_URL}/repos/{repo}/issues/{issue_number}"
        resp = requests.patch(url, headers=headers, json={"state": "closed"}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # -- Chunk retrieval (GitHub-specific: edit history via GraphQL) --

    def fetch_chunks(self, repo: str,
                     issue_number: int) -> Tuple[List[str], Optional[str]]:
        """Fetch hex chunks from issue edit history + current body."""
        owner, repo_name = repo.split("/")

        query = """
        query ($owner: String!, $name: String!, $number: Int!, $after: String) {
          repository(owner: $owner, name: $name) {
            issue(number: $number) {
              body
              author { login }
              createdAt
              lastEditedAt
              editor { login }
              userContentEdits(first: 50, after: $after) {
                totalCount
                pageInfo { hasNextPage endCursor }
                nodes { createdAt editedAt diff editor { login } }
              }
            }
          }
        }
        """

        variables: Dict[str, Any] = {
            "owner": owner, "name": repo_name,
            "number": issue_number, "after": None,
        }

        all_edits: List[Dict[str, Any]] = []
        issue_body: Optional[str] = None

        while True:
            data = self._graphql(query, variables)
            if not data or "repository" not in data or not data["repository"]:
                break
            issue_data = data["repository"].get("issue")
            if not issue_data:
                break
            if issue_body is None:
                issue_body = issue_data.get("body", "")
            edits_data = issue_data.get("userContentEdits", {})
            all_edits.extend(edits_data.get("nodes", []))
            page_info = edits_data.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                variables["after"] = page_info["endCursor"]
            else:
                break

        # Extract hex from edits + body
        raw_chunks: List[str] = []
        for edit in all_edits:
            diff = edit.get("diff", "")
            if diff:
                hex_data = clean_hex_data(diff)
                if hex_data:
                    raw_chunks.append(hex_data)
        if issue_body:
            body_hex = clean_hex_data(issue_body)
            if body_hex:
                raw_chunks.append(body_hex)

        return raw_chunks, issue_body
