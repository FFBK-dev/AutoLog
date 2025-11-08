#!/bin/bash
# Compare metadata extraction from multiple audio files

DIR="/Volumes/6 E2E/15 Music/1 Original Files/251015/E2E - SOURCE MX"

# Test 3 different files
FILES=(
    "Deep River.wav"
    "Go Down Moses.wav"
    "Were You There.wav"
)

for file in "${FILES[@]}"; do
    filepath="$DIR/$file"
    echo "================================================================================"
    echo "FILE: $file"
    echo "================================================================================"
    
    echo ""
    echo "--- FFPROBE METADATA (format.tags) ---"
    ffprobe -v quiet -print_format json -show_format "$filepath" 2>&1 | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    tags = data.get('format', {}).get('tags', {})
    for key, value in sorted(tags.items()):
        print(f'{key}: {value}')
except: pass
"
    
    echo ""
    echo "--- EXIFTOOL METADATA (RIFF tags) ---"
    exiftool -RIFF:* -s3 -t "$filepath" 2>&1 | grep -v "^ExifTool" | grep -v "^File" | grep -v "^System"
    
    echo ""
    echo ""
done

echo "================================================================================"
echo "KEY FINDINGS SUMMARY"
echo "================================================================================"
echo "Testing which fields are populated across different files..."
echo ""

for file in "${FILES[@]}"; do
    filepath="$DIR/$file"
    echo "$(basename "$file"):"
    
    # Check ffprobe for key fields
    result=$(ffprobe -v quiet -print_format json -show_format "$filepath" 2>&1)
    
    echo "  Track Number: $(echo "$result" | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('format',{}).get('tags',{}).get('track','NOT FOUND'))")"
    echo "  Copyright: $(echo "$result" | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('format',{}).get('tags',{}).get('copyright','NOT FOUND'))")"
    echo "  Composer: $(echo "$result" | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('format',{}).get('tags',{}).get('composer','NOT FOUND'))")"
    echo ""
done

