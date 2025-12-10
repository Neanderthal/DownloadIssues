#!/bin/bash

# Script to archive, encrypt, split, and hex-encode a file
# Usage: ./archive-encrypt.sh <input_file> [-k <gpg_key>]

set -e

# Default GPG key
GPG_KEY="neanderthal"

# Parse arguments
INPUT_FILE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        -k|--key)
            GPG_KEY="$2"
            shift 2
            ;;
        *)
            if [ -z "$INPUT_FILE" ]; then
                INPUT_FILE="$1"
            else
                echo "Error: Unexpected argument '$1'"
                echo "Usage: $0 <input_file> [-k <gpg_key>]"
                exit 1
            fi
            shift
            ;;
    esac
done

if [ -z "$INPUT_FILE" ]; then
    echo "Usage: $0 <input_file> [-k <gpg_key>]"
    echo ""
    echo "Arguments:"
    echo "  <input_file> Path to file to archive and encrypt"
    echo "  -k, --key    GPG key to use for encryption (default: neanderthal)"
    echo ""
    echo "Output format:"
    echo "  Creates: <filename>_<timestamp>.tar.gz.gpg.hex"
    echo "  If file > 50KB, creates multiple parts:"
    echo "    <filename>_<timestamp>.tar.gz.gpg.part_aa.hex"
    echo "    <filename>_<timestamp>.tar.gz.gpg.part_ab.hex"
    echo "    ..."
    echo ""
    echo "Examples:"
    echo "  $0 myfile.txt"
    echo "  $0 /path/to/document.pdf -k mykey"
    exit 1
fi
BASENAME=$(basename "$INPUT_FILE")
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_PREFIX="${BASENAME}_${TIMESTAMP}"

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: File '$INPUT_FILE' not found"
    exit 1
fi

echo "Step 1: Creating tar.gz archive..."
tar czf "${OUTPUT_PREFIX}.tar.gz" "$INPUT_FILE"

echo "Step 2: Encrypting with GPG (key: $GPG_KEY)..."
gpg -r "$GPG_KEY" -e "${OUTPUT_PREFIX}.tar.gz"

echo "Step 3: Checking file size and splitting if necessary..."
ENCRYPTED_FILE="${OUTPUT_PREFIX}.tar.gz.gpg"
FILE_SIZE=$(stat -c%s "$ENCRYPTED_FILE")
SIZE_50K=$((50 * 1024))

if [ $FILE_SIZE -gt $SIZE_50K ]; then
    echo "File size ($FILE_SIZE bytes) > 50KB, splitting..."
    split -b 50k "$ENCRYPTED_FILE" "${ENCRYPTED_FILE}.part_"
    rm "$ENCRYPTED_FILE"
    FILES_TO_HEX="${ENCRYPTED_FILE}.part_*"
else
    echo "File size ($FILE_SIZE bytes) <= 50KB, no splitting needed"
    FILES_TO_HEX="$ENCRYPTED_FILE"
fi

echo "Step 4: Converting to hex with xxd..."
for file in $FILES_TO_HEX; do
    xxd -p "$file" > "${file}.hex"
    rm "$file"
    echo "Created: ${file}.hex"
done

# Cleanup intermediate tar.gz
rm "${OUTPUT_PREFIX}.tar.gz"

echo ""
echo "Done! Output files:"
ls -lh ${OUTPUT_PREFIX}*.hex

echo ""
echo "To decrypt, use: ./decrypt-restore.sh ${OUTPUT_PREFIX}"
