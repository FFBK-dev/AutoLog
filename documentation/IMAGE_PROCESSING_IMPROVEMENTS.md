# Image Processing Improvements

## Overview
Enhanced `stills_autolog_02_copy_to_server.py` to comprehensively handle all image formats, ensuring flattened RGB JPG output.

## Date
October 20, 2025

## Changes Made

### 1. Subfolder Creation Fix
**Problem:** First subfolder was incorrectly created as `S00000-S00499` but there is no file `S00000`.

**Solution:** Added special handling for first range to start at S00001:
```python
# Special handling for first range: starts at 1, not 0
if num < 500:
    range_start = 1
    range_end = 499
else:
    range_start = (num // 500) * 500
    range_end = range_start + 499
```

**Result:** 
- First folder: `S00001-S00499` (was `S00000-S00499`)
- Subsequent folders: `S00500-S00999`, `S01000-S01499`, etc. (unchanged)

### 2. Comprehensive Image Processing
**Problem:** Limited handling of complex image formats (multi-layered images, CMYK, various color modes).

**Solution:** Created `flatten_and_convert_to_rgb()` function that handles:

#### Supported Image Types
1. **Multi-layered images** (PSDs, layered TIFs)
   - Automatically detects and flattens all layers
   - Composites layers into single RGB image

2. **RGBA images** (with alpha/transparency)
   - Flattens on white background
   - Properly handles transparency

3. **CMYK images** (print-ready files)
   - Converts to RGB color space
   - Common in professional photography

4. **16-bit images** (both grayscale and color)
   - Properly scales from 16-bit (0-65535) to 8-bit (0-255)
   - Prevents data loss during conversion

5. **Grayscale images** (L, 1 modes)
   - Converts to RGB by replicating channels

6. **Palette mode images** (P mode, common in GIFs)
   - Converts palette to full RGB

7. **LAB color space**
   - Converts to RGB

8. **Exotic color modes**
   - Fallback conversion using numpy arrays
   - Handles any PIL-supported format

#### Processing Flow
```
Input Image → Detect Format → Flatten Layers → Convert Color Mode → RGB Output
```

## Testing Results

Tested with 5 different image types:
- ✅ RGBA with alpha → RGB (white background)
- ✅ Grayscale → RGB
- ✅ Palette mode → RGB
- ✅ CMYK → RGB
- ✅ 16-bit grayscale → 8-bit RGB

All conversions successful with proper flattening and color mode conversion.

## Benefits

1. **Universal Compatibility**: Handles any image format FileMaker might receive
2. **Consistent Output**: Always produces flattened RGB JPGs
3. **Quality Preservation**: Proper handling of high bit-depth images
4. **Transparency Handling**: RGBA images flattened on white background
5. **Print File Support**: CMYK images properly converted to RGB
6. **Layer Flattening**: PSDs and multi-layer TIFs automatically composited

## Technical Details

### Key Function: `flatten_and_convert_to_rgb(img)`
- Input: PIL Image object (any format)
- Output: PIL Image object (RGB mode, flattened)
- Location: `jobs/stills_autolog_02_copy_to_server.py` lines 38-145

### Integration
Function called during main image processing flow (line 393):
```python
img = flatten_and_convert_to_rgb(img)
```

### Logging
Detailed logging shows:
- Original image mode and dimensions
- Conversion steps taken
- Final RGB output confirmation

## Files Modified

1. `jobs/stills_autolog_02_copy_to_server.py`
   - Added `flatten_and_convert_to_rgb()` function
   - Updated image processing flow
   - Fixed subfolder calculation for first range

## Migration Notes

**Existing Files**: No changes needed to existing processed images.

**New Imports**: All required imports already present (PIL, numpy, cv2).

**Backward Compatibility**: Maintains all existing functionality while adding new capabilities.

## Future Enhancements

Potential improvements:
- Add support for RAW camera formats (requires separate library)
- Add HEIC/HEIF format support
- Add color profile preservation options
