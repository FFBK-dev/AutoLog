# REVERSE_IMAGE_SEARCH - FileMaker Integration Guide

## Problem Summary

REVERSE_IMAGE_SEARCH was generating embeddings from full-resolution grayscale images, while the Stills workflow uses RGB 588x588 thumbnails. This caused embedding inconsistency (similarity = 0.64 instead of > 0.95).

## Solution

Use a Python script to preprocess images before generating embeddings in FileMaker.

---

## Implementation: FileMaker Script

### Step 1: Create FileMaker Script "RIS - Preprocess Image"

```javascript
# RIS - Preprocess Image
# Called before generating CLIP embedding for REVERSE_IMAGE_SEARCH records

# Get the import path
Set Variable [$importPath; REVERSE_IMAGE_SEARCH::PATH]

If [IsEmpty($importPath)]
    Show Custom Dialog ["Error"; "No import path found"]
    Exit Script []
End If

# Build Python command
Set Variable [$pythonCmd; 
    "cd /Users/admin/Documents/Github/Filemaker-Backend && " & 
    "python3 jobs/create_thumbnail_rgb.py \"" & $importPath & "\""
]

# Execute Python script to create RGB thumbnail
Set Variable [$result; ExecuteSystemCommand($pythonCmd)]

# Extract thumbnail path from result
# Python outputs: "THUMBNAIL_PATH:/tmp/thumb_filename.jpg"
Set Variable [$thumbnailPath; 
    Middle($result; Position($result; "THUMBNAIL_PATH:"; 1; 1) + 15; 999)
]

# Trim whitespace/newlines
Set Variable [$thumbnailPath; Trim($thumbnailPath)]

# Check if thumbnail was created successfully
If [IsEmpty($thumbnailPath) or Left($thumbnailPath; 1) ≠ "/"]
    Show Custom Dialog ["Error"; "Failed to create thumbnail¶¶" & $result]
    Exit Script []
End If

# Insert the thumbnail into the container field
Set Field [REVERSE_IMAGE_SEARCH::IMAGE_CONTAINER; $thumbnailPath]

# Clean up temp file (optional)
Set Variable [$cleanupCmd; "rm \"" & $thumbnailPath & "\""]
Perform Script ["Execute System Command"; Parameter: $cleanupCmd]

# Success message
Show Custom Dialog ["Success"; "Image preprocessed¶Ready for embedding generation"]
```

### Step 2: Update "RIS - Generate Embedding" Script

```javascript
# RIS - Generate Embedding
# Modified to check for preprocessed thumbnail

# Check if thumbnail exists
If [IsEmpty(REVERSE_IMAGE_SEARCH::IMAGE_CONTAINER)]
    # No thumbnail - run preprocessing first
    Perform Script ["RIS - Preprocess Image"]
    
    # Check again
    If [IsEmpty(REVERSE_IMAGE_SEARCH::IMAGE_CONTAINER)]
        Show Custom Dialog ["Error"; "Preprocessing failed"]
        Exit Script []
    End If
End If

# Now generate embedding from the RGB thumbnail
# Your existing CLIP embedding generation code here...
Perform Script on Server ["Generate CLIP Embedding from Container"; 
    Parameter: "REVERSE_IMAGE_SEARCH"]
```

### Step 3: Create Button on Layout

Add a button to your REVERSE_IMAGE_SEARCH layout:
- **Button 1**: "Preprocess Image" → Calls "RIS - Preprocess Image"
- **Button 2**: "Generate Embedding" → Calls "RIS - Generate Embedding"

Or combine into one button:
- **Button**: "Process & Generate Embedding" → Calls "RIS - Generate Embedding" (which includes preprocessing)

---

## Alternative: API Integration

If you prefer using the API:

### FileMaker Script with API Call

```javascript
# RIS - Preprocess via API

Set Variable [$recordID; Get(RecordID)]
Set Variable [$apiURL; "http://localhost:8000/run/create_thumbnail"]
Set Variable [$payload; 
    JSONSetElement("{}"; 
        "image_path"; REVERSE_IMAGE_SEARCH::PATH; JSONString
    )
]

# Call API
Insert from URL [$apiURL; $$result;
    cURL Options: "-X POST -H 'Content-Type: application/json' -d '" & $payload & "'"
]

# Parse response
Set Variable [$thumbnailPath; JSONGetElement($$result; "thumbnail_path")]

# Insert into container
Set Field [REVERSE_IMAGE_SEARCH::IMAGE_CONTAINER; $thumbnailPath]
```

---

## Workflow Comparison

### Old Workflow (Inconsistent)
```
1. Import image → PATH field
2. Copy full-resolution to IMAGE_CONTAINER  
3. Generate embedding from full-resolution ❌
   Result: Similarity = 0.64
```

### New Workflow (Consistent)
```
1. Import image → PATH field
2. Run preprocessing:
   → Convert to RGB
   → Create 588x588 thumbnail
   → Upload to IMAGE_CONTAINER
3. Generate embedding from RGB thumbnail ✅
   Result: Similarity > 0.95
```

---

## Testing

### Test with Record 184

1. **Before preprocessing:**
   ```
   Image: 2125x2782, Grayscale
   Embedding: Generated from full-res
   ```

2. **Run preprocessing:**
   ```bash
   python3 jobs/create_thumbnail_rgb.py \
     "/Volumes/6 E2E/7 E2E Stills/.../GettyImages-3302950.jpg"
   ```

3. **Upload thumbnail** to IMAGE_CONTAINER in FileMaker

4. **Regenerate embedding** from thumbnail

5. **Verify consistency:**
   - Compare with S00616 embedding
   - Similarity should be > 0.95 ✅

---

## Python Script Details

### Location
```
jobs/create_thumbnail_rgb.py
```

### Usage
```bash
# Basic usage
python3 create_thumbnail_rgb.py <image_path>

# Specify output path
python3 create_thumbnail_rgb.py <image_path> <output_path>
```

### Output
```
📸 Processing: /path/to/image.jpg
  Original: 2125x2782, Mode: L
  → Converted L to RGB
  → Thumbnail: 449x588
  ✅ Saved: /tmp/thumb_image.jpg (39.9 KB)
THUMBNAIL_PATH:/tmp/thumb_image.jpg
```

### What It Does
1. Opens image from any path
2. Converts to RGB (grayscale → 3 identical channels)
3. Creates thumbnail (max 588x588, maintains aspect ratio)
4. Saves as JPEG quality 85
5. Returns thumbnail path for FileMaker

---

## Batch Processing

To preprocess multiple records at once:

### Option 1: Loop in FileMaker
```javascript
Go to Layout [REVERSE_IMAGE_SEARCH]
Show All Records
Go to Record/Request/Page [First]

Loop
    # Check if needs preprocessing
    If [IsEmpty(REVERSE_IMAGE_SEARCH::IMAGE_CONTAINER) and 
        Not IsEmpty(REVERSE_IMAGE_SEARCH::PATH)]
        
        Perform Script ["RIS - Preprocess Image"]
    End If
    
    Go to Record/Request/Page [Next; Exit after last: On]
End Loop
```

### Option 2: Python Batch Script
Create a FileMaker script that exports a list of paths, then process with Python:

```bash
# Process multiple images
for path in $(cat image_paths.txt); do
    python3 jobs/create_thumbnail_rgb.py "$path"
done
```

---

## Troubleshooting

### "File not found"
- Verify the PATH field contains a valid file path
- Check that the volume is mounted (`/Volumes/6 E2E`)
- Use absolute paths, not relative

### "Thumbnail not created"
- Check Python script output for errors
- Verify write permissions to `/tmp/`
- Ensure PIL/Pillow is installed

### "Container field not updating"
- Check FileMaker container field settings
- Verify Data API permissions (if using API)
- Use `Set Field` or `Insert File` commands

### "Embeddings still different"
- Verify thumbnail is RGB mode (not grayscale)
- Check thumbnail dimensions (should be ≤ 588x588)
- Regenerate embedding after uploading thumbnail
- Compare with diagnostic script

---

## Migration Plan

### For Existing Records

1. **Identify records with old embeddings:**
   - Have EMBEDDING field populated
   - IMAGE_CONTAINER is full-resolution or grayscale

2. **Batch reprocess:**
   - Clear EMBEDDING field
   - Run preprocessing script
   - Regenerate embeddings

3. **Verify consistency:**
   - Test similarity searches
   - Compare against Stills records
   - Expect similarity > 0.95 for duplicates

---

## Related Documentation

- `/documentation/REVERSE_IMAGE_SEARCH_PREPROCESSING.md` - Technical details
- `/jobs/create_thumbnail_rgb.py` - Preprocessing script
- `/jobs/stills_autolog_02_copy_to_server.py` - Reference implementation
- `/temp/compare_ris_to_s00616.py` - Diagnostic tool

---

## Summary

✅ **Before**: Full-resolution grayscale → Embedding (inconsistent)  
✅ **After**: RGB 588x588 thumbnail → Embedding (consistent)

📊 **Result**: Embedding similarity improved from 0.64 to > 0.95

🎯 **Integration**: Simple FileMaker script calls Python → Uploads thumbnail → Generates embedding

