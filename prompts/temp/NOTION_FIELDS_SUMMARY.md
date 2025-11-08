# Notion Integration - Fields Summary

## Currently Implemented (Step 4)

The Music AutoLog workflow now pulls the following fields from your Notion database:

### Primary Fields
| Notion Property | FileMaker Field | Type | Purpose |
|----------------|-----------------|------|---------|
| `Track Title` | `INFO_Song_Name` (match only) | title | Used for matching |
| `Artist` | `INFO_Artist` (match only) | rich_text | Used for matching |
| `Album` | `INFO_Album` (match only) | rich_text | Used for matching |
| **`ISRC/UPC`** | **`INFO_ISRC_UPC_Code`** | rich_text | **✅ RETRIEVED** |
| **`Type`** | **`INFO_Cue_Type`** | multi_select | **✅ RETRIEVED** |
| **`URL`** | **`SPECS_URL`** | url | **✅ RETRIEVED** |
| **`Performed By`** | **`INFO_PerformedBy`** | rich_text | **✅ RETRIEVED** |
| **`Composer`** | **`PUBLISHING_Composer`** | rich_text | **✅ RETRIEVED** |

### Smart Update Logic

The script only updates fields that are currently **empty** in FileMaker:

```python
# Only update if field is empty in FileMaker
if not current_isrc and notion_isrc:
    update_isrc()

if not current_type and notion_type:
    update_type()

if not current_url and notion_url:
    update_url()
```

**This means:**
- Won't overwrite existing data
- Can run multiple times safely
- Only fills in missing information

### Example Output

```
🔍 Step 4: Query Notion Database
  -> Music ID: MX0006
  -> Song: De Gospel Train
  -> Current ISRC/UPC: (empty)
  -> Current Cue Type: (empty)
  -> Current URL: (empty)
  
  -> Querying Notion database...
  -> Found 1 potential matches
  
  -> Checking match:
     Notion Title: De Gospel Train
     Notion Artist: Fisk Jubilee Singers
     Notion Album: In Bright Mansions
     Notion ISRC/UPC: USCP50200132
     Notion Type: Source
     Notion URL: https://music.apple.com/us/album/...
  
  -> ✅ MATCH FOUND (confidence: 100%, tiebreaker: 1104)
  
  -> Updating FileMaker with Notion data...
     ISRC/UPC: USCP50200132
     Cue Type: Source
     URL: https://music.apple.com/us/album/...
  
  -> FileMaker record updated with 3 field(s) from Notion
✅ Step 4 complete: Data retrieved from Notion
```

## Available in Notion Database (Not Yet Implemented)

Your Notion "Music Options" database has **23 total properties**. Here are the ones we could add in the future:

### Metadata Fields
| Notion Property | Type | Potential FileMaker Field |
|----------------|------|---------------------------|
| `Composer` | rich_text | `PUBLISHING_Composer` |
| `Performed By` | rich_text | New field needed |
| `Release Date` | number | `INFO_Release_Year` |
| `Track Number` | number | `INFO_Track_Number` |
| `Duration` | rich_text | `SPECS_Duration` |
| `Record Date` | date | New field needed |

### Categorization Fields
| Notion Property | Type | Potential FileMaker Field |
|----------------|------|---------------------------|
| `Mood/Keywords` | multi_select | New field needed |
| `Themes` | multi_select | New field needed |
| `Instruments` | multi_select | New field needed |
| `Source` | select | `INFO_Source` |

### Status Fields
| Notion Property | Type | Potential FileMaker Field |
|----------------|------|---------------------------|
| `Downloaded` | checkbox | New field needed |
| `Removed` | checkbox | New field needed |

### Other Fields
| Notion Property | Type | Notes |
|----------------|------|-------|
| `Notes` | rich_text | Could go in a notes field |
| `File Upload` | files | Files attached in Notion |
| `All Artists` | formula | Calculated field in Notion |
| `Created By` | created_by | System field |
| `Created time` | created_time | System field |

## How to Add More Fields

To add any additional Notion property to the workflow:

1. **Update Field Mapping** in `music_autolog_04_query_notion.py`:
```python
FIELD_MAPPING = {
    # ... existing fields ...
    "composer": "PUBLISHING_Composer",  # Add new mapping
}
```

2. **Extract in Query Function** (around line 98):
```python
notion_composer = extract_notion_text(properties.get('Composer', {}))
```

3. **Add to Match Data** (around line 164):
```python
match_data = {
    # ... existing fields ...
    'composer': notion_composer,
}
```

4. **Add to Update Logic** (around line 332):
```python
if not has_composer and notion_match.get('composer'):
    update_data[FIELD_MAPPING["composer"]] = notion_match['composer'].strip()
```

5. **Update Documentation** to reflect new fields

The extraction function already handles:
- `title`, `rich_text`, `select`, `multi_select`
- `number`, `url`, `email`, `phone_number`

So most Notion property types are already supported!

## Current Status

✅ **Implemented (5 fields):**
- ISRC/UPC
- Type (Cue Type)
- URL
- Performed By
- Composer

📋 **Easily Available (9+ fields):**
- Source, Release Date, Track Number, Duration
- Mood/Keywords, Themes, Instruments
- Downloaded, Removed, Notes

🔧 **Just needs:**
- Field mapping updates
- A few lines of code per field
- FileMaker fields to exist


