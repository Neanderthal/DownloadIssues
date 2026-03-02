#!/bin/bash
# Reassemble hex parts into binary file

CHANGES_DIR="data/projects/issues/changes"
OUTPUT_FILE="reassembled"

echo "🔧 Reassembling hex parts..."

# Step 0: Auto-detect available parts
echo "Step 0: Detecting available hex parts..."
PARTS=($(ls "${CHANGES_DIR}"/bck.part*.hex 2>/dev/null | sort -V))
PART_COUNT=${#PARTS[@]}

if [ $PART_COUNT -eq 0 ]; then
    echo "❌ Error: No hex parts found in ${CHANGES_DIR}"
    exit 1
fi

echo "   Found ${PART_COUNT} part(s)"
echo "   First: $(basename "${PARTS[0]}")"
echo "   Last:  $(basename "${PARTS[-1]}")"
echo ""

# Step 1: Concatenate all hex parts (removing newlines)
echo "Step 1: Concatenating hex parts (removing newlines)..."
> "${OUTPUT_FILE}.hex"  # Create empty file
for part_file in "${PARTS[@]}"; do
    echo "   Processing: $(basename "$part_file")"
    tr -d '\n' < "$part_file" >> "${OUTPUT_FILE}.hex"
done

echo "   Created: ${OUTPUT_FILE}.hex"
ls -lh "${OUTPUT_FILE}.hex"

# Step 2: Convert hex to binary
echo ""
echo "Step 2: Converting hex to binary..."
xxd -r -p "${OUTPUT_FILE}.hex" > "${OUTPUT_FILE}.bin"

echo "   Created: ${OUTPUT_FILE}.bin"
ls -lh "${OUTPUT_FILE}.bin"

# Step 3: Check file type
echo ""
echo "Step 3: Checking file type..."
file "${OUTPUT_FILE}.bin"

# Step 4: Detect if it's encrypted
if file "${OUTPUT_FILE}.bin" | grep -q "PGP"; then
    echo ""
    echo "🔐 File is PGP encrypted. Attempting to decrypt..."
    if gpg --decrypt "${OUTPUT_FILE}.bin" > "${OUTPUT_FILE}.tar.gz" 2>/dev/null; then
        echo "✅ Decryption successful!"
        echo "   Created: ${OUTPUT_FILE}.tar.gz"
        ls -lh "${OUTPUT_FILE}.tar.gz"

        # Step 5: Extract archive
        echo ""
        echo "Step 5: Extracting archive..."
        if tar -xf "${OUTPUT_FILE}.tar.gz"; then
            echo "✅ Extraction successful!"
            echo ""
            echo "📂 Extracted contents:"
            ls -lh
        else
            echo "❌ Extraction failed"
        fi
    else
        echo "⚠️  Decryption requires passphrase or failed"
        echo "   Use: gpg --decrypt ${OUTPUT_FILE}.bin > ${OUTPUT_FILE}.tar.gz"
    fi
else
    # Not encrypted, try to rename and extract
    mv "${OUTPUT_FILE}.bin" "${OUTPUT_FILE}.tar.gz"
    echo ""
    echo "Step 4: Extracting archive..."
    if tar -xf "${OUTPUT_FILE}.tar.gz"; then
        echo "✅ Extraction successful!"
        echo ""
        echo "📂 Extracted contents:"
        ls -lh
    else
        echo "⚠️  Not a standard archive or requires different extraction method"
    fi
fi

echo ""
echo "✅ Done!"
