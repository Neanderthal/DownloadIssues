"""Structured metadata in issue comments for data transfer tracking."""

import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from lib.config import TITLE_PREFIX


def generate_issue_title(filename: str, timestamp: str) -> str:
    """Generate a standardized issue title for data transfer."""
    return f"{TITLE_PREFIX} {filename} {timestamp}"


def generate_metadata_comment(filename: str, timestamp: str,
                              gpg_key: str, total_parts: int,
                              parts: List[Dict],
                              archive_md5: str,
                              total_hex_chars: int = 0) -> str:
    """
    Generate metadata JSON to be posted as the first comment.
    Plain JSON -- no wrapper needed.
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

    return json.dumps(metadata, indent=2)


def parse_metadata_comment(comment_body: str) -> Optional[Dict[str, Any]]:
    """
    Parse metadata from an issue comment body.
    Tries plain JSON first, then falls back to DT-METADATA wrapper for
    backward compatibility.
    """
    text = comment_body.strip()

    # Try plain JSON (new format: first comment is just JSON)
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "parts" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: legacy DT-METADATA HTML comment wrapper
    import re
    pattern = re.compile(
        r'<!--\s*DT-METADATA\s*(.*?)\s*DT-METADATA\s*-->',
        re.DOTALL
    )
    match = pattern.search(text)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def find_metadata_in_comments(comments: List[Dict[str, Any]]
                              ) -> Optional[Dict[str, Any]]:
    """
    Find metadata in issue comments.
    Checks the first comment first (expected location), then scans all.
    """
    if not comments:
        return None

    # Check first comment (where push.py puts it)
    first = parse_metadata_comment(comments[0].get("body", ""))
    if first:
        return first

    # Scan remaining comments as fallback
    for comment in comments[1:]:
        metadata = parse_metadata_comment(comment.get("body", ""))
        if metadata:
            return metadata

    return None
