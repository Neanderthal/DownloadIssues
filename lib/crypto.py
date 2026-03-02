"""Encryption/decryption pipeline: tar, gpg, hex, split via subprocess."""

import os
import subprocess
import tempfile
from typing import List, Tuple

from lib.config import GPG_KEY, HEX_CHARS_PER_CHUNK


def clean_hex_data(text: str) -> str:
    """
    Extract and clean hex data from diff/body text.
    Removes non-hex characters, markdown formatting, whitespace.
    """
    lines = text.split('\n')
    hex_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(('#', '```', '---', '*', '<!--', 'DT-METADATA')):
            continue

        cleaned = ''.join(c for c in line if c in '0123456789abcdefABCDEF')
        if cleaned:
            hex_lines.append(cleaned)

    return ''.join(hex_lines)


def generate_part_suffix(index: int) -> str:
    """Generate part suffix: part_aa, part_ab, ... part_zz."""
    first = index // 26
    second = index % 26
    return f"part_{chr(ord('a') + first)}{chr(ord('a') + second)}"


def split_hex_text(hex_str: str, chunk_size: int = HEX_CHARS_PER_CHUNK) -> List[str]:
    """Split hex string into chunks of exactly chunk_size characters."""
    chunks = []
    for i in range(0, len(hex_str), chunk_size):
        chunks.append(hex_str[i:i + chunk_size])
    return chunks


def tar_compress(input_path: str, output_path: str) -> None:
    """Create a tar.gz archive of input_path."""
    parent = os.path.dirname(os.path.abspath(input_path))
    basename = os.path.basename(input_path)
    subprocess.run(
        ["tar", "czf", output_path, "-C", parent, basename],
        check=True,
    )


def gpg_encrypt(input_path: str, output_path: str,
                gpg_key: str = GPG_KEY) -> None:
    """Encrypt a file with GPG."""
    subprocess.run(
        ["gpg", "--batch", "--yes", "-r", gpg_key, "-e",
         "-o", output_path, input_path],
        check=True,
    )


def gpg_decrypt(input_path: str, output_path: str) -> None:
    """Decrypt a GPG-encrypted file. Allows gpg-agent passphrase prompt."""
    with open(output_path, 'wb') as out_f:
        subprocess.run(
            ["gpg", "--yes", "-d", input_path],
            check=True,
            stdout=out_f,
        )


def tar_extract(archive_path: str, output_dir: str) -> None:
    """Extract a tar.gz archive."""
    os.makedirs(output_dir, exist_ok=True)
    subprocess.run(
        ["tar", "xzf", archive_path, "-C", output_dir],
        check=True,
    )


def binary_to_hex(input_path: str) -> str:
    """Convert binary file to hex string using xxd."""
    result = subprocess.run(
        ["xxd", "-p", input_path],
        check=True,
        capture_output=True,
    )
    # xxd outputs with newlines; strip them for a continuous hex string
    return result.stdout.decode('ascii').replace('\n', '').strip()


def hex_to_binary(hex_str: str, output_path: str) -> None:
    """Convert hex string to binary file using xxd."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.hex',
                                     delete=False) as tmp:
        tmp.write(hex_str)
        tmp_path = tmp.name

    try:
        with open(output_path, 'wb') as out_f:
            subprocess.run(
                ["xxd", "-r", "-p", tmp_path],
                check=True,
                stdout=out_f,
            )
    finally:
        os.unlink(tmp_path)


def full_encrypt_pipeline(input_path: str,
                          gpg_key: str = GPG_KEY,
                          chunk_size: int = HEX_CHARS_PER_CHUNK
                          ) -> Tuple[List[str], dict]:
    """
    Full encrypt pipeline: tar.gz -> gpg encrypt -> hex encode -> split.

    Returns:
        (hex_chunks, metadata_dict) where metadata_dict has archive_md5, etc.
    """
    from lib.integrity import compute_md5_bytes, compute_md5_file

    with tempfile.TemporaryDirectory() as tmpdir:
        tar_path = os.path.join(tmpdir, "archive.tar.gz")
        gpg_path = os.path.join(tmpdir, "archive.tar.gz.gpg")

        tar_compress(input_path, tar_path)
        gpg_encrypt(tar_path, gpg_path, gpg_key)

        archive_md5 = compute_md5_file(gpg_path)
        hex_str = binary_to_hex(gpg_path)

    chunks = split_hex_text(hex_str, chunk_size)

    parts_meta = []
    for i, chunk in enumerate(chunks):
        parts_meta.append({
            "index": i,
            "suffix": generate_part_suffix(i),
            "md5": compute_md5_bytes(chunk.encode('ascii')),
            "hex_chars": len(chunk),
        })

    metadata = {
        "total_parts": len(chunks),
        "total_hex_chars": len(hex_str),
        "parts": parts_meta,
        "archive_md5": archive_md5,
    }

    return chunks, metadata


def full_decrypt_pipeline(hex_chunks: List[str],
                          output_dir: str) -> str:
    """
    Full decrypt pipeline: join hex -> binary -> gpg decrypt -> tar extract.

    Returns path to extracted output directory.
    """
    hex_str = ''.join(hex_chunks)

    with tempfile.TemporaryDirectory() as tmpdir:
        gpg_path = os.path.join(tmpdir, "archive.tar.gz.gpg")
        tar_path = os.path.join(tmpdir, "archive.tar.gz")

        hex_to_binary(hex_str, gpg_path)
        gpg_decrypt(gpg_path, tar_path)
        tar_extract(tar_path, output_dir)

    return output_dir
