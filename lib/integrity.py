"""MD5/SHA256 hashing and verification for data transfer integrity."""

import hashlib
from typing import List, Dict, Tuple


def compute_md5_file(file_path: str) -> str:
    """Compute MD5 hash of a file."""
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


def compute_md5_bytes(data: bytes) -> str:
    """Compute MD5 hash of bytes."""
    return hashlib.md5(data).hexdigest()


def compute_md5_str(text: str) -> str:
    """Compute MD5 hash of a string (encoded as ASCII)."""
    return hashlib.md5(text.encode('ascii')).hexdigest()


def verify_part_md5s(chunks: List[str],
                     expected: List[Dict]) -> Tuple[bool, List[str]]:
    """
    Verify MD5 of each hex chunk against expected manifest data.

    When chunks are already matched by MD5 (metadata-based extraction),
    verifies each chunk against its corresponding part. Extra or missing
    chunks are reported but don't block verification of what we have.

    Args:
        chunks: list of hex strings (ordered by metadata matching)
        expected: list of dicts with 'index', 'md5', 'hex_chars' keys

    Returns:
        (all_ok, list_of_error_messages)
    """
    errors = []

    # Verify chunks we have against their corresponding expected parts
    for i, (chunk, exp) in enumerate(zip(chunks, expected)):
        actual_md5 = compute_md5_bytes(chunk.encode('ascii'))
        exp_md5 = exp.get("md5", "")

        if actual_md5 != exp_md5:
            errors.append(
                f"Part {i} ({exp.get('suffix', '?')}): MD5 mismatch "
                f"(got {actual_md5}, expected {exp_md5})")

        exp_chars = exp.get("hex_chars", 0)
        if exp_chars and len(chunk) != exp_chars:
            errors.append(
                f"Part {i} ({exp.get('suffix', '?')}): size mismatch "
                f"(got {len(chunk)} chars, expected {exp_chars})")

    # Report count issues
    if len(chunks) < len(expected):
        missing = [
            f"{e.get('suffix', '?')} ({e.get('hex_chars', '?')} chars)"
            for e in expected[len(chunks):]
        ]
        errors.append(
            f"Missing {len(expected) - len(chunks)} chunk(s): "
            f"{', '.join(missing)}")

    return len(errors) == 0, errors


def generate_md5_manifest(chunks: List[str]) -> List[Dict]:
    """Generate MD5 manifest entries for a list of hex chunks."""
    from lib.crypto import generate_part_suffix

    parts = []
    for i, chunk in enumerate(chunks):
        parts.append({
            "index": i,
            "suffix": generate_part_suffix(i),
            "md5": compute_md5_bytes(chunk.encode('ascii')),
            "hex_chars": len(chunk),
        })
    return parts
