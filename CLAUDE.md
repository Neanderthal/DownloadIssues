# CLAUDE.md

Bidirectional encrypted data tunnel through GitHub Issues.

## Key Commands

```bash
uv sync                              # install deps
python pull.py list                  # list data-transfer issues
python pull.py issue <N> [-o DIR]    # download + verify + decrypt
python push.py <path> [--dry-run]    # encrypt + push to GitHub issue
./archive-encrypt-v2.sh <path>       # server-side: encrypt + chunk + manifest
./decrypt-restore.sh <prefix>        # manual decrypt from .hex files
```

## Architecture

- `lib/` - shared library: config, github_api, crypto, integrity, metadata
- `pull.py` / `push.py` - unified local-side pipeline (replaces 5-script manual workflow)
- `archive-encrypt-v2.sh` - server-side encrypt with correct 62,464-char hex chunking + MD5 manifest

## Data Format

- Each GitHub issue edit body = exactly 62,464 hex chars (except last chunk)
- Full data = `reversed(edits)` when edits exist, or `body` alone for single-chunk
- Metadata stored as plain JSON in first issue comment
- Pipeline: `tar.gz -> GPG encrypt -> xxd hex -> split at 62,464 chars`

## Rules

See `.claude/rules/` for detailed rules (if present).
