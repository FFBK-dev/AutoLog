# REVERSE_IMAGE_SEARCH Preprocessing Guide

## Problem

REVERSE_IMAGE_SEARCH records were generating embeddings from full-resolution images, while the Stills workflow uses 588x588 thumbnails. This caused embedding inconsistency:

- **Stills workflow**: RGB → 588x588 thumbnail → embedding
- **REVERSE_IMAGE_SEARCH** (old): Full-resolution → embedding ❌

This resulted in low similarity scores (0.64) even for identical images.

## Solution

Preprocess REVERSE_IMAGE_SEARCH images to match the Stills workflow before generating embeddings.

## Workflow

### 1. Import Image to REVERSE_IMAGE_SEARCH

When importing an image:
1. Set the `PATH` field to the import path
2. **Leave `IMAGE_CONTAINER` and `EMBEDDING` empty**

### 2. Preprocess the Image

Run the preprocessing script to:
- Convert grayscale → RGB (3 identical channels)
- Create 588x588 thumbnail
- Upload thumbnail to `IMAGE_CONTAINER` field

**Options:**

#### Process All Unprocessed Records (Batch)
```bash
python3 jobs/ris_preprocess_image.py all
```

#### Process Single Record
```bash
python3 jobs/ris_preprocess_image.py <record_id>
```

#### Via API
```bash
# Process all unprocessed
curl -X POST "http://localhost:8000/run/ris_preprocess_image" \
  -H "Content-Type: application/json" \
  -d '{"record_id": "all"}'

# Process single record
curl -X POST "http://localhost:8000/run/ris_preprocess_image" \
  -H "Content-Type: application/json" \
  -d '{"record_id": "184"}'
```

### 3. Generate Embedding in FileMaker

After preprocessing:
1. The `IMAGE_CONTAINER` field now contains the preprocessed thumbnail
2. Run your FileMaker CLIP embedding script
3. The embedding will be generated from the thumbnail (consistent with Stills)

## What the Preprocessing Does

```python
# 1. Detect image mode
Original: 2125x2782, Mode: L (grayscale)

# 2. Convert to RGB
→ Converting grayscale to RGB
✓ 3 identical channels created

# 3. Create thumbnail
→ Creating thumbnail (max 588x588)
Original: 2125x2782
Thumbnail: 449x588 (maintains aspect ratio)

# 4. Save as JPEG quality 85
✓ Thumbnail saved: 40 KB

# 5. Upload to FileMaker
✓ Uploaded to IMAGE_CONTAINER field
```

## Expected Results

After preprocessing and regenerating embeddings:

- **Before**: Similarity = 0.64 (LOW)
- **After**: Similarity > 0.95 (VERY HIGH) ✅

Both records now use:
- RGB mode (3 channels)
- 588x588 max thumbnail size
- JPEG quality 85
- Same preprocessing pipeline

## Integration with FileMaker

### Option 1: Manual Workflow
1. User imports image to REVERSE_IMAGE_SEARCH (sets PATH only)
2. User clicks button to run preprocessing API call
3. User clicks button to generate embedding

### Option 2: Automated Workflow
Create a FileMaker script that:
```javascript
// After user sets PATH field
Set Field [EMBEDDING; ""]  // Clear embedding
Set Field [IMAGE_CONTAINER; ""]  // Clear container

// Call preprocessing API
Perform Script ["HTTP_POST"; Parameter: "ris_preprocess_image"]

// Wait for completion
Pause [2 seconds]

// Generate embedding from preprocessed thumbnail
Perform Script ["Generate CLIP Embedding"]
```

### Option 3: Batch Processing
Run preprocessing for all pending records:
```bash
python3 jobs/ris_preprocess_image.py all
```

Then run FileMaker embedding generation script for all records with thumbnails but no embeddings.

## Field Requirements

### REVERSE_IMAGE_SEARCH Layout Fields:
- `PATH` - Import path (required for preprocessing)
- `IMAGE_CONTAINER` - Container field for thumbnail (populated by preprocessing)
- `EMBEDDING` - CLIP embedding (generated after preprocessing)
- `MATCH COUNT` - Number of matches found

## Troubleshooting

### "Record already has embedding - skipping"
The script skips records that already have embeddings to avoid reprocessing.

**To reprocess:**
1. Delete the existing embedding in FileMaker
2. Run preprocessing again
3. Generate new embedding

### "File not found"
Check that the `PATH` field points to an accessible file location.

### Container field not updating
Verify FileMaker Data API permissions for container field uploads.

## Technical Details

### Image Preprocessing Pipeline

Mirrors `stills_autolog_02_copy_to_server.py`:

```python
def flatten_and_convert_to_rgb(img):
    """Convert any image mode to RGB."""
    # Handles: L, RGBA, CMYK, P, 16-bit, etc.
    # Returns: RGB mode with 3 channels

def create_thumbnail(img, max_size=588):
    """Create thumbnail maintaining aspect ratio."""
    # Uses LANCZOS resampling
    # Saves as JPEG quality 85
    # Returns: thumbnail <= 588x588
```

### Why RGB Conversion Matters

CLIP processes grayscale and RGB images differently:
- **Grayscale (L)**: Single channel, CLIP converts internally
- **RGB**: Three channels, CLIP processes directly

Converting to RGB explicitly ensures consistent preprocessing and embedding generation.

### Why Thumbnail Size Matters

Resolution significantly affects CLIP embeddings:
- **Full res (2125x2782)**: CLIP downsamples → loses different features
- **Thumbnail (449x588)**: CLIP downsamples → consistent feature extraction

Using matching thumbnail sizes ensures consistent embeddings.

## Best Practices

1. **Always preprocess before generating embeddings**
2. **Use batch processing** for multiple imports
3. **Regenerate old embeddings** that were created from full-resolution images
4. **Monitor embedding similarity** to verify consistency (should be > 0.95 for duplicates)

## API Integration

Add to your FileMaker scripts:

```javascript
// Preprocessing API call
Set Variable [$url; "http://localhost:8000/run/ris_preprocess_image"]
Set Variable [$payload; JSONSetElement("{}"; "record_id"; Get(RecordID); JSONString)]

// POST request
Insert from URL [$url; $result; 
    cURL Options: "-X POST -H 'Content-Type: application/json' -d '" & $payload & "'"]

// Check job status
Set Variable [$jobID; JSONGetElement($result; "job_id")]
```

## Related Files

- `jobs/ris_preprocess_image.py` - Preprocessing script
- `jobs/stills_autolog_02_copy_to_server.py` - Reference implementation for Stills
- `API.py` - API endpoint: `/run/ris_preprocess_image`
- `temp/compare_ris_to_s00616.py` - Diagnostic tool

