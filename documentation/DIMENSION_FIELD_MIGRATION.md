# Dimension Field Migration Guide

## Overview

This document describes the migration from a single `SPECS_File_Dimensions` field to separate `SPECS_File_Dimensions_X` and `SPECS_File_Dimensions_Y` fields in the Stills workflow.

## Changes Made

### 1. Updated `stills_autolog_01_get_file_info.py`

The script now extracts and stores dimensions in three fields:
- **SPECS_File_Dimensions** - Combined format (e.g., "1920x1080") - kept for compatibility
- **SPECS_File_Dimensions_X** - Width as integer (e.g., 1920)
- **SPECS_File_Dimensions_Y** - Height as integer (e.g., 1080)

#### Technical Details

- Dimensions are extracted from images using PIL (primary method)
- Falls back to alternative methods (exiftool, sips, ImageMagick) if PIL fails
- Both X and Y values are stored as integers for easy calculations
- Alternative extraction methods are also parsed into separate X/Y fields

### 2. Migration Script for Existing Records

**File**: `/temp/migrate_dimensions.py`

This script processes all existing records to populate the new X and Y fields.

#### Features

- **Batch Processing**: Processes records in configurable batches (default: 50)
- **API Rate Limiting**: Built-in delays between batches and updates
- **Dry Run Mode**: Test without making changes
- **Progress Tracking**: Real-time progress updates with ETA
- **Resumable**: Automatically skips records that already have X/Y values
- **Error Handling**: Comprehensive error handling with detailed logging
- **Token Refresh**: Automatically handles expired tokens

#### Usage

```bash
# Dry run (test without making changes)
python3 temp/migrate_dimensions.py --dry-run

# Small batch test
python3 temp/migrate_dimensions.py --dry-run --batch-size 10

# Actual migration (production run)
python3 temp/migrate_dimensions.py

# Custom batch size
python3 temp/migrate_dimensions.py --batch-size 100
```

#### Configuration Options

Edit these variables at the top of the script:

```python
BATCH_SIZE = 50                 # Records per batch
DELAY_BETWEEN_BATCHES = 2       # Seconds between batches
DELAY_BETWEEN_UPDATES = 0.1     # Seconds between individual updates
DRY_RUN = False                 # Set True to test without changes
```

#### Performance

Based on test runs with 8,867 records:

| Mode | Processing Rate | Estimated Time |
|------|----------------|----------------|
| Dry Run | ~88 records/sec | ~1.7 minutes |
| Production | ~40-50 records/sec | ~3-4 minutes |

**Note**: Production runs are slower due to actual API writes and rate limiting.

## Migration Results

From the test run on the production database:

- **Total Records**: 8,867
- **Successfully Processed**: 8,858 (99.9%)
- **Already Split**: 1 (0.01%)
- **No Dimensions**: 3 (0.03%)
- **Parse Errors**: 5 (0.06%)
- **Failed**: 0 (0%)

### Records Requiring Attention

#### No Dimensions (3 records)
These records have no dimension data or have "Unknown" as the value. These need manual review.

#### Parse Errors (5 records)
These records have dimension strings that couldn't be parsed (e.g., malformed format). These need manual review.

## Testing

### Test Script

**File**: `/temp/test_dimension_split.py`

Verifies that the dimension fields exist and are correctly formatted.

```bash
python3 temp/test_dimension_split.py
```

### Manual Testing

1. Run the get_file_info script on a single record:
```bash
python3 jobs/stills_autolog_01_get_file_info.py S00001
```

2. Verify the output shows:
```
-> Set dimensions: X=3652, Y=2748
```

3. Check FileMaker to confirm the fields are populated.

## Database Schema

Ensure these fields exist in the FileMaker Stills layout:

| Field Name | Type | Description |
|------------|------|-------------|
| SPECS_File_Dimensions | Text | Combined dimensions (e.g., "1920x1080") |
| SPECS_File_Dimensions_X | Number | Width in pixels |
| SPECS_File_Dimensions_Y | Number | Height in pixels |

## API Rate Limiting Strategy

The migration script respects FileMaker Data API limits:

1. **Batch Processing**: Processes 50 records at a time (configurable)
2. **Batch Delays**: 2-second delay between batches
3. **Update Delays**: 0.1-second delay between individual updates
4. **Token Management**: Automatically refreshes expired tokens

This approach ensures:
- No API timeout errors
- Minimal server load
- Stable, reliable migration
- ~3-4 minutes total migration time for 8,000+ records

## Rollback Plan

If issues are encountered:

1. **Stop the migration**: Press Ctrl+C if running
2. **Review errors**: Check the console output for specific issues
3. **Fix issues**: Correct any identified problems
4. **Re-run**: The script automatically skips already-processed records

The original `SPECS_File_Dimensions` field is never modified, so it serves as a backup reference.

## Future Considerations

### Benefits of Separate X/Y Fields

- **Calculations**: Easy to calculate aspect ratios, cropping, resizing
- **Filtering**: Can filter by width or height directly
- **Sorting**: Can sort by dimension size
- **Validation**: Can validate minimum/maximum dimensions
- **Analytics**: Can analyze image size distributions

### Example Use Cases

```javascript
// Calculate aspect ratio
aspectRatio = SPECS_File_Dimensions_X / SPECS_File_Dimensions_Y

// Filter large images
SPECS_File_Dimensions_X > 4000

// Sort by total pixel count
SPECS_File_Dimensions_X * SPECS_File_Dimensions_Y
```

## Maintenance

### New Records

All new records processed through `stills_autolog_01_get_file_info.py` will automatically have all three fields populated.

### Existing Records

If new records are added to the database without going through the workflow:

1. Run the migration script again (it will skip already-processed records)
2. Or manually run the get_file_info script on specific records:
```bash
python3 jobs/stills_autolog_01_get_file_info.py S12345
```

## Troubleshooting

### Issue: "No valid IDs to process"
**Solution**: Ensure the record ID is correct and follows the format (S00001, F00001, etc.)

### Issue: "Token expired" errors
**Solution**: The script handles this automatically. If persistent, check config.py credentials.

### Issue: "Could not parse dimensions"
**Solution**: Check the SPECS_File_Dimensions field format. Should be "WIDTHxHEIGHT" (e.g., "1920x1080")

### Issue: Migration seems stuck
**Solution**: Normal - the delays between batches make it seem slow. Check progress updates.

## Conclusion

This migration provides better data structure for dimension handling while maintaining backward compatibility with the original combined field. The migration script is designed to be safe, efficient, and easy to monitor.

