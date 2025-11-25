# Avid Metadata Bridge - Current Field Reference

**Last Updated**: 2025-01-XX  
**Changelog**: Added `SPECS_TimeOfDay` field for Footage (Import & Export)  
**Purpose**: Reference document for coordinating metadata expansion between FileMaker Backend and Avid Media Composer

## Overview

The metadata bridge supports **bidirectional synchronization**:
- **Import (Query)**: FileMaker Pro → Avid Media Composer (`/metadata-bridge/query`)
- **Export**: Avid Media Composer → FileMaker Pro (`/metadata-bridge/export`)

---

## 1. METADATA IMPORT (FileMaker → Avid)

### Endpoint: `POST /metadata-bridge/query`

**What FileMaker sends to Avid when Avid requests metadata**

### Stills (`media_type: "stills"`)

**Identifier**: `INFO_STILLS_ID` (used to look up records)

**Fields Returned to Avid**:

| Avid Field Name | FileMaker Field Name | Type | Notes |
|----------------|---------------------|------|-------|
| `identifier` | `INFO_STILLS_ID` | String | The stills ID itself |
| `info_description` | `INFO_Description` | String | Image description |
| `info_date` | `INFO_Date` | String | Date in format from FileMaker |
| `info_source` | `INFO_Source` | String | Source information |
| `tags_list` | `TAGS_List` | String | Comma-separated tags |
| `info_reviewed_checkbox` | `INFO_Reviewed_Checkbox` | String | "Yes" or "No" (converted from FileMaker checkbox) |
| `info_avid_bins` | `INFO_AvidBins` | String | Avid bin information |

**Example Response**:
```json
{
  "identifier": "STILLS_001",
  "found": true,
  "info_description": "Sample still image description",
  "info_date": "2024-01-15",
  "info_source": "Sample Source",
  "tags_list": "sample, test, stills",
  "info_reviewed_checkbox": "Yes",
  "info_avid_bins": "Stills Collection 2024"
}
```

---

### Footage - Archival & Live (`media_type: "archival"` or `"live_footage"`)

**Identifier**: `INFO_Filename` (the source file name, e.g., "A075C005_250428_R3WV.mov")

**Fields Returned to Avid**:

| Avid Field Name | FileMaker Field Name | Type | Notes |
|----------------|---------------------|------|-------|
| `identifier` | `INFO_Filename` | String | The filename itself |
| `ftg_id` | `INFO_FTG_ID` | String | Footage ID (e.g., "LF0005") |
| `info_description` | `INFO_Description` | String | Footage description |
| `info_title` | `INFO_Title` | String | Title of the footage |
| `info_location` | `INFO_Location` | String | Location where footage was shot |
| `info_source` | `INFO_Source` | String | Source information |
| `info_date` | `INFO_Date` | String | Date in format from FileMaker |
| `tags_list` | `TAGS_List` | String | Comma-separated tags |
| `info_color_mode` | `INFO_ColorMode` | String | Color/B&W, etc. |
| `info_audio_type` | `INFO_AudioType` | String | Stereo/Mono/etc. |
| `info_avid_description` | `INFO_AvidDescription` | String | Avid-specific description field |
| `info_ff_project` | `INFO_FF_Project` | String | Final Fantasy project reference |
| `info_reviewed_checkbox` | `INFO_Reviewed_Checkbox` | String | "Yes" or "No" (converted from FileMaker checkbox) |
| `info_avid_bins` | `INFO_AvidBins` | String | Avid bin information |
| `info_time_of_day` | `SPECS_TimeOfDay` | String | Time of day category (Morning, Midday, Evening, Night) |

**Example Response**:
```json
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
  "info_color_mode": "Color",
  "info_audio_type": "Stereo",
  "info_avid_description": "Beautiful morning light",
  "info_ff_project": "Charleston Documentary 2025",
  "info_reviewed_checkbox": "Yes",
  "info_avid_bins": "Archive Collection 2025",
  "info_time_of_day": "Morning"
}
```

---

## 2. METADATA EXPORT (Avid → FileMaker)

### Endpoint: `POST /metadata-bridge/export`

**What Avid sends to FileMaker to update records**

### Stills (`media_type: "stills"`)

**Identifier**: `identifier` field must match `INFO_STILLS_ID` in FileMaker

**Fields Avid Can Send**:

| Avid Sends | FileMaker Receives | FileMaker Field Updated | Type | Notes |
|-----------|-------------------|------------------------|------|-------|
| `metadata.description` | `description` | `INFO_Description` | String | ✓ Currently supported |
| `metadata.date` | `date` | `INFO_Date` | String | ✓ Currently supported |
| `metadata.source` | `source` | `INFO_Source` | String | ✓ Currently supported |
| `metadata.tags` | `tags` | `TAGS_List` | String | ✓ Currently supported |
| `metadata.reviewed_checkbox` | `reviewed_checkbox` | `INFO_Reviewed_Checkbox` | String | ✓ Currently supported ("Yes"/"No") |
| `metadata.avid_bins` | `avid_bins` | `INFO_AvidBins` | String | ✓ Currently supported |
| `metadata.name` | `name` | ❌ Not mapped | String | ⚠️ Field doesn't exist in FileMaker Stills layout |
| `metadata.title` | `title` | ❌ Not mapped | String | ⚠️ Field doesn't exist in FileMaker Stills layout |

**Special Behavior**: When metadata is updated, FileMaker automatically sets `AutoLog_Status` to `"6 - Generating Embeddings"` to trigger embedding regeneration.

**Example Request from Avid**:
```json
{
  "media_type": "stills",
  "assets": [
    {
      "identifier": "STILLS_001",
      "mob_id": "mob_12345",
      "media_type": "stills",
      "metadata": {
        "description": "Updated description from Avid",
        "date": "2024-01-15",
        "tags": "updated, tags, from, avid",
        "source": "Updated Source",
        "reviewed_checkbox": "Yes",
        "avid_bins": "Updated Bin Structure"
      }
    }
  ]
}
```

---

### Footage - Archival & Live (`media_type: "archival"` or `"live_footage"`)

**Identifier**: `identifier` field must match `INFO_Filename` in FileMaker (the source file name)

**Fields Avid Can Send**:

| Avid Sends | FileMaker Receives | FileMaker Field Updated | Type | Notes |
|-----------|-------------------|------------------------|------|-------|
| `metadata.description` | `description` | `INFO_Description` | String | ✓ Currently supported |
| `metadata.title` | `title` | `INFO_Title` | String | ✓ Currently supported |
| `metadata.location` | `location` | `INFO_Location` | String | ✓ Currently supported |
| `metadata.source` | `source` | `INFO_Source` | String | ✓ Currently supported |
| `metadata.date` | `date` | `INFO_Date` | String | ✓ Currently supported |
| `metadata.tags` | `tags` | `TAGS_List` | String | ✓ Currently supported |
| `metadata.color_mode` | `color_mode` | `INFO_ColorMode` | String | ✓ Currently supported |
| `metadata.audio_type` | `audio_type` | `INFO_AudioType` | String | ✓ Currently supported |
| `metadata.avid_description` | `avid_description` | `INFO_AvidDescription` | String | ✓ Currently supported |
| `metadata.ff_project` | `ff_project` | `INFO_FF_Project` | String | ✓ Currently supported |
| `metadata.reviewed_checkbox` | `reviewed_checkbox` | `INFO_Reviewed_Checkbox` | String | ✓ Currently supported ("Yes"/"No") |
| `metadata.avid_bins` | `avid_bins` | `INFO_AvidBins` | String | ✓ Currently supported |
| `metadata.time_of_day` | `time_of_day` | `SPECS_TimeOfDay` | String | ✓ Currently supported (Morning, Midday, Evening, Night) |
| `metadata.name` | `name` | ❌ Not mapped | String | ⚠️ Field doesn't exist in FileMaker Footage layout |

**Special Behavior**: When metadata is updated, FileMaker automatically sets `AutoLog_Status` to `"8 - Generating Embeddings"` to trigger embedding regeneration.

**Example Request from Avid**:
```json
{
  "media_type": "archival",
  "assets": [
    {
      "identifier": "A075C005_250428_R3WV.mov",
      "mob_id": "mob_78901",
      "media_type": "archival",
      "metadata": {
        "description": "Sunrise over Charleston Harbor",
        "title": "Sunrise Over Charleston Harbor",
        "location": "Charleston, SC",
        "date": "2025-04-28",
        "tags": "sunrise, harbor, charleston",
        "source": "20250428",
        "avid_bins": "Archive Collection 2025",
        "avid_description": "Beautiful morning light",
        "color_mode": "Color",
        "audio_type": "Stereo",
        "ff_project": "Charleston Documentary 2025",
        "reviewed_checkbox": "Yes",
        "time_of_day": "Morning"
      }
    }
  ]
}
```

---

## 3. Field Mappings Summary

### Complete Field Mapping Reference

#### Stills Layout

**FileMaker → Avid (Import/Query)**:
```
INFO_STILLS_ID → identifier (lookup key)
INFO_Description → info_description
INFO_Date → info_date
INFO_Source → info_source
TAGS_List → tags_list
INFO_Reviewed_Checkbox → info_reviewed_checkbox (converted: "0"="Yes", "1"="No")
INFO_AvidBins → info_avid_bins
```

**Avid → FileMaker (Export)**:
```
identifier → INFO_STILLS_ID (lookup key)
metadata.description → INFO_Description
metadata.date → INFO_Date
metadata.source → INFO_Source
metadata.tags → TAGS_List
metadata.reviewed_checkbox → INFO_Reviewed_Checkbox (converted: "Yes"="0", "No"="1")
metadata.avid_bins → INFO_AvidBins
```

#### Footage Layout (Archival & Live)

**FileMaker → Avid (Import/Query)**:
```
INFO_Filename → identifier (lookup key)
INFO_FTG_ID → ftg_id
INFO_Description → info_description
INFO_Title → info_title
INFO_Location → info_location
INFO_Source → info_source
INFO_Date → info_date
TAGS_List → tags_list
INFO_ColorMode → info_color_mode
INFO_AudioType → info_audio_type
INFO_AvidDescription → info_avid_description
INFO_FF_Project → info_ff_project
INFO_Reviewed_Checkbox → info_reviewed_checkbox (converted: "0"="Yes", "1"="No")
INFO_AvidBins → info_avid_bins
SPECS_TimeOfDay → info_time_of_day
```

**Avid → FileMaker (Export)**:
```
identifier → INFO_Filename (lookup key)
metadata.description → INFO_Description
metadata.title → INFO_Title
metadata.location → INFO_Location
metadata.source → INFO_Source
metadata.date → INFO_Date
metadata.tags → TAGS_List
metadata.color_mode → INFO_ColorMode
metadata.audio_type → INFO_AudioType
metadata.avid_description → INFO_AvidDescription
metadata.ff_project → INFO_FF_Project
metadata.reviewed_checkbox → INFO_Reviewed_Checkbox (converted: "Yes"="0", "No"="1")
metadata.avid_bins → INFO_AvidBins
metadata.time_of_day → SPECS_TimeOfDay
```

---

## 4. Data Type Conversions

### Checkbox Handling

**FileMaker → Avid**:
- FileMaker checkbox value `"0"` → Avid receives `"Yes"`
- FileMaker checkbox value `"1"` → Avid receives `"No"`
- Empty/null → Avid receives `"No"`

**Avid → FileMaker**:
- Avid sends `"Yes"` → FileMaker stores `"0"`
- Avid sends `"No"` → FileMaker stores `"1"`
- Any other value → FileMaker stores `"1"` (default to "No")

---

## 5. Response Formats

### Query Response (FileMaker → Avid)

```json
{
  "media_type": "stills",
  "requested_identifiers": ["STILLS_001", "STILLS_002"],
  "results": [
    {
      "identifier": "STILLS_001",
      "found": true,
      "info_description": "...",
      // ... other fields
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

### Export Response (Avid → FileMaker)

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
      "fields_updated": ["INFO_Description", "INFO_Date", "TAGS_List"]
    }
  ],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## 6. Current Limitations & Notes

### Fields NOT Currently Supported

**Stills**:
- ❌ `metadata.name` - Field doesn't exist in FileMaker Stills layout
- ❌ `metadata.title` - Field doesn't exist in FileMaker Stills layout

**Footage**:
- ❌ `metadata.name` - Field doesn't exist in FileMaker Footage layout

### Automatic Behaviors

1. **Embedding Regeneration**: When metadata is exported from Avid to FileMaker, the system automatically:
   - Sets `AutoLog_Status` to `"6 - Generating Embeddings"` (Stills) or `"8 - Generating Embeddings"` (Footage)
   - This triggers the embedding regeneration workflow

2. **Batch Processing**: Both endpoints support batch processing:
   - Query endpoint: Can handle 50-200+ identifiers per request
   - Export endpoint: Optimized for 10-50 assets per request

3. **Error Handling**: Individual record failures don't stop batch processing - each item is processed independently

---

## 7. Expansion Opportunities

### Potential New Fields to Add

To expand the metadata bridge, we can add new fields by:

1. **Adding to FileMaker layouts** (if fields don't exist)
2. **Updating field mappings** in:
   - `jobs/metadata-to-avid.py` (import - FileMaker → Avid)
   - `jobs/metadata-from-avid.py` (export - Avid → FileMaker)
3. **Testing with sample payloads**

### Suggested Fields for Discussion

**Stills - Potential Additions**:
- Camera settings (ISO, aperture, shutter speed)
- Photographer/credit information
- Image dimensions/resolution
- File format/compression info
- Keywords/categories (separate from tags)
- Usage rights/licensing

**Footage - Potential Additions**:
- Frame rate
- Resolution/aspect ratio
- Duration/length
- Codec information
- Timecode information
- Camera settings (if applicable)
- Crew/credit information
- Scene/take numbers

---

## 8. Technical Implementation Files

### Backend Files (FileMaker Side)

- `jobs/metadata-to-avid.py` - Handles import queries (FileMaker → Avid)
  - Function: `get_stills_metadata()`
  - Function: `get_footage_metadata()`
  - Field mappings: `STILLS_FIELD_MAPPING`, `FOOTAGE_FIELD_MAPPING`

- `jobs/metadata-from-avid.py` - Handles export updates (Avid → FileMaker)
  - Function: `update_stills_metadata()`
  - Function: `update_footage_metadata()`
  - Field mappings: `STILLS_FIELD_MAPPING`, `FOOTAGE_FIELD_MAPPING`

- `API.py` - Main API server
  - Endpoint: `POST /metadata-bridge/query` (line ~1787)
  - Endpoint: `POST /metadata-bridge/export` (line ~1842)

- `documentation/METADATA_BRIDGE_API.md` - Full API documentation

---

## 9. Contact & Coordination

**For expanding metadata fields**, coordinate:
1. Which new fields Avid can send/receive
2. Which FileMaker fields should be mapped
3. Data type conversions (if needed)
4. Testing with sample payloads

**Current Implementation**: See `jobs/metadata-to-avid.py` and `jobs/metadata-from-avid.py` for exact field mappings and conversion logic.

