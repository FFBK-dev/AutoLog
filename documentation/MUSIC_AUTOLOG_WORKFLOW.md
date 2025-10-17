# Music AutoLog Workflow Documentation

## Overview

The Music AutoLog workflow provides automated processing for music files in the FileMaker Music layout. It handles file renaming, technical specs extraction, and comprehensive metadata parsing.

## Workflow Architecture

### Status Progression

The workflow uses the `AutoLog_Status` field to track progress:

1. **0 - Pending File Info** → Initial state
2. **1 - File Renamed** → After Step 1 (file renaming)
3. **2 - Specs Extracted** → After Step 2 (specs extraction)
4. **3 - Metadata Parsed** → After Step 3 (metadata parsing)
5. **4 - Complete** → Workflow complete
6. **Awaiting User Input** → Error state requiring manual intervention

### Workflow Steps

#### Step 1: Rename File with ID Prefix
**Script:** `music_autolog_01_rename_file.py`

- Retrieves the file path from `SPECS_Filepath_Server`
- Prepends the `INFO_MUSIC_ID` to the filename
- Example: `Band of Gideon.wav` → `MX001_Band of Gideon.wav`
- Updates FileMaker with the new file path
- Skips renaming if file already has the ID prefix

**Error Handling:**
- Validates file exists before renaming
- Ensures volume is mounted
- Handles duplicate renames gracefully

#### Step 2: Extract File Specs
**Script:** `music_autolog_02_extract_specs.py`

Extracts technical specifications using `exiftool` (with `ffprobe` fallback):
- **File Format** → `SPECS_File_Format` (e.g., "WAV", "MP3")
- **Sample Rate** → `SPECS_File_Sample_Rate` (e.g., "48000")
- **Duration** → `SPECS_Duration` (formatted as "MM:SS" or "H:MM:SS")

**Tools Used:**
- Primary: `exiftool` (faster, simpler)
- Fallback: `ffprobe` (more comprehensive for complex formats)

#### Step 3: Parse Metadata
**Script:** `music_autolog_03_parse_metadata.py`

**Multi-Tool Approach:** Uses **both ffprobe AND exiftool** for maximum metadata extraction:

**Primary Tool: ffprobe** (best for music tags)
- Extracts comprehensive music metadata
- **Finds track numbers** that other tools miss ✅
- Provides consistent JSON structure
- Handles all major audio formats

**Secondary Tool: exiftool** (supplementary extraction)
- Extracts additional RIFF/INFO chunks
- Fills in gaps from ffprobe
- Provides backup extraction method

**Fields Extracted:**
- **Song Name** → `INFO_Song_Name`
- **Artist** → `INFO_Artist`
- **Album** → `INFO_Album`
- **Composer** → `PUBLISHING_Composer` (when available)
- **Genre** → `INFO_Genre`
- **Release Year** → `INFO_Release_Year`
- **Track Number** → `INFO_Track_Number` ✅ **NEW**
- **ISRC/UPC Code** → `INFO_ISRC_UPC_Code` (when available)
- **Copyright** → `INFO_Copyright` (when available)
- **Raw Metadata** → `INFO_Metadata` (comprehensive from both tools)

**Intelligent Merging:**
- ffprobe data takes priority (better for music tags)
- exiftool fills in any missing fields
- Both extractions stored in `INFO_Metadata` for reference

**Format Support:**
The multi-tool approach handles all common audio formats:
- WAV (RIFF tags)
- MP3 (ID3 tags)
- FLAC (Vorbis comments)
- AAC/M4A (iTunes metadata)
- OGG (Vorbis comments)
- WMA (Windows Media tags)

**Graceful Degradation:**
- Continues processing even if some metadata fields are missing
- Logs which fields were found vs. not found
- Stores comprehensive raw metadata for reference

## Field Mapping

```python
FIELD_MAPPING = {
    # Core identification
    "music_id": "INFO_MUSIC_ID",
    "status": "AutoLog_Status",
    "dev_console": "AI_DevConsole",
    
    # File paths
    "filepath_import": "SPECS_Filepath_Import",
    "filepath_server": "SPECS_Filepath_Server",
    
    # File specs (Step 2)
    "file_format": "SPECS_File_Format",
    "sample_rate": "SPECS_File_Sample_Rate",
    "duration": "SPECS_Duration",
    
    # Music metadata (Step 3)
    "song_name": "INFO_Song_Name",
    "artist": "INFO_Artist",
    "album": "INFO_Album",
    "composer": "PUBLISHING_Composer",
    "genre": "INFO_Genre",
    "release_year": "INFO_Release_Year",
    "isrc_upc": "INFO_ISRC_UPC_Code",
    "copyright": "INFO_Copyright",
    
    # Raw metadata storage
    "metadata": "INFO_Metadata",
    
    # Import tracking
    "imported_by": "SPECS_File_Imported_By",
    "import_timestamp": "SPECS_File_Import_Timestamp"
}
```

## Usage

### Automatic Discovery Mode (Recommended)

The `music_autolog_00_run_all.py` script automatically discovers and processes pending items:

```bash
python3 jobs/music_autolog_00_run_all.py
```

**Behavior:**
- Queries FileMaker for all records with status "0 - Pending File Info"
- Processes up to 100 items per batch
- Handles single items or batch processing automatically
- Provides comprehensive progress logging

### Manual Single-Item Processing

Process a specific Music ID:

```bash
# Get a token first
python3 -c "import config; print(config.get_token())"

# Run individual steps
python3 jobs/music_autolog_01_rename_file.py MX001 <token>
python3 jobs/music_autolog_02_extract_specs.py MX001 <token>
python3 jobs/music_autolog_03_parse_metadata.py MX001 <token>
```

### API Integration

The Music AutoLog endpoint is available at `/run/music_autolog`:

```bash
# Trigger the music autolog workflow via API
curl -X POST http://localhost:8000/run/music_autolog \
  -H "Content-Type: application/json"

# Response:
{
  "job_id": "music_autolog_0_1234567890",
  "job_name": "music_autolog",
  "submitted": true,
  "status": "running",
  "message": "Music AutoLog workflow started - processing pending items"
}

# Check job status:
curl http://localhost:8000/status/music_autolog_0_1234567890
```

## Batch Processing

The workflow supports parallel batch processing with optimized concurrency:

- **Small batches (<20 items):** Up to 16 concurrent workers
- **Medium batches (20-50 items):** 14 concurrent workers
- **Large batches (>50 items):** 12 concurrent workers

**Performance Metrics:**
- Progress tracking with milestone reporting
- Success/failure statistics
- Throughput measurement (items/minute)
- Per-item timing

## Error Handling

### Resilient Design

- **Token Refresh:** Automatic token renewal on 401 errors
- **Retry Logic:** 3 attempts with exponential backoff for network operations
- **Timeout Protection:** 5-minute timeout per step
- **Volume Mounting:** Automatic SMB volume mounting for `/Volumes/6 E2E/`

### Error Reporting

All errors are logged to the `AI_DevConsole` field:
- Timestamp for each error
- Step name where error occurred
- Music ID affected
- Detailed error message (truncated to 1000 characters)

### Graceful Degradation

- Individual item failures don't stop batch processing
- Missing metadata fields don't fail the workflow
- File already renamed → skip rename step
- Continue to next step even if optional fields are empty

## Testing

### Test Script

Use the provided test script to validate the workflow:

```bash
python3 temp/test_music_autolog.py
```

**Prerequisites:**
1. Create a test record in FileMaker Music layout
2. Set `INFO_MUSIC_ID` (e.g., "MX001")
3. Set `SPECS_Filepath_Server` to a test file path:
   ```
   /Volumes/6 E2E/15 Music/1 Original Files/251015/E2E - SOURCE MX/Band of Gideon.wav
   ```
4. Set `AutoLog_Status` to "0 - Pending File Info"

The test script will:
- Test each step individually
- Prompt for confirmation between steps
- Validate all fields are populated correctly
- Verify final status is "9 - Complete"

### Manual Testing

You can also test by updating a record's status and running the facilitator:

```bash
# In FileMaker, set a record's AutoLog_Status to "0 - Pending File Info"
# Then run:
python3 jobs/music_autolog_00_run_all.py
```

## Supported Audio Formats

The workflow supports all formats that `exiftool` can process:
- **WAV** (tested) - RIFF metadata tags
- **MP3** - ID3 tags
- **FLAC** - Vorbis comments
- **AAC/M4A** - iTunes metadata
- **OGG** - Vorbis comments
- **WMA** - Windows Media metadata
- **AIFF** - AIFF metadata chunks

## File Organization

All music files should be stored on the SMB volume:
```
/Volumes/6 E2E/15 Music/1 Original Files/
```

The workflow uses the existing `config.mount_volume("stills")` function to ensure the volume is mounted before processing.

## Integration with Other Systems

### FileMaker Scripts

Call the workflow from FileMaker using the Perform Script on Server (PSOS) feature or via the API.

### Scheduled Processing

Set up a cron job or scheduled task to run the workflow periodically:

```bash
# Run every hour to process pending items
0 * * * * cd /path/to/Filemaker-Backend && python3 jobs/music_autolog_00_run_all.py
```

## Troubleshooting

### Common Issues

**"File not found at path"**
- Verify the file path in `SPECS_Filepath_Server` is correct
- Ensure the SMB volume is mounted: `/Volumes/6 E2E/`
- Check file permissions

**"No metadata found"**
- Some files may not have embedded metadata
- Check the `INFO_Metadata` field for raw exiftool output
- Verify the file format is supported

**"Token expired during processing"**
- The workflow automatically refreshes tokens
- Check FileMaker server connectivity
- Verify credentials in `config.py`

**"Script timed out after 5 minutes"**
- Large files may take longer to process
- Check network connectivity to SMB volume
- Consider increasing timeout in workflow step configuration

### Debug Mode

Enable debug mode for real-time output:

```bash
export AUTOLOG_DEBUG=true
python3 jobs/music_autolog_00_run_all.py
```

This will show subprocess output in real-time without capturing it.

## Performance Considerations

### Optimization Tips

1. **Batch Processing:** Process multiple items at once for better throughput
2. **Volume Pre-mounting:** Ensure SMB volume is mounted before starting large batches
3. **Network Stability:** Process during low-traffic periods for better reliability
4. **Concurrent Workers:** Adjust max_workers based on system resources

### Expected Performance

- **Single item:** ~2-5 seconds per file
- **Batch processing:** ~30-60 items/minute (depending on concurrency)
- **Network overhead:** ~0.5-1 second per FileMaker API call

## Future Enhancements

Potential improvements to consider:

1. **Audio Analysis:** Add waveform analysis, tempo detection, key detection
2. **Tag Cleanup:** Normalize genre tags, clean up artist names
3. **Duplicate Detection:** Check for duplicate files based on metadata
4. **Quality Validation:** Verify sample rate meets minimum requirements
5. **Format Conversion:** Optional transcoding to standard format
6. **Thumbnail Generation:** Create waveform thumbnails for visual reference

## Related Documentation

- [Stills AutoLog Workflow](STILLS_POLLING_CONVERSION.md)
- [Footage AutoLog Workflow](POLLING_VS_SEQUENTIAL_WORKFLOWS.md)
- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [Security README](SECURITY_README.md)

## Support

For issues or questions about the Music AutoLog workflow:
1. Check this documentation first
2. Review error messages in `AI_DevConsole` field
3. Test with the provided test script
4. Check the logs in `/logs/` directory (if logging is configured)

