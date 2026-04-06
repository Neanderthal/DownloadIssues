#!/usr/bin/env python3
"""
Local FastAPI backend for the Chrome extension.

Wraps the existing push/pull pipeline with HTTP endpoints + SSE progress.
Run: uv run server.py
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from dotenv import load_dotenv

load_dotenv(override=True)

from lib.config import (
    PROVIDER, GPG_KEY, TRANSFER_LABEL, TITLE_PREFIX,
    HEX_CHARS_PER_CHUNK, EXTRACTED_DIR,
    get_repo_for_provider,
)
from lib.provider import get_provider
from lib.crypto import full_encrypt_pipeline, full_decrypt_pipeline
from lib.metadata import (
    generate_metadata_comment, generate_issue_title,
    find_metadata_in_comments, parse_metadata_comment,
)

app = FastAPI(title="DT Encrypted Transfer")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(chrome-extension://.*|http://127\.0\.0\.1.*|http://localhost.*)",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple lock to prevent concurrent operations
_operation_lock = asyncio.Lock()


# -- Models --

class PushRequest(BaseModel):
    input_path: str
    provider: str | None = None
    gpg_key: str | None = None
    delay: float = 2.0


class PullRequest(BaseModel):
    issue_number: int
    output_dir: str | None = None
    provider: str | None = None
    force: bool = False


# -- SSE helper --

def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# -- Endpoints --

@app.get("/api/health")
def health():
    provider = PROVIDER
    repo = get_repo_for_provider(provider)
    return {"status": "ok", "provider": provider, "repo": repo}


@app.get("/api/config")
def config():
    from lib.config import (
        GITHUB_TOKEN, GITHUB_REPO, GITFLIC_TOKEN, GITFLIC_PROJECT,
    )
    return {
        "provider": PROVIDER,
        "gpg_key": GPG_KEY,
        "github_repo": GITHUB_REPO,
        "gitflic_project": GITFLIC_PROJECT,
        "has_github_token": bool(GITHUB_TOKEN),
        "has_gitflic_token": bool(GITFLIC_TOKEN),
    }


@app.get("/api/issues")
async def list_issues(provider: str | None = Query(default=None)):
    """List data-transfer issues."""
    provider_name = provider or PROVIDER
    prov = get_provider(provider_name)
    repo = get_repo_for_provider(provider_name)

    if not repo:
        return {"error": f"Repo not configured for {provider_name}", "issues": []}

    issues = await asyncio.to_thread(prov.fetch_open_issues, repo)

    dt_issues = []
    for issue in issues:
        title = issue.get("title", "")
        labels = [l["name"] for l in issue.get("labels", [])]
        if title.startswith(TITLE_PREFIX) or TRANSFER_LABEL in labels:
            dt_issues.append({
                "number": issue["number"],
                "title": title,
                "labels": labels,
                "updated_at": issue.get("updated_at", ""),
                "body_length": len(issue.get("body") or ""),
            })

    return {"provider": provider_name, "repo": repo, "issues": dt_issues}


@app.post("/api/push")
async def push(req: PushRequest):
    """Encrypt and push a file/folder. Returns SSE stream."""
    return StreamingResponse(
        _push_stream(req), media_type="text/event-stream",
    )


async def _push_stream(req: PushRequest) -> AsyncGenerator[str, None]:
    if _operation_lock.locked():
        yield sse_event({"stage": "error", "message": "Another operation in progress"})
        return

    async with _operation_lock:
        provider_name = req.provider or PROVIDER
        repo = get_repo_for_provider(provider_name)
        gpg_key = req.gpg_key or GPG_KEY

        if not repo:
            yield sse_event({"stage": "error",
                             "message": f"Repo not configured for {provider_name}"})
            return

        input_path = Path(req.input_path)
        if not input_path.exists():
            yield sse_event({"stage": "error",
                             "message": f"Path not found: {input_path}"})
            return

        # Step 1: Encrypt
        yield sse_event({"stage": "encrypting",
                         "detail": f"tar + gpg + hex for {input_path.name}"})

        try:
            chunks, metadata = await asyncio.to_thread(
                full_encrypt_pipeline, str(input_path), gpg_key,
                HEX_CHARS_PER_CHUNK,
            )
        except Exception as e:
            yield sse_event({"stage": "error", "message": f"Encrypt failed: {e}"})
            return

        total_chars = sum(len(c) for c in chunks)
        yield sse_event({
            "stage": "encrypted",
            "chunks": len(chunks),
            "total_chars": total_chars,
            "archive_md5": metadata["archive_md5"],
        })

        # Step 2: Upload
        provider = get_provider(provider_name)
        filename = input_path.name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        comment_body = generate_metadata_comment(
            filename=filename, timestamp=timestamp, gpg_key=gpg_key,
            total_parts=len(chunks), parts=metadata["parts"],
            archive_md5=metadata["archive_md5"],
            total_hex_chars=total_chars,
        )

        try:
            if provider.chunks_in_comments:
                # GitFlic: metadata in body, chunks as comments
                title = generate_issue_title(filename, timestamp)
                yield sse_event({"stage": "creating_issue", "title": title})

                issue_data = await asyncio.to_thread(
                    provider.create_issue, repo, title, comment_body)
                issue_number = issue_data["number"]
                issue_url = issue_data.get("html_url", "")

                yield sse_event({"stage": "issue_created",
                                 "issue_number": issue_number, "url": issue_url})

                for i, chunk in enumerate(chunks):
                    yield sse_event({"stage": "uploading",
                                     "chunk": i, "total": len(chunks),
                                     "chars": len(chunk)})
                    await asyncio.to_thread(
                        provider.add_issue_comment, repo, issue_number, chunk)
                    if req.delay > 0 and i < len(chunks) - 1:
                        await asyncio.sleep(req.delay)
            else:
                # GitHub: body edits for chunks, comment for metadata
                title = generate_issue_title(filename, timestamp)
                yield sse_event({"stage": "creating_issue", "title": title})

                issue_data = await asyncio.to_thread(
                    provider.create_issue, repo, title, chunks[0],
                    [TRANSFER_LABEL])
                issue_number = issue_data["number"]
                issue_url = issue_data.get("html_url", "")

                yield sse_event({"stage": "issue_created",
                                 "issue_number": issue_number, "url": issue_url})
                yield sse_event({"stage": "uploading",
                                 "chunk": 0, "total": len(chunks),
                                 "chars": len(chunks[0])})

                for i in range(1, len(chunks)):
                    if req.delay > 0:
                        await asyncio.sleep(req.delay)
                    yield sse_event({"stage": "uploading",
                                     "chunk": i, "total": len(chunks),
                                     "chars": len(chunks[i])})
                    await asyncio.to_thread(
                        provider.update_issue_body, repo, issue_number, chunks[i])

                yield sse_event({"stage": "posting_metadata"})
                await asyncio.to_thread(
                    provider.add_issue_comment, repo, issue_number, comment_body)

                try:
                    await asyncio.to_thread(
                        provider.add_issue_labels, repo, issue_number, ["complete"])
                except Exception:
                    pass

        except Exception as e:
            yield sse_event({"stage": "error", "message": f"Upload failed: {e}"})
            return

        yield sse_event({
            "stage": "done",
            "issue_number": issue_number,
            "url": issue_url,
            "chunks": len(chunks),
        })


@app.post("/api/pull")
async def pull(req: PullRequest):
    """Download and decrypt an issue. Returns SSE stream."""
    return StreamingResponse(
        _pull_stream(req), media_type="text/event-stream",
    )


async def _pull_stream(req: PullRequest) -> AsyncGenerator[str, None]:
    if _operation_lock.locked():
        yield sse_event({"stage": "error", "message": "Another operation in progress"})
        return

    async with _operation_lock:
        provider_name = req.provider or PROVIDER
        repo = get_repo_for_provider(provider_name)

        if not repo:
            yield sse_event({"stage": "error",
                             "message": f"Repo not configured for {provider_name}"})
            return

        provider = get_provider(provider_name)
        issue_number = req.issue_number
        output_dir = Path(req.output_dir or EXTRACTED_DIR)

        # Step 1: Metadata
        yield sse_event({"stage": "fetching_metadata", "issue": issue_number})

        try:
            metadata = await asyncio.to_thread(
                _get_metadata_sync, provider, repo, issue_number)
        except Exception as e:
            yield sse_event({"stage": "warning",
                             "message": f"Metadata fetch error: {e}"})
            metadata = None

        if metadata:
            yield sse_event({
                "stage": "metadata",
                "filename": metadata.get("filename", "?"),
                "total_parts": metadata.get("total_parts", "?"),
                "archive_md5": metadata.get("archive_md5", "?"),
            })
        else:
            yield sse_event({"stage": "metadata", "filename": None,
                             "message": "No metadata (legacy issue)"})

        # Step 2: Fetch chunks
        yield sse_event({"stage": "fetching_chunks"})

        try:
            chunks, verified = await asyncio.to_thread(
                _extract_chunks_sync, provider, repo, issue_number, metadata)
        except Exception as e:
            yield sse_event({"stage": "error",
                             "message": f"Chunk fetch failed: {e}"})
            return

        if not chunks:
            yield sse_event({"stage": "error",
                             "message": "No hex data found in this issue"})
            return

        total_chars = sum(len(c) for c in chunks)
        yield sse_event({
            "stage": "chunks_fetched",
            "count": len(chunks),
            "total_chars": total_chars,
            "verified": verified,
        })

        if metadata and not verified and not req.force:
            yield sse_event({"stage": "error",
                             "message": "MD5 mismatch — use force to proceed"})
            return

        # Step 3: Decrypt
        if metadata:
            filename = metadata.get("filename", f"issue_{issue_number}")
            timestamp = metadata.get("timestamp",
                                     datetime.now().strftime("%Y%m%d_%H%M%S"))
        else:
            filename = f"issue_{issue_number:04d}"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        issue_output = output_dir / f"{filename}_{timestamp}"
        yield sse_event({"stage": "decrypting", "output": str(issue_output)})

        try:
            await asyncio.to_thread(
                full_decrypt_pipeline, chunks, str(issue_output), batch=True)
        except Exception as e:
            yield sse_event({"stage": "error",
                             "message": f"Decryption failed: {e}"})
            return

        yield sse_event({
            "stage": "done",
            "output_path": str(issue_output.absolute()),
            "filename": filename,
            "chunks": len(chunks),
        })


# -- Sync helpers (reused from pull.py logic) --

def _get_metadata_sync(provider, repo, issue_number):
    if provider.chunks_in_comments:
        _, body = provider.fetch_chunks(repo, issue_number)
        if body:
            return parse_metadata_comment(body)
        return None
    else:
        comments = provider.get_issue_comments(repo, issue_number)
        return find_metadata_in_comments(comments)


def _extract_chunks_sync(provider, repo, issue_number, metadata):
    """Extract and verify chunks — adapted from pull.py."""
    from lib.integrity import compute_md5_str

    raw_chunks, _ = provider.fetch_chunks(repo, issue_number)

    if metadata and "parts" in metadata:
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
                missing.append(part.get("suffix", "?"))

        verified = len(missing) == 0
        return chunks, verified
    else:
        seen = set()
        chunks = []
        for chunk in raw_chunks:
            if chunk not in seen:
                seen.add(chunk)
                chunks.append(chunk)
        return chunks, False


# -- Crypto-only endpoints (for hybrid JS mode) --

class EncryptRequest(BaseModel):
    input_path: str
    gpg_key: str | None = None


class DecryptRequest(BaseModel):
    hex_chunks: list[str]
    output_dir: str | None = None
    filename: str | None = None


@app.post("/api/encrypt")
async def encrypt(req: EncryptRequest):
    """Encrypt a local file/folder (by path) → return hex chunks + metadata JSON."""
    gpg_key = req.gpg_key or GPG_KEY
    input_path = Path(req.input_path)

    if not input_path.exists():
        return JSONResponse(
            status_code=400,
            content={"error": f"Path not found: {input_path}"},
        )

    try:
        chunks, metadata = await asyncio.to_thread(
            full_encrypt_pipeline, str(input_path), gpg_key,
            HEX_CHARS_PER_CHUNK,
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Encrypt failed: {e}"},
        )

    filename = input_path.name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    total_chars = sum(len(c) for c in chunks)

    metadata_body = generate_metadata_comment(
        filename=filename, timestamp=timestamp, gpg_key=gpg_key,
        total_parts=len(chunks), parts=metadata["parts"],
        archive_md5=metadata["archive_md5"],
        total_hex_chars=total_chars,
    )

    return {
        "chunks": chunks,
        "metadata": metadata_body,
        "filename": filename,
        "timestamp": timestamp,
        "total_parts": len(chunks),
        "total_hex_chars": total_chars,
        "archive_md5": metadata["archive_md5"],
    }


@app.post("/api/encrypt-upload")
async def encrypt_upload(
    files: list[UploadFile] = File(...),
    gpg_key: str = Form(default=""),
):
    """Encrypt uploaded file(s) → return hex chunks + metadata JSON.

    Single file: encrypts that file directly.
    Multiple files (folder upload): recreates directory structure in a temp dir,
    then encrypts the whole folder.
    """
    key = gpg_key or GPG_KEY
    tmp_dir = tempfile.mkdtemp(prefix="dt_upload_")

    try:
        if len(files) == 1 and "/" not in (files[0].filename or ""):
            # Single file — write directly
            f = files[0]
            filename = f.filename or "upload"
            tmp_path = os.path.join(tmp_dir, filename)
            content = await f.read()
            with open(tmp_path, "wb") as fh:
                fh.write(content)
            encrypt_target = tmp_path
        else:
            # Multiple files (folder) — recreate directory structure
            # filenames come as "folder/sub/file.txt" via webkitRelativePath
            folder_name = None
            for f in files:
                rel_path = f.filename or "file"
                if not folder_name:
                    folder_name = rel_path.split("/")[0]
                dest = os.path.join(tmp_dir, rel_path)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                content = await f.read()
                with open(dest, "wb") as fh:
                    fh.write(content)
            filename = folder_name or "folder"
            encrypt_target = os.path.join(tmp_dir, filename)

        chunks, metadata = await asyncio.to_thread(
            full_encrypt_pipeline, encrypt_target, key, HEX_CHARS_PER_CHUNK,
        )
    except Exception as e:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Encrypt failed: {e}"},
        )

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    total_chars = sum(len(c) for c in chunks)

    metadata_body = generate_metadata_comment(
        filename=filename, timestamp=timestamp, gpg_key=key,
        total_parts=len(chunks), parts=metadata["parts"],
        archive_md5=metadata["archive_md5"],
        total_hex_chars=total_chars,
    )

    return {
        "chunks": chunks,
        "metadata": metadata_body,
        "filename": filename,
        "timestamp": timestamp,
        "total_parts": len(chunks),
        "total_hex_chars": total_chars,
        "archive_md5": metadata["archive_md5"],
    }


@app.post("/api/decrypt")
async def decrypt(req: DecryptRequest):
    """Decrypt hex chunks → extract to output_dir."""
    output_dir = Path(req.output_dir or EXTRACTED_DIR)
    filename = req.filename or "download"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    issue_output = output_dir / f"{filename}_{timestamp}"

    try:
        await asyncio.to_thread(
            full_decrypt_pipeline, req.hex_chunks, str(issue_output), batch=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": f"Decryption failed: {e}"},
        )

    return {
        "output_path": str(issue_output.absolute()),
        "filename": filename,
    }


if __name__ == "__main__":
    import uvicorn
    print("Starting DT server on http://127.0.0.1:9741")
    print("Press Ctrl+C to stop")
    uvicorn.run(app, host="127.0.0.1", port=9741)
