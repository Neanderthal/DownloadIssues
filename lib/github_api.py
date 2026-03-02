"""GitHub REST + GraphQL client for data transfer operations."""

import sys
from typing import Optional, List, Dict, Any, Tuple

import requests

from lib.config import GITHUB_TOKEN, GITHUB_API_URL, GRAPHQL_API_URL


def get_headers(token: Optional[str] = None) -> Dict[str, str]:
    """Build authorization headers."""
    t = token or GITHUB_TOKEN
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if t:
        headers["Authorization"] = f"Bearer {t}"
    return headers


def graphql_query(query: str, variables: Dict[str, Any],
                  token: Optional[str] = None) -> Dict[str, Any]:
    """Execute a GraphQL query against GitHub API."""
    t = token or GITHUB_TOKEN
    if not t:
        raise ValueError("GITHUB_TOKEN required for GraphQL API")

    headers = {
        "Authorization": f"Bearer {t}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": variables}

    try:
        resp = requests.post(GRAPHQL_API_URL, headers=headers,
                             json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if "errors" in result:
            print(f"GraphQL errors: {result['errors']}", file=sys.stderr)
            return {}
        return result.get("data", {})
    except requests.RequestException as e:
        print(f"Error making GraphQL query: {e}", file=sys.stderr)
        return {}


def fetch_issue_edit_history(repo: str, issue_number: int,
                             token: Optional[str] = None
                             ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Fetch full edit history for an issue using GraphQL with cursor pagination.
    Returns (list_of_edits, current_issue_body).
    """
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
            pageInfo {
              hasNextPage
              endCursor
            }
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
        "after": None,
    }

    all_edits = []
    issue_body = None

    while True:
        data = graphql_query(query, variables, token)
        if not data or "repository" not in data or not data["repository"]:
            break

        issue_data = data["repository"].get("issue")
        if not issue_data:
            break

        if issue_body is None:
            issue_body = issue_data.get("body", "")

        edits_data = issue_data.get("userContentEdits", {})
        nodes = edits_data.get("nodes", [])
        all_edits.extend(nodes)

        page_info = edits_data.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            variables["after"] = page_info["endCursor"]
        else:
            break

    return all_edits, issue_body


def fetch_open_issues(repo: str, labels: Optional[str] = None,
                      token: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch all open issues, optionally filtered by label."""
    headers = get_headers(token)
    issues = []
    page = 1

    while True:
        params = {"state": "open", "page": page, "per_page": 100}
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

        batch_issues = [i for i in batch if "pull_request" not in i]
        issues.extend(batch_issues)

        if len(batch) < 100:
            break
        page += 1

    return issues


def create_issue(repo: str, title: str, body: str,
                 labels: Optional[List[str]] = None,
                 token: Optional[str] = None) -> Dict[str, Any]:
    """Create a new issue. Returns the issue JSON."""
    headers = get_headers(token)
    url = f"{GITHUB_API_URL}/repos/{repo}/issues"
    payload: Dict[str, Any] = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def update_issue_body(repo: str, issue_number: int, body: str,
                      token: Optional[str] = None) -> Dict[str, Any]:
    """Update an issue's body (creates an edit in history)."""
    headers = get_headers(token)
    url = f"{GITHUB_API_URL}/repos/{repo}/issues/{issue_number}"
    payload = {"body": body}

    resp = requests.patch(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def add_issue_comment(repo: str, issue_number: int, body: str,
                      token: Optional[str] = None) -> Dict[str, Any]:
    """Add a comment to an issue."""
    headers = get_headers(token)
    url = f"{GITHUB_API_URL}/repos/{repo}/issues/{issue_number}/comments"
    payload = {"body": body}

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_issue_comments(repo: str, issue_number: int,
                       token: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all comments on an issue."""
    headers = get_headers(token)
    url = f"{GITHUB_API_URL}/repos/{repo}/issues/{issue_number}/comments"

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def add_issue_labels(repo: str, issue_number: int, labels: List[str],
                     token: Optional[str] = None) -> List[Dict[str, Any]]:
    """Add labels to an issue."""
    headers = get_headers(token)
    url = f"{GITHUB_API_URL}/repos/{repo}/issues/{issue_number}/labels"
    payload = {"labels": labels}

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def close_issue(repo: str, issue_number: int,
                token: Optional[str] = None) -> Dict[str, Any]:
    """Close an issue (set state to closed)."""
    headers = get_headers(token)
    url = f"{GITHUB_API_URL}/repos/{repo}/issues/{issue_number}"
    payload = {"state": "closed"}

    resp = requests.patch(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()
