# Metadata Bridge API Documentation

## Overview

The Metadata Bridge API provides **bidirectional metadata synchronization** between FileMaker Pro and Avid Media Composer:

- **Import**: FileMaker Pro → Avid Media Composer (`/metadata-bridge/query`)
- **Export**: Avid Media Composer → FileMaker Pro (`/metadata-bridge/export`)

## Endpoints

### 1. Metadata Import (FileMaker Pro → Avid Media Composer)

**Endpoint**: `POST /metadata-bridge/query`

**Purpose**: Retrieve metadata from FileMaker Pro for use in Avid Media Composer

**Headers**:
```
X-API-Key: your_api_key
Content-Type: application/json
```

**Request Payload**:
```json
{
  "media_type": "stills|archival|live_footage",
  "identifiers": ["STILLS_001", "STILLS_002"]
}
```

**Response (Stills)**:
```json
{
  "media_type": "stills",
  "requested_identifiers": ["STILLS_001", "STILLS_002"],
  "results": [
    {
      "identifier": "STILLS_001",
      "found": true,
      "info_description": "Sample still image description",
      "info_date": "2024-01-15",
      "info_source": "Sample Source",
      "tags_list": "sample, test, stills"
    },
    {
      "identifier": "STILLS_002",
      "found": false,
      "error": "Record not found"
    }
  ],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Response (Footage - Archival or Live)**:
```json
{
  "media_type": "archival",
  "requested_identifiers": ["A075C005_250428_R3WV.mov"],
  "results": [
    {
      "identifier": "A075C005_250428_R3WV.mov",
      "found": true,
      "ftg_id": "LF0005",
      "info_description": "Sunrise over Charleston Harbor",
      "info_title": "Sunrise Over Charleston Harbor",
      "info_location": "Charleston, SC",
      "info_source": "20250428",
      "info_date": "2025-04-28",
      "tags_list": "sunrise, harbor, charleston",
      "info_avid_description": "Beautiful morning light",
      "info_color_mode": "Color",
      "info_audio_type": "Stereo",
      "info_ff_project": "Charleston Documentary 2025",
      "info_reviewed_checkbox": "Yes",
      "info_avid_bins": "Archive Collection 2025"
    }
  ],
  "timestamp": "2025-04-28T10:30:00Z"
}
```

### 2. Metadata Export (Avid Media Composer → FileMaker Pro)

**Endpoint**: `POST /metadata-bridge/export`

**Purpose**: Send metadata from Avid Media Composer to update FileMaker Pro records

**Headers**:
```
X-API-Key: your_api_key
Content-Type: application/json
```

**Request Payload (Stills)**:
```json
{
  "media_type": "stills",
  "assets": [
    {
      "identifier": "STILLS_001",
      "mob_id": "mob_12345",
      "media_type": "stills",
      "metadata": {
        "name": "Updated Still Image Name",
        "description": "Updated description from Avid Media Composer",
        "date": "2024-01-15",
        "tags": "updated, tags, from, avid",
        "source": "Updated Source",
        "title": "Updated Title"
      }
    }
  ]
}
```

**Request Payload (Footage - Archival or Live)**:
```json
{
  "media_type": "archival",
  "assets": [
    {
      "identifier": "A075C005_250428_R3WV.mov",
      "mob_id": "mob_78901",
      "media_type": "archival",
      "metadata": {
        "source_file": "A075C005_250428_R3WV.mov",
        "name": "LF0005",
        "description": "Sunrise over Charleston Harbor",
        "date": "2025-04-28",
        "tags": "sunrise, harbor, charleston",
        "title": "Sunrise Over Charleston Harbor",
        "location": "Charleston, SC",
        "source": "20250428",
        "avid_bins": "Archive Collection 2025",
        "avid_description": "Beautiful morning light",
        "color_mode": "Color",
        "audio_type": "Stereo",
        "ff_project": "Charleston Documentary 2025",
        "reviewed_checkbox": "Yes"
      }
    }
  ]
}
```

**Response**:
```json
{
  "success": true,
  "message": "Metadata exported successfully. 1/1 assets updated.",
  "processed_count": 1,
  "successful_count": 1,
  "total_count": 1,
  "media_type": "stills",
  "results": [
    {
      "identifier": "STILLS_001",
      "success": true,
      "fields_updated": ["INFO_Description", "INFO_Date", "INFO_Source", "TAGS_List"]
    }
  ],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Media Types

### Stills (`media_type: "stills"`)
- **Identifier Field**: `INFO_STILLS_ID`
- **Supported Metadata Fields**:
  - `name` → `INFO_Name`
  - `description` → `INFO_Description`
  - `date` → `INFO_Date`
  - `tags` → `TAGS_List`
  - `source` → `INFO_Source`
  - `title` → `INFO_Title`

### Archival Footage (`media_type: "archival"`)
- **Identifier Field**: `INFO_Filename`
- **Layout**: `Footage`
- **Supported Metadata Fields**:
  - `name` → `INFO_Name`
  - `description` → `INFO_Description`
  - `title` → `INFO_Title`
  - `location` → `INFO_Location`
  - `source` → `INFO_Source`
  - `date` → `INFO_Date`
  - `tags` → `TAGS_List`
  - `color_mode` → `INFO_ColorMode`
  - `audio_type` → `INFO_AudioType`
  - `avid_description` → `INFO_AvidDescription`
  - `ff_project` → `INFO_FF_Project`
  - `reviewed_checkbox` → `INFO_Reviewed_Checkbox`
  - `avid_bins` → `INFO_AvidBins`

### Live Footage (`media_type: "live_footage"`)
- **Identifier Field**: `INFO_Filename`
- **Layout**: `Footage`
- **Supported Metadata Fields**: Same as archival footage

## Error Handling

### Common Error Responses

**400 Bad Request**:
```json
{
  "detail": "Missing media_type in payload"
}
```

**404 Not Found**:
```json
{
  "detail": "Record not found"
}
```

**500 Internal Server Error**:
```json
{
  "detail": "Script error: Invalid JSON payload"
}
```

### Error Handling in Responses

**Partial Success** (some records found, some not):
```json
{
  "success": true,
  "message": "Metadata exported successfully. 1/2 assets updated.",
  "successful_count": 1,
  "total_count": 2,
  "results": [
    {
      "identifier": "STILLS_001",
      "success": true,
      "fields_updated": ["INFO_Description"]
    },
    {
      "identifier": "STILLS_002",
      "success": false,
      "error": "Record not found"
    }
  ]
}
```

## Usage Examples

### Python Example

```python
import requests
import json

# API Configuration
API_BASE_URL = "http://localhost:8000"
API_KEY = "your_api_key"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# Import metadata from FileMaker Pro
def import_metadata(media_type, identifiers):
    payload = {
        "media_type": media_type,
        "identifiers": identifiers
    }
    
    response = requests.post(
        f"{API_BASE_URL}/metadata-bridge/query",
        headers=headers,
        json=payload
    )
    
    return response.json()

# Export metadata to FileMaker Pro
def export_metadata(media_type, assets):
    payload = {
        "media_type": media_type,
        "assets": assets
    }
    
    response = requests.post(
        f"{API_BASE_URL}/metadata-bridge/export",
        headers=headers,
        json=payload
    )
    
    return response.json()

# Example usage
stills_metadata = import_metadata("stills", ["STILLS_001", "STILLS_002"])
print(json.dumps(stills_metadata, indent=2))
```

### cURL Examples

**Import Metadata**:
```bash
curl -X POST "http://localhost:8000/metadata-bridge/query" \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "media_type": "stills",
    "identifiers": ["STILLS_001", "STILLS_002"]
  }'
```

**Export Metadata**:
```bash
curl -X POST "http://localhost:8000/metadata-bridge/export" \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "media_type": "stills",
    "assets": [
      {
        "identifier": "STILLS_001",
        "mob_id": "mob_12345",
        "media_type": "stills",
        "metadata": {
          "description": "Updated description",
          "tags": "updated, tags"
        }
      }
    ]
  }'
```

## Performance Considerations

### Timeouts
- **Import (query)**: 60 seconds
- **Export**: 120 seconds

### Batch Processing
- Both endpoints support batch processing
- Recommended batch size: 10-50 items per request
- Larger batches may require longer timeouts

### Error Recovery
- Individual record failures don't stop batch processing
- Each record is processed independently
- Detailed error reporting for each item

## Security

### Authentication
- All endpoints require `X-API-Key` header
- API key is configurable via environment variable `FM_AUTOMATION_KEY`

### Data Validation
- Payload structure validation
- Media type validation
- Required field validation

## Testing

### Test Payloads
Test payloads are available in the `/temp/` directory:
- `test_metadata_export_payload.json` - Stills export test
- `test_footage_export_payload.json` - Footage export test

### Manual Testing
```bash
# Test stills export
python3 jobs/metadata-from-avid.py temp/test_metadata_export_payload.json

# Test footage export  
python3 jobs/metadata-from-avid.py temp/test_footage_export_payload.json
```

## Troubleshooting

### Common Issues

1. **"Record not found" errors**
   - Verify the identifier exists in FileMaker Pro
   - Check the media type matches the record type
   - Ensure the identifier format is correct

2. **Timeout errors**
   - Reduce batch size
   - Check network connectivity to FileMaker Pro
   - Verify FileMaker Pro server performance

3. **Authentication errors**
   - Verify API key is correct
   - Check FileMaker Pro authentication
   - Ensure token refresh is working

### Debug Mode
Enable debug logging by setting environment variable:
```bash
export FM_DEBUG=true
```

## Related Files

- `jobs/metadata-to-avid.py` - Import script (FileMaker → Avid)
- `jobs/metadata-from-avid.py` - Export script (Avid → FileMaker)
- `API.py` - Main API server with endpoints
- `config.py` - FileMaker Pro configuration 