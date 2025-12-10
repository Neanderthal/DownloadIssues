#!/bin/bash

# Script to hex-decode, join, decrypt, and extract files
# Usage: ./decrypt-restore.sh <prefix> [-k <gpg_key>]

set -e

# Default GPG key (optional, GPG will auto-detect)
GPG_KEY=""

# Parse arguments
PREFIX=""
while [[ $# -gt 0 ]]; do
    case $1 in
        -k|--key)
            GPG_KEY="$2"
            shift 2
            ;;
        *)
            if [ -z "$PREFIX" ]; then
                PREFIX="$1"
            else
                echo "Error: Unexpected argument '$1'"
                echo "Usage: $0 <prefix> [-k <gpg_key>]"
                exit 1
            fi
            shift
            ;;
    esac
done

if [ -z "$PREFIX" ]; then
    echo "Usage: $0 <prefix> [-k <gpg_key>]"
    echo "  <prefix>     Prefix of the encrypted files (e.g., myfile_20231215_143022)"
    echo "  -k, --key    GPG key to use for decryption (optional, auto-detected by default)"
    echo ""
    echo "Example: $0 myfile_20231215_143022"
    echo "Example: $0 myfile_20231215_143022 -k neanderthal"
    exit 1
fi

# Find all hex files matching the prefix
HEX_FILES=(${PREFIX}*.hex)

if [ ${#HEX_FILES[@]} -eq 0 ]; then
    echo "Error: No hex files found with prefix '$PREFIX'"
    exit 1
fi

echo "Found ${#HEX_FILES[@]} hex file(s)"

echo "Step 1: Converting from hex with xxd..."
for hex_file in "${HEX_FILES[@]}"; do
    binary_file="${hex_file%.hex}"
    xxd -r -p "$hex_file" > "$binary_file"
    echo "Decoded: $binary_file"
done

echo "Step 2: Joining parts if necessary..."
# Check if there are part files
PART_FILES=(${PREFIX}*.part_*)
if [ ${#PART_FILES[@]} -gt 0 ]; then
    # Filter out .hex files
    BINARY_PARTS=()
    for file in "${PART_FILES[@]}"; do
        if [[ ! "$file" == *.hex ]]; then
            BINARY_PARTS+=("$file")
        fi
    done

    if [ ${#BINARY_PARTS[@]} -gt 0 ]; then
        echo "Joining ${#BINARY_PARTS[@]} parts..."
        ENCRYPTED_FILE="${PREFIX}.tar.gz.gpg"
        cat $(printf '%s\n' "${BINARY_PARTS[@]}" | sort) > "$ENCRYPTED_FILE"

        # Cleanup parts
        for part in "${BINARY_PARTS[@]}"; do
            rm "$part"
        done
    fi
else
    ENCRYPTED_FILE="${PREFIX}.tar.gz.gpg"
fi

echo "Step 3: Decrypting with GPG..."
if [ -n "$GPG_KEY" ]; then
    echo "Using key: $GPG_KEY"
    gpg --try-secret-key "$GPG_KEY" -d "$ENCRYPTED_FILE" > "${PREFIX}.tar.gz"
else
    gpg -d "$ENCRYPTED_FILE" > "${PREFIX}.tar.gz"
fi

echo "Step 4: Extracting tar.gz..."
tar xzf "${PREFIX}.tar.gz"

# Cleanup
rm "$ENCRYPTED_FILE"
rm "${PREFIX}.tar.gz"

echo ""
echo "Done! File(s) extracted successfully."
echo "You can remove the .hex files if no longer needed:"
echo "rm ${PREFIX}*.hex"
