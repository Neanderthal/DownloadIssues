"""Provider protocol and factory for git hosting services."""

from __future__ import annotations

from typing import Protocol, List, Dict, Any, Optional, Tuple


class GitProvider(Protocol):
    """Common interface for git hosting providers (GitHub, GitFlic, etc.)."""

    # -- Data layout --
    # Providers differ in how they store chunks vs metadata:
    #   GitHub:  body edits = chunks, first comment = metadata
    #   GitFlic: body = metadata, comments = chunks
    #
    # The `chunks_in_comments` flag tells push/pull which layout to use.

    chunks_in_comments: bool

    def fetch_open_issues(self, repo: str,
                          labels: Optional[str] = None) -> List[Dict[str, Any]]:
        ...

    def create_issue(self, repo: str, title: str, body: str,
                     labels: Optional[List[str]] = None) -> Dict[str, Any]:
        ...

    def update_issue_body(self, repo: str, issue_number: int,
                          body: str) -> Dict[str, Any]:
        ...

    def add_issue_comment(self, repo: str, issue_number: int,
                          body: str) -> Dict[str, Any]:
        ...

    def get_issue_comments(self, repo: str,
                           issue_number: int) -> List[Dict[str, Any]]:
        ...

    def add_issue_labels(self, repo: str, issue_number: int,
                         labels: List[str]) -> None:
        ...

    def close_issue(self, repo: str,
                    issue_number: int) -> Dict[str, Any]:
        ...

    def fetch_chunks(self, repo: str,
                     issue_number: int) -> Tuple[List[str], Optional[str]]:
        """Fetch raw hex chunks and the current issue body.

        Returns (hex_chunks, body_text).
        For GitHub: chunks come from edit history.
        For GitFlic: chunks come from comments.
        """
        ...


def get_provider(name: str) -> GitProvider:
    """Factory: return a provider instance by name."""
    if name == "github":
        from lib.github_api import GitHubProvider
        return GitHubProvider()
    elif name == "gitflic":
        from lib.gitflic_api import GitFlicProvider
        return GitFlicProvider()
    else:
        raise ValueError(f"Unknown provider: {name!r}. Use 'github' or 'gitflic'.")
