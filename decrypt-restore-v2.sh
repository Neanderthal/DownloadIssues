#!/bin/bash

# Decrypt and restore files from pull.py hex output
# Usage: ./decrypt-restore-v2.sh <prefix_or_dir> [-k <gpg_key>]
#
# Handles the pull.py output format:
#   prefix.tar.gz.gpg.part_aa.hex  (continuous hex string per file)
#   prefix.tar.gz.gpg.part_ab.hex
#   ...
# Or single-chunk:
#   prefix.tar.gz.gpg.hex
#
# Hex files are concatenated in sort order, decoded to binary, then
# GPG-decrypted and tar-extracted.

set -e

GPG_KEY=""
INPUT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -k|--key)
            GPG_KEY="$2"
            shift 2
            ;;
        *)
            if [ -z "$INPUT" ]; then
                INPUT="$1"
            else
                echo "Error: Unexpected argument '$1'"
                echo "Usage: $0 <prefix_or_dir> [-k <gpg_key>]"
                exit 1
            fi
            shift
            ;;
    esac
done

if [ -z "$INPUT" ]; then
    echo "Usage: $0 <prefix_or_dir> [-k <gpg_key>]"
    echo ""
    echo "Arguments:"
    echo "  <prefix_or_dir>  Directory containing .hex files, or file prefix."
    echo "                   Accepts any of:"
    echo "                     ./extracted/backend_20260310_190545/"
    echo "                     backend_20260310_190545"
    echo "                     backend_20260310_190545.tar.gz.gpg.part_aa.hex"
    echo "  -k, --key        GPG key for decryption (optional, auto-detected)"
    echo ""
    echo "Examples:"
    echo "  $0 extracted/backend_20260310_190545/"
    echo "  $0 backend_20260310_190545 -k neanderthal"
    exit 1
fi

# If input is a directory, find the prefix from hex files inside it
if [ -d "$INPUT" ]; then
    DIR="$INPUT"
    shopt -s nullglob
    FIRST_HEX=("${DIR}"/*.hex)
    shopt -u nullglob
    if [ ${#FIRST_HEX[@]} -eq 0 ]; then
        echo "Error: No .hex files found in '$DIR'"
        exit 1
    fi
    # Extract prefix from first hex file
    BASENAME=$(basename "${FIRST_HEX[0]}")
    # Strip .tar.gz.gpg.* suffix to get the base prefix
    PREFIX="${BASENAME%.tar.gz.gpg*}"
    WORK_DIR="$DIR"
else
    # Input is a prefix or filename — extract prefix
    # Strip common suffixes
    PREFIX="$INPUT"
    PREFIX="${PREFIX%.hex}"
    PREFIX="${PREFIX%.tar.gz.gpg.part_*}"
    PREFIX="${PREFIX%.tar.gz.gpg}"
    # Work in the directory containing the file
    if [[ "$PREFIX" == */* ]]; then
        WORK_DIR=$(dirname "$PREFIX")
        PREFIX=$(basename "$PREFIX")
    else
        WORK_DIR="."
    fi
fi

echo "Prefix: $PREFIX"
echo "Directory: $WORK_DIR"

# Find hex files
shopt -s nullglob
HEX_FILES=("${WORK_DIR}/${PREFIX}"*.hex)
shopt -u nullglob

if [ ${#HEX_FILES[@]} -eq 0 ]; then
    echo "Error: No hex files found for prefix '$PREFIX' in '$WORK_DIR'"
    exit 1
fi

# Sort hex files to ensure correct order (part_aa, part_ab, ...)
IFS=$'\n' HEX_FILES=($(printf '%s\n' "${HEX_FILES[@]}" | sort)); unset IFS

echo "Found ${#HEX_FILES[@]} hex file(s):"
for f in "${HEX_FILES[@]}"; do
    echo "  $(basename "$f") ($(wc -c < "$f") chars)"
done

# Step 1: Concatenate all hex chunks and decode to binary in one pass
ENCRYPTED_FILE="${WORK_DIR}/${PREFIX}.tar.gz.gpg"
echo ""
echo "Step 1: Decoding hex to binary..."
cat "${HEX_FILES[@]}" | xxd -r -p > "$ENCRYPTED_FILE"
echo "  Created: $ENCRYPTED_FILE ($(wc -c < "$ENCRYPTED_FILE") bytes)"

# Step 2: Verify archive MD5 if we can find it
ARCHIVE_MD5=""
# Check for manifest.json alongside hex files
MANIFEST="${WORK_DIR}/${PREFIX}.manifest.json"
if [ -f "$MANIFEST" ] && command -v python3 &>/dev/null; then
    ARCHIVE_MD5=$(python3 -c "import json; print(json.load(open('$MANIFEST')).get('archive_md5',''))" 2>/dev/null || true)
fi
if [ -n "$ARCHIVE_MD5" ]; then
    ACTUAL_MD5=$(md5sum "$ENCRYPTED_FILE" | awk '{print $1}')
    if [ "$ACTUAL_MD5" = "$ARCHIVE_MD5" ]; then
        echo "  Archive MD5 verified: $ACTUAL_MD5"
    else
        echo "  WARNING: Archive MD5 mismatch!"
        echo "    Expected: $ARCHIVE_MD5"
        echo "    Got:      $ACTUAL_MD5"
        read -p "  Continue anyway? [y/N] " -n 1 -r
        echo
        [[ $REPLY =~ ^[Yy]$ ]] || exit 1
    fi
fi

# Step 3: Decrypt
echo ""
echo "Step 2: Decrypting with GPG..."
TAR_FILE="${WORK_DIR}/${PREFIX}.tar.gz"
if [ -n "$GPG_KEY" ]; then
    echo "  Using key: $GPG_KEY"
    gpg --yes --try-secret-key "$GPG_KEY" -d "$ENCRYPTED_FILE" > "$TAR_FILE"
else
    gpg --yes -d "$ENCRYPTED_FILE" > "$TAR_FILE"
fi
echo "  Decrypted: $TAR_FILE ($(wc -c < "$TAR_FILE") bytes)"

# Step 4: Extract
echo ""
echo "Step 3: Extracting archive..."
tar xzf "$TAR_FILE" -C "$WORK_DIR"

# Cleanup intermediates (keep hex files)
rm -f "$ENCRYPTED_FILE" "$TAR_FILE"

echo ""
echo "Done! Files extracted to: $WORK_DIR/"
echo "To clean up hex files: rm ${WORK_DIR}/${PREFIX}*.hex"
