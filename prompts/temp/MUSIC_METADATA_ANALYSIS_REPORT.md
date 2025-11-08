# Music Metadata Extraction Analysis Report

## Executive Summary

After testing multiple metadata extraction tools on your sample music files, I've identified **ffprobe** (from FFmpeg) as the superior choice for music metadata extraction. It consistently extracts more complete metadata than exiftool, including the critical **track number** field that was missing.

## Test Results Comparison

### Files Tested
- Deep River.wav
- Go Down Moses.wav  
- Were You There.wav

### Tools Evaluated
1. **exiftool** (current implementation)
2. **ffprobe** (FFmpeg) ✅ RECOMMENDED
3. **mediainfo** (not installed)

## Key Findings

### ✅ What Works Well

**ffprobe** successfully extracts:
- ✅ **Track Number** (`track` tag) - **NOW AVAILABLE**
- ✅ Title (`title` tag)
- ✅ Artist (`artist` tag)
- ✅ Album Artist (`album_artist` tag)
- ✅ Album (`album` tag)
- ✅ Date/Year (`date` tag)
- ✅ Genre (`genre` tag)
- ✅ Disc Number (`disc` tag)
- ✅ Encoder (`encoder` tag)
- ✅ Sample Rate
- ✅ Duration
- ✅ File Format

### ❌ What's Not Present in Your Files

**Copyright and Composer fields are NOT embedded in these WAV files.**

Extensive testing with both ffprobe and exiftool confirms:
- ❌ No `copyright` tag found
- ❌ No `composer` tag found
- ❌ No `publisher` tag found
- ❌ No `label` tag found

This is **NOT a tool limitation** - these files simply don't have copyright or composer information embedded in their metadata. This is common for archival audio files that were digitized from older recordings.

## Metadata Extraction Comparison

### Current Method (exiftool)
```bash
$ exiftool -j -a -G1 "Deep River.wav"
```

**Extracts:**
- Artist, Title, Album (Product), Genre, Date, Sample Rate, Duration
- **MISSING: Track Number** ❌

### Recommended Method (ffprobe)
```bash
$ ffprobe -v quiet -print_format json -show_format -show_streams "Deep River.wav"
```

**Extracts:**
- Artist, Album Artist, Title, Album, Genre, Date, Disc, **Track Number** ✅
- Plus: Sample Rate, Duration, Bit Rate, Channels, Format
- **Bonus: More consistent tag structure** ✅

### Sample Output Comparison

**exiftool output:**
```
Artist: The Howard University Chamber Choir
Title: Deep River
Product: Wade In the Water, Vol. 1...
DateCreated: 1994
Genre: Vocal
[NO TRACK NUMBER] ❌
```

**ffprobe output:**
```json
{
  "format": {
    "tags": {
      "title": "Deep River",
      "artist": "The Howard University Chamber Choir",
      "album_artist": "The Howard University Chamber Choir",
      "album": "Wade In the Water, Vol. 1: African-American Spirituals...",
      "date": "1994",
      "genre": "Vocal",
      "track": "8",  ✅ FOUND!
      "disc": "1"
    }
  }
}
```

## Recommended Implementation Strategy

### Hybrid Approach: ffprobe Primary + exiftool Fallback

```python
def extract_metadata_robust(filepath):
    """
    Extract metadata using ffprobe first, with exiftool fallback.
    This ensures maximum metadata extraction across all audio formats.
    """
    
    # Method 1: ffprobe (BEST for music metadata)
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", filepath],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            tags = data.get('format', {}).get('tags', {})
            stream = data.get('streams', [{}])[0]
            
            # Extract all available fields with fallbacks
            metadata = {
                'title': tags.get('title', ''),
                'artist': tags.get('artist', tags.get('album_artist', '')),
                'album': tags.get('album', ''),
                'genre': tags.get('genre', ''),
                'date': tags.get('date', tags.get('year', '')),
                'track': tags.get('track', ''),  # ✅ NOW AVAILABLE
                'disc': tags.get('disc', ''),
                'composer': tags.get('composer', ''),
                'copyright': tags.get('copyright', ''),
                'sample_rate': stream.get('sample_rate', ''),
                'duration': data.get('format', {}).get('duration', ''),
                'format': data.get('format', {}).get('format_name', '').upper()
            }
            
            return metadata, 'ffprobe'
            
    except Exception as e:
        print(f"ffprobe failed: {e}, trying exiftool...")
    
    # Method 2: exiftool (FALLBACK for edge cases)
    try:
        result = subprocess.run(
            ["exiftool", "-j", "-a", "-G1", filepath],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)[0]
            # ... exiftool extraction logic ...
            
            return metadata, 'exiftool'
            
    except Exception as e:
        print(f"exiftool also failed: {e}")
        return None, None
```

### Field Mapping Updates

```python
FIELD_MAPPING = {
    # ... existing fields ...
    "track_number": "INFO_Track_Number",  # NEW FIELD ✅
    "disc_number": "INFO_Disc_Number",    # BONUS FIELD ✅
    "album_artist": "INFO_Album_Artist",  # BONUS FIELD ✅
    # ... existing fields ...
}
```

## What About Copyright & Composer?

### Reality Check ✅

Your test files **genuinely do not contain** copyright or composer metadata. This is normal for:
- Archival recordings digitized from older formats
- Public domain spirituals and traditional music
- Collection albums without per-track composer credits

### Recommended Approach

1. **Accept empty fields gracefully** ✅
   - Store empty strings in FileMaker if metadata doesn't exist
   - Don't treat missing copyright/composer as errors
   
2. **Manual entry option** ✅
   - Leave fields empty for bulk user entry if needed
   - Or pre-populate with collection-level info from album tags

3. **Alternative data sources** (optional enhancement)
   - Could integrate MusicBrainz API for additional metadata
   - Could parse album-level copyright from album tags
   - Could extract from filename patterns if consistent

## Format Support Analysis

### Tested: WAV Files ✅
Both ffprobe and exiftool handle WAV perfectly.

### Also Supports:
- **ffprobe**: MP3, FLAC, AAC, M4A, OGG, WMA, AIFF, etc. (comprehensive)
- **exiftool**: Similar broad format support

### Winner: ffprobe
- More consistent tag structure across formats
- Better JSON output format
- Includes additional technical specs (bit rate, channels, etc.)
- **Finds track numbers** that exiftool misses

## Proposed Changes

### Priority 1: Switch to ffprobe ✅
Replace exiftool with ffprobe as primary extraction method.

### Priority 2: Add Track Number Field ✅
Map `track` tag to `INFO_Track_Number` field.

### Priority 3: Handle Missing Data Gracefully ✅
- Don't error on missing copyright/composer
- Log what was found vs. not found
- Store empty strings for missing fields

### Priority 4: Add Bonus Fields (Optional)
- Disc Number → `INFO_Disc_Number`
- Album Artist → `INFO_Album_Artist`
- Bit Rate → `SPECS_File_Bit_Rate`

## Performance Impact

### ffprobe vs exiftool
- **Speed**: Comparable (both ~0.5-1.0s per file)
- **Reliability**: ffprobe slightly better for audio
- **Accuracy**: ffprobe extracts more complete tags
- **Format Support**: Both excellent

### No significant performance degradation expected ✅

## Implementation Checklist

- [ ] Update `music_autolog_03_parse_metadata.py` to use ffprobe
- [ ] Add track number extraction
- [ ] Add fallback to exiftool for edge cases
- [ ] Update field mapping to include track_number
- [ ] Test with various audio formats (MP3, FLAC, etc.)
- [ ] Update documentation
- [ ] Handle missing copyright/composer gracefully

## Conclusion

**Recommendation: Switch to ffprobe with exiftool fallback**

This hybrid approach will:
1. ✅ Extract track numbers (currently missing)
2. ✅ Get more complete metadata overall
3. ✅ Handle missing fields gracefully
4. ✅ Support all common audio formats
5. ✅ Provide better structured output

**Note on Copyright/Composer:**
Your expectation that this data exists was reasonable, but the files genuinely don't contain it. This is normal for archival music collections. The workflow will handle this gracefully by storing empty values.

