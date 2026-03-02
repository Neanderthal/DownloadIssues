#!/bin/bash

# Improved archive-encrypt script with correct hex chunking and MD5 manifest
# Usage: ./archive-encrypt-v2.sh <input_path> [-k <gpg_key>]
#
# Key improvements over archive-encrypt.sh:
#   - Splits hex output at 62,464 chars (matching GitHub issue body limit)
#   - Generates per-chunk MD5 hashes + full archive MD5
#   - Outputs manifest.json alongside hex files

set -e

# Default GPG key
GPG_KEY="neanderthal"

# Hex chars per chunk (matches GitHub issue edit body limit)
HEX_CHARS_PER_CHUNK=62464

# Parse arguments
INPUT_PATH=""
while [[ $# -gt 0 ]]; do
    case $1 in
        -k|--key)
            GPG_KEY="$2"
            shift 2
            ;;
        *)
            if [ -z "$INPUT_PATH" ]; then
                INPUT_PATH="$1"
            else
                echo "Error: Unexpected argument '$1'"
                echo "Usage: $0 <input_path> [-k <gpg_key>]"
                exit 1
            fi
            shift
            ;;
    esac
done

if [ -z "$INPUT_PATH" ]; then
    echo "Usage: $0 <input_path> [-k <gpg_key>]"
    echo ""
    echo "Arguments:"
    echo "  <input_path> Path to file or folder to archive and encrypt"
    echo "  -k, --key    GPG key to use for encryption (default: neanderthal)"
    echo ""
    echo "Output format:"
    echo "  Creates hex files split at $HEX_CHARS_PER_CHUNK chars per chunk:"
    echo "    <name>_<timestamp>.tar.gz.gpg.part_aa.hex"
    echo "    <name>_<timestamp>.tar.gz.gpg.part_ab.hex"
    echo "    ..."
    echo "    <name>_<timestamp>.manifest.json"
    echo ""
    echo "Examples:"
    echo "  $0 myfile.txt"
    echo "  $0 /path/to/folder -k mykey"
    exit 1
fi

if [ ! -e "$INPUT_PATH" ]; then
    echo "Error: Path '$INPUT_PATH' not found"
    exit 1
fi

BASENAME=$(basename "$INPUT_PATH")
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_PREFIX="${BASENAME}_${TIMESTAMP}"

echo "Step 1: Creating tar.gz archive..."
tar czf "${OUTPUT_PREFIX}.tar.gz" "$INPUT_PATH"

echo "Step 2: Encrypting with GPG (key: $GPG_KEY)..."
gpg -r "$GPG_KEY" -e "${OUTPUT_PREFIX}.tar.gz"

ENCRYPTED_FILE="${OUTPUT_PREFIX}.tar.gz.gpg"

echo "Step 3: Computing archive MD5..."
ARCHIVE_MD5=$(md5sum "$ENCRYPTED_FILE" | awk '{print $1}')
echo "  Archive MD5: $ARCHIVE_MD5"

echo "Step 4: Converting to continuous hex string..."
FULL_HEX=$(xxd -p "$ENCRYPTED_FILE" | tr -d '\n')
TOTAL_HEX_CHARS=${#FULL_HEX}
echo "  Total hex chars: $TOTAL_HEX_CHARS"

echo "Step 5: Splitting hex at $HEX_CHARS_PER_CHUNK chars per chunk..."

# Calculate number of parts
NUM_PARTS=$(( (TOTAL_HEX_CHARS + HEX_CHARS_PER_CHUNK - 1) / HEX_CHARS_PER_CHUNK ))
echo "  Will create $NUM_PARTS part(s)"

# Generate parts and collect MD5s
PART_INDEX=0
OFFSET=0
MANIFEST_PARTS=""

while [ $OFFSET -lt $TOTAL_HEX_CHARS ]; do
    # Generate part suffix (aa, ab, ac, ...)
    FIRST_LETTER=$(printf "\\$(printf '%03o' $((97 + PART_INDEX / 26)))")
    SECOND_LETTER=$(printf "\\$(printf '%03o' $((97 + PART_INDEX % 26)))")
    SUFFIX="part_${FIRST_LETTER}${SECOND_LETTER}"

    # Extract chunk
    CHUNK="${FULL_HEX:$OFFSET:$HEX_CHARS_PER_CHUNK}"
    CHUNK_LEN=${#CHUNK}

    # Write hex file
    HEX_FILE="${OUTPUT_PREFIX}.tar.gz.gpg.${SUFFIX}.hex"
    echo -n "$CHUNK" > "$HEX_FILE"

    # Compute chunk MD5
    CHUNK_MD5=$(echo -n "$CHUNK" | md5sum | awk '{print $1}')

    echo "  Created: $HEX_FILE ($CHUNK_LEN chars, MD5: $CHUNK_MD5)"

    # Build manifest JSON entry
    if [ $PART_INDEX -gt 0 ]; then
        MANIFEST_PARTS="${MANIFEST_PARTS},"
    fi
    MANIFEST_PARTS="${MANIFEST_PARTS}
    {\"index\": $PART_INDEX, \"suffix\": \"$SUFFIX\", \"md5\": \"$CHUNK_MD5\", \"hex_chars\": $CHUNK_LEN, \"file\": \"$HEX_FILE\"}"

    PART_INDEX=$((PART_INDEX + 1))
    OFFSET=$((OFFSET + HEX_CHARS_PER_CHUNK))
done

echo "Step 6: Generating manifest..."

MANIFEST_FILE="${OUTPUT_PREFIX}.manifest.json"

# Try python3 for proper JSON, fall back to echo
if command -v python3 &>/dev/null; then
    echo "[${MANIFEST_PARTS}]" | python3 -c "
import json, sys
parts = json.load(sys.stdin)
manifest = {
    'version': 1,
    'filename': sys.argv[1],
    'timestamp': sys.argv[2],
    'gpg_key': sys.argv[3],
    'total_parts': int(sys.argv[4]),
    'total_hex_chars': int(sys.argv[5]),
    'parts': parts,
    'archive_md5': sys.argv[6]
}
print(json.dumps(manifest, indent=2))
" "$BASENAME" "$TIMESTAMP" "$GPG_KEY" "$NUM_PARTS" "$TOTAL_HEX_CHARS" "$ARCHIVE_MD5" > "$MANIFEST_FILE"
else
    # Plain JSON fallback
    cat > "$MANIFEST_FILE" << MANIFEST_EOF
{
  "version": 1,
  "filename": "$BASENAME",
  "timestamp": "$TIMESTAMP",
  "gpg_key": "$GPG_KEY",
  "total_parts": $NUM_PARTS,
  "total_hex_chars": $TOTAL_HEX_CHARS,
  "parts": [${MANIFEST_PARTS}
  ],
  "archive_md5": "$ARCHIVE_MD5"
}
MANIFEST_EOF
fi

echo "  Created: $MANIFEST_FILE"

# Cleanup intermediates
rm -f "${OUTPUT_PREFIX}.tar.gz" "$ENCRYPTED_FILE"

echo ""
echo "Done! Output files:"
ls -lh ${OUTPUT_PREFIX}*.hex ${MANIFEST_FILE} 2>/dev/null
echo ""
echo "To use with pull.py:"
echo "  1. Create a GitHub issue with title: [DT] $BASENAME $TIMESTAMP"
echo "  2. Paste each .hex file as successive issue body edits"
echo "  3. Paste the manifest.json content as the first comment"
echo ""
echo "To decrypt locally: ./decrypt-restore.sh ${OUTPUT_PREFIX}"
