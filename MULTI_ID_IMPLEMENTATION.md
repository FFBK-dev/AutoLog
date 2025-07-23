# Multi-ID Processing Implementation

## Overview

This implementation adds comprehensive multi-ID processing capabilities to all individual job endpoints in the FileMaker Backend system. Individual job scripts can now accept either a single ID or multiple IDs in various formats, with automatic parsing, validation, and parallel processing.

## What Was Implemented

### 1. Input Parser Utility (`utils/input_parser.py`)

A standardized input parsing utility that supports multiple ID formats:

- **Single ID**: `"S04871"`
- **JSON Array**: `'["S04871", "S04872", "S04873"]'`
- **Comma-separated**: `"S04871,S04872,S04873"`
- **Line-separated**: `"S04871\nS04872\nS04873"`
- **Space-separated**: `"S04871 S04872 S04873"`

**Key Functions:**
- `parse_input_ids(input_string)` - Parse various input formats into a list of IDs
- `validate_ids(ids, expected_prefixes)` - Validate IDs against expected prefixes
- `format_input_summary(ids, script_name)` - Format logging summaries
- `get_input_from_argv()` - Get and parse input from command line arguments

### 2. API Layer Updates (`API.py`)

Enhanced the API layer to support both single values and arrays for multi-ID processing:

```python
# Support both single values and arrays for multi-ID processing
if isinstance(value, list):
    # Convert list to JSON string for the script to parse
    import json
    args.append(json.dumps(value))
else:
    args.append(str(value))
```

### 3. Updated Job Script Template (`jobs/template_multi_id.py`)

A new template that provides standardized multi-ID processing for job scripts with:

- Input parsing and validation
- Single item processing function
- Batch processing with parallel execution
- Comprehensive error handling and logging
- JSON result output for easy parsing

### 4. Updated Individual Job Script (`jobs/stills_autolog_01_get_file_info.py`)

Converted an existing job script to demonstrate the new multi-ID capabilities:

- Added input parsing and validation
- Implemented `process_single_item()` function
- Implemented `process_batch_items()` function with parallel processing
- Updated main execution logic to handle both single and batch processing

## Usage Examples

### API Endpoint Usage

**Single ID:**
```bash
curl -X POST "http://localhost:8081/run/stills_autolog_01_get_file_info" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": "S04871"}'
```

**Multiple IDs (JSON Array):**
```bash
curl -X POST "http://localhost:8081/run/stills_autolog_01_get_file_info" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": ["S04871", "S04872", "S04873"]}'
```

**Multiple IDs (Comma-separated):**
```bash
curl -X POST "http://localhost:8081/run/stills_autolog_01_get_file_info" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": "S04871,S04872,S04873"}'
```

### Direct Script Usage

**Single ID:**
```bash
python3 jobs/stills_autolog_01_get_file_info.py "S04871"
```

**Multiple IDs (various formats):**
```bash
python3 jobs/stills_autolog_01_get_file_info.py "S04871,S04872,S04873"
python3 jobs/stills_autolog_01_get_file_info.py '["S04871", "S04872", "S04873"]'
python3 jobs/stills_autolog_01_get_file_info.py "S04871\nS04872\nS04873"
```

## Key Features

### 1. Flexible Input Formats
- Supports 5 different input formats
- Automatic format detection and parsing
- Robust error handling for malformed input

### 2. Input Validation
- Validates IDs against expected prefixes (S, F, AF, FTG)
- Filters out invalid IDs while proceeding with valid ones
- Provides clear feedback about validation results

### 3. Parallel Processing
- Configurable number of concurrent workers (default: 8)
- Automatic worker adjustment based on item count
- Progress tracking and real-time status updates

### 4. Comprehensive Logging
- Emoji-based visual indicators for different operations
- Detailed progress tracking for batch operations
- Clear success/failure reporting

### 5. Structured Results
- JSON output for batch operations
- Detailed success/failure counts
- Individual item result tracking
- Easy parsing by client applications

### 6. Backward Compatibility
- Existing single-ID usage continues to work unchanged
- Legacy API formats are still supported
- Gradual migration path for existing scripts

## Implementation Pattern

### For New Job Scripts

1. **Import the input parser:**
```python
from utils.input_parser import parse_input_ids, format_input_summary, validate_ids
```

2. **Define expected ID prefixes:**
```python
EXPECTED_ID_PREFIXES = ['S', 'F', 'AF', 'FTG']
```

3. **Implement single item processing:**
```python
def process_single_item(item_id: str, token: str) -> bool:
    # Your processing logic here
    return True/False
```

4. **Implement batch processing:**
```python
def process_batch_items(item_ids: list, token: str, max_workers: int = 8) -> dict:
    # Standardized batch processing implementation
```

5. **Update main execution:**
```python
# Parse and validate input
item_ids = parse_input_ids(input_string)
valid_ids, invalid_ids = validate_ids(item_ids, EXPECTED_ID_PREFIXES)

# Process items
if len(valid_ids) == 1:
    success = process_single_item(valid_ids[0], token)
    sys.exit(0 if success else 1)
else:
    results = process_batch_items(valid_ids, token)
    print(f"BATCH_RESULTS: {json.dumps(results, indent=2)}")
    sys.exit(0 if results["failed"] == 0 else 1)
```

### For Existing Job Scripts

1. Add the input parser import
2. Replace single ID processing with the new pattern
3. Add batch processing functions
4. Update the main execution logic

## Testing

A test script (`test_multi_id.py`) is provided to demonstrate and validate the multi-ID capabilities:

```bash
python3 test_multi_id.py
```

## Benefits

1. **Increased Efficiency** - Process multiple items in parallel
2. **Flexible Input** - Support various input formats for different use cases
3. **Better Error Handling** - Continue processing even if some items fail
4. **Improved Monitoring** - Real-time progress tracking and detailed results
5. **Standardized Approach** - Consistent pattern across all job scripts
6. **Backward Compatibility** - Existing workflows continue to work

## Next Steps

To complete the implementation across all job scripts:

1. **Update remaining job scripts** using the same pattern as `stills_autolog_01_get_file_info.py`
2. **Test with real data** to ensure performance and reliability
3. **Update documentation** for all affected endpoints
4. **Consider performance tuning** based on actual usage patterns

## Files Modified/Created

- ✅ `utils/input_parser.py` - New input parsing utility
- ✅ `API.py` - Enhanced API layer for multi-ID support
- ✅ `jobs/template_multi_id.py` - New template for multi-ID scripts
- ✅ `jobs/stills_autolog_01_get_file_info.py` - Updated example script
- ✅ `README.md` - Updated documentation
- ✅ `test_multi_id.py` - Test script for validation
- ✅ `MULTI_ID_IMPLEMENTATION.md` - This implementation guide 