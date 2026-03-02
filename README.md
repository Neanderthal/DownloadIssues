# GitHub Issue File Transfer System

Transfer files securely through GitHub issues using hex encoding and encryption.

This system enables **bidirectional encrypted file transfer** using GitHub issues as the transport medium. Binary files are encrypted (GPG), encoded as hex, split into chunks, and stored in issue body edits. The receiver downloads, verifies MD5 checksums, and decrypts automatically. Built with `uv` for fast, reliable dependency management.

## Features

- **One-command push/pull**: `push.py` and `pull.py` replace a 5-script manual workflow
- **Automatic MD5 verification**: per-chunk and full-archive checksums with metadata tracking
- **Correct chunking**: splits at 62,464 hex chars to match GitHub issue body limit exactly
- **Metadata in comments**: structured JSON in HTML comments for verification and tracking
- **Legacy compatible**: old scripts (`archive-encrypt.sh`, `decrypt-restore.sh`, etc.) still work
- **Cursor pagination**: handles issues with >50 edits via GraphQL pagination

## Quick Start

### 1. Install and Configure

```bash
uv sync
cp .env.example .env
# Edit .env with your GITHUB_TOKEN and GITHUB_REPO
```

### 2. Push a file (local -> GitHub)

```bash
python push.py /path/to/file_or_folder
python push.py /path/to/file --dry-run          # encrypt locally without uploading
python push.py /path/to/file -k mykey --delay 3  # custom GPG key, 3s between edits
```

### 3. Pull a file (GitHub -> local)

```bash
python pull.py list                    # show available data-transfer issues
python pull.py issue 35 -o output/     # download + verify MD5 + decrypt
python pull.py issue 35 --hex-only     # download hex without decrypting
python pull.py all                     # pull all [DT] issues
```

### 4. Server-side encrypt (for manual paste)

```bash
./archive-encrypt-v2.sh /path/to/folder -k neanderthal
# Creates .hex files + manifest.json
# Paste hex into issue body edits, manifest as first comment
```

## How It Works

```
Push (local):
  file -> tar.gz -> GPG encrypt -> hex encode -> split at 62,464 chars
       -> create GitHub issue with chunk[0] as body
       -> PATCH body with chunk[1], chunk[2], ... (creates edit history)
       -> post metadata JSON as first comment

Pull (local):
  fetch issue comments -> find metadata JSON
  fetch edit history via GraphQL (with pagination)
  extract hex chunks from reversed(edits)
  verify MD5 per-chunk (if metadata found)
  join chunks -> hex decode -> GPG decrypt -> tar extract
```

## Data Format

Each issue edit body contains exactly **62,464 hex characters** (except the last chunk which may be shorter). The full encrypted payload is reconstructed from the edit history:

- `reversed(edits)` = all chunks in order (GitHub returns newest-first)
- Current body = same as newest edit (for issues with edits)
- Single-chunk issues: body alone contains the data

Metadata is stored as an HTML comment in the first issue comment:
```
<!-- DT-METADATA
{"version":1,"filename":"myfile","timestamp":"20260303_120000",
 "gpg_key":"neanderthal","total_parts":5,
 "parts":[{"index":0,"md5":"f906...","hex_chars":62464}, ...],
 "archive_md5":"a1b2c3...","created_at":"2026-03-03T12:00:00Z"}
DT-METADATA -->
```

## Project Structure

```
DownloadIssues/
├── push.py                    # Push: encrypt + upload to GitHub issue
├── pull.py                    # Pull: download + verify + decrypt
├── lib/                       # Shared library
│   ├── config.py              # Env vars, paths, constants
│   ├── github_api.py          # REST + GraphQL client (paginated)
│   ├── crypto.py              # tar/gpg/hex/split subprocess wrappers
│   ├── integrity.py           # MD5 hashing and verification
│   └── metadata.py            # Metadata comment generate/parse
├── archive-encrypt-v2.sh      # Server-side: correct chunking + MD5 manifest
├── decrypt-restore.sh         # Manual decrypt from .hex files
├── archive-encrypt.sh         # Legacy server-side encrypt (50KB binary split)
├── download_issues.py         # Legacy: download + sync all open issues
├── extract_hex_from_edits.py  # Legacy: extract hex from edit history JSON
├── compare_md5.py             # Legacy: MD5 matching
├── reassemble_parts.sh        # Legacy: reassemble hex parts from changes/
├── pyproject.toml             # Project config + entry points
├── .env.example               # Environment template
└── data/projects/issues/      # Downloaded issues, changes, edit history
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | **Yes** | - | GitHub personal access token |
| `GITHUB_REPO` | **Yes** | - | Repository in `owner/repo` format |
| `GPG_KEY` | No | `neanderthal` | GPG key for encryption |
| `ISSUES_DIR` | No | `data/projects/issues` | Output directory for issues |

Get a token at GitHub -> Settings -> Developer settings -> [Personal access tokens](https://github.com/settings/tokens). Needs `repo` scope.

## CLI Reference

### push.py

```
python push.py <file_or_folder> [-k KEY] [--repo REPO] [--issue N] [--dry-run] [--delay SECS] [-o DIR]
```

| Flag | Description |
|------|-------------|
| `-k KEY` | GPG encryption key (default: neanderthal) |
| `--issue N` | Resume pushing to existing issue |
| `--dry-run` | Save hex + manifest locally, no API calls |
| `--delay N` | Seconds between body edits (default: 2.0) |
| `-o DIR` | Output directory for dry-run files |

### pull.py

```
python pull.py list                          # list [DT] issues
python pull.py issue <N> [-o DIR] [--force] [--hex-only] [--no-label]
python pull.py all [-o DIR] [--force]
```

| Flag | Description |
|------|-------------|
| `--force` | Proceed despite MD5 verification failure |
| `--hex-only` | Save hex files without decrypting |
| `--no-label` | Don't add 'verified' label after success |
| `-o DIR` | Output directory |

### archive-encrypt-v2.sh

```
./archive-encrypt-v2.sh <input_path> [-k <gpg_key>]
```

Outputs `*.hex` files + `*.manifest.json`. The manifest uses the same schema as the metadata comment, so `pull.py` can verify both.

## Legacy Workflow

The old multi-script workflow still works for backward compatibility:

```bash
# Download + extract + decrypt (manual, 4 steps)
uv run download-issues --fetch-edit-history
python extract_hex_from_edits.py data/projects/issues/edit_history/NNNN-slug-edits.json
cd extracted/
../decrypt-restore.sh issue_NNNN_timestamp

# Server-side (old 50KB binary split)
./archive-encrypt.sh /path/to/file
```

## Security

- Files are encrypted with GPG before transfer
- Use private repos for sensitive transfers
- Issue history is permanent on GitHub (even after deletion)
- Revoke tokens after transfer completes
- Delete issues after successful transfer to remove traces

## License

Free to use and modify.
