"""Structured metadata in issue comments for data transfer tracking."""

import json
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from lib.config import TITLE_PREFIX

METADATA_START = "<!-- DT-METADATA"
METADATA_END = "DT-METADATA -->"


def generate_issue_title(filename: str, timestamp: str) -> str:
    """Generate a standardized issue title for data transfer."""
    return f"{TITLE_PREFIX} {filename} {timestamp}"


def generate_metadata_comment(filename: str, timestamp: str,
                              gpg_key: str, total_parts: int,
                              parts: List[Dict],
                              archive_md5: str,
                              total_hex_chars: int = 0) -> str:
    """
    Generate a metadata comment body to be posted as the first comment.
    Wrapped in an HTML comment so it's invisible in the GitHub UI.
    """
    metadata = {
        "version": 1,
        "filename": filename,
        "timestamp": timestamp,
        "gpg_key": gpg_key,
        "total_parts": total_parts,
        "total_hex_chars": total_hex_chars,
        "parts": parts,
        "archive_md5": archive_md5,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    json_str = json.dumps(metadata, indent=2)
    return f"{METADATA_START}\n{json_str}\n{METADATA_END}"


def parse_metadata_comment(comment_body: str) -> Optional[Dict[str, Any]]:
    """
    Parse metadata from an issue comment.
    Returns the metadata dict if found, None otherwise.
    """
    pattern = re.compile(
        re.escape(METADATA_START) + r'\s*(.*?)\s*' + re.escape(METADATA_END),
        re.DOTALL
    )
    match = pattern.search(comment_body)
    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None


def find_metadata_in_comments(comments: List[Dict[str, Any]]
                              ) -> Optional[Dict[str, Any]]:
    """Search through issue comments for DT-METADATA block."""
    for comment in comments:
        body = comment.get("body", "")
        metadata = parse_metadata_comment(body)
        if metadata:
            return metadata
    return None
