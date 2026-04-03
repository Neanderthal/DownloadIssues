# CLAUDE.md

Bidirectional encrypted data tunnel through GitHub/GitFlic Issues.

## Key Commands

```bash
uv sync                              # install deps
python pull.py list                  # list data-transfer issues
python pull.py issue <N> [-o DIR]    # download + verify + decrypt
python push.py <path> [--dry-run]    # encrypt + push to issue
uv run server.py                     # start local API server for Chrome extension
```

## Architecture

- `lib/` — shared library: config, crypto, integrity, metadata, provider, github_api, gitflic_api
- `pull.py` / `push.py` — CLI pipeline (supports both GitHub and GitFlic)
- `server.py` — FastAPI backend on `127.0.0.1:9741` for Chrome extension (crypto-only endpoints)
- `extension/` — Chrome Manifest V3 extension (hybrid mode: JS handles API, server handles crypto)

## Data Format

- Pipeline: `tar.gz → GPG encrypt → xxd hex → split at 62,464 chars`
- **GitHub**: chunks as issue body edits, metadata in first comment
- **GitFlic**: metadata in issue body, chunks as comments (no edit history API)
- Metadata stored as plain JSON with MD5 checksums per chunk

## Rules

See `.claude/rules/` for detailed rules (if present).
