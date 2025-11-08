# Multi-User REVERSE_IMAGE_SEARCH Architecture

## The Challenge

Users on different devices need to:
1. Import local images (from their own computers)
2. Preprocess images (convert to RGB, create thumbnails)
3. Generate embeddings
4. **Without** having Python installed on every device

## The Solution: Server-Side Processing

### Architecture Overview

```
┌─────────────────┐
│ User's Computer │
│  (any device)   │
└────────┬────────┘
         │ 1. Insert local image to container
         │
    ┌────▼─────────┐
    │  FileMaker   │
    │   Client     │
    └────┬─────────┘
         │ 2. Export container to server temp location
         │
    ┌────▼──────────────┐
    │ FileMaker Server  │
    │                   │
    │ ┌───────────────┐ │
    │ │ Container     │ │ 3. Image now on server
    │ │ Temp Export   │ │
    │ └───────┬───────┘ │
    │         │         │
    │ ┌───────▼───────┐ │
    │ │ Python Script │ │ 4. Preprocessing
    │ │ (via API)     │ │    - RGB conversion
    │ └───────┬───────┘ │    - Thumbnail creation
    │         │         │
    │ ┌───────▼───────┐ │
    │ │ Upload to     │ │ 5. Upload preprocessed
    │ │ Container     │ │    thumbnail
    │ └───────────────┘ │
    └───────────────────┘
         │
         │ 6. Generate embedding from thumbnail
         │
    ┌────▼─────────┐
    │  CLIP Model  │
    │  (FileMaker) │
    └──────────────┘
```

## Implementation

### Step 1: User Imports Local Image

User's FileMaker client:

```javascript
# Button: "Import Image"

# Let user select local file
Set Variable [$imagePath; Get(DesktopPath) & "image.jpg"]

# Show file dialog
Set Variable [$selectedFile; 
    GetFile(
        "Select image to import";
        $imagePath;
        "*.jpg;*.jpeg;*.png;*.tif;*.tiff"
    )
]

# Insert into temporary container field
Insert File [REVERSE_IMAGE_SEARCH::TEMP_CONTAINER; $selectedFile]

# Store original filename for reference
Set Field [REVERSE_IMAGE_SEARCH::ORIGINAL_FILENAME; 
    Get(FileName)]

# Commit record
Commit Records/Requests []

# Proceed to preprocessing
Perform Script ["RIS - Preprocess Server Side"]
```

### Step 2: Export Container to Server Location

FileMaker script exports the container to a server-accessible location:

```javascript
# RIS - Preprocess Server Side

# Generate unique temp filename
Set Variable [$tempID; Get(UUID)]
Set Variable [$serverTempPath; 
    "/Library/FileMaker Server/Data/Scripts/temp/" & $tempID & ".jpg"
]

# Export container to server location
Export Field Contents [
    REVERSE_IMAGE_SEARCH::TEMP_CONTAINER;
    $serverTempPath;
    Automatically open file: Off
]

# Store temp path for Python script
Set Field [REVERSE_IMAGE_SEARCH::TEMP_PATH; $serverTempPath]
Commit Records/Requests []

# Call API to preprocess
Perform Script ["RIS - Call Preprocessing API"; 
    Parameter: JSONSetElement("{}"; 
        "record_id"; Get(RecordID); JSONNumber
    )
]
```

### Step 3: Call Python Preprocessing API

```javascript
# RIS - Call Preprocessing API

Set Variable [$recordID; Get(RecordID)]
Set Variable [$apiURL; "http://localhost:8000/run/ris_preprocess_image"]
Set Variable [$payload; 
    JSONSetElement("{}"; 
        ["record_id"; $recordID; JSONNumber]
    )
]

# Call API (runs on server)
Insert from URL [
    $apiURL;
    $$apiResult;
    cURL Options: 
        "-X POST " &
        "-H 'Content-Type: application/json' " &
        "-d '" & $payload & "'"
]

# Parse response
Set Variable [$jobID; JSONGetElement($$apiResult; "job_id")]
Set Variable [$status; JSONGetElement($$apiResult; "status")]

# Show progress
Show Custom Dialog [
    "Processing..."; 
    "Preprocessing image on server¶Job ID: " & $jobID
]

# Optional: Poll for completion
Perform Script ["Poll Job Status"; Parameter: $jobID]
```

### Step 4: Python Processes on Server

The Python script (running on server via API):

```python
# jobs/ris_preprocess_image.py (already created)

def process_ris_record(record_id, token):
    # 1. Get record data
    record = get_record_from_filemaker(record_id)
    
    # 2. Get temp path (exported container)
    temp_path = record['TEMP_PATH']
    
    # 3. Process image (RGB + thumbnail)
    thumbnail_path = create_rgb_thumbnail(temp_path)
    
    # 4. Upload thumbnail to IMAGE_CONTAINER
    upload_to_container(record_id, thumbnail_path)
    
    # 5. Clean up temp files
    cleanup_temp_files()
    
    return True
```

### Step 5: Generate Embedding

After preprocessing completes:

```javascript
# RIS - Generate Embedding (called after preprocessing)

# Check if thumbnail exists
If [IsEmpty(REVERSE_IMAGE_SEARCH::IMAGE_CONTAINER)]
    Show Custom Dialog ["Error"; "Preprocessing failed"]
    Exit Script []
End If

# Clear temp fields
Set Field [REVERSE_IMAGE_SEARCH::TEMP_CONTAINER; ""]
Set Field [REVERSE_IMAGE_SEARCH::TEMP_PATH; ""]

# Generate CLIP embedding from IMAGE_CONTAINER
Perform Script on Server [
    "Generate CLIP Embedding"; 
    Parameter: Get(RecordID)
]

# Update status
Set Field [REVERSE_IMAGE_SEARCH::STATUS; "Embedding Generated"]

Show Custom Dialog ["Success"; "Image processed and embedding generated"]
```

## Required FileMaker Fields

### REVERSE_IMAGE_SEARCH Table

| Field | Type | Purpose |
|-------|------|---------|
| `TEMP_CONTAINER` | Container | Temporary storage for user's local file |
| `TEMP_PATH` | Text | Server path where container was exported |
| `IMAGE_CONTAINER` | Container | Final preprocessed RGB thumbnail |
| `PATH` | Text | Original import path (for reference) |
| `ORIGINAL_FILENAME` | Text | User's original filename |
| `EMBEDDING` | Text | CLIP embedding vector |
| `MATCH COUNT` | Number | Number of similar images found |
| `MATCHES` | Text | List of matching record IDs |
| `STATUS` | Text | Processing status |

## Required Server Setup

### 1. Server Temp Directory

Create temp directory accessible to both FileMaker and Python:

```bash
# On FileMaker Server machine
sudo mkdir -p /Library/FileMaker\ Server/Data/Scripts/temp
sudo chmod 777 /Library/FileMaker\ Server/Data/Scripts/temp
```

### 2. Python Backend API Running

Ensure your FastAPI server is running:

```bash
cd /Users/admin/Documents/Github/Filemaker-Backend
python3 -m uvicorn API:app --host 0.0.0.0 --port 8000
```

Or use a process manager (systemd, launchd, etc.) to keep it running.

### 3. Network Access

- FileMaker clients must reach FileMaker Server
- FileMaker Server must reach Python API (localhost:8000)
- Python can access FileMaker Data API (10.0.222.144)

## User Workflow

### Simple 2-Button Interface

**Button 1: "Import & Process Image"**
```javascript
# Combines import + preprocessing
Perform Script ["RIS - Import Local Image"]
# This script does:
# 1. File dialog
# 2. Insert to container
# 3. Export to server
# 4. Call preprocessing API
# 5. Wait for completion
```

**Button 2: "Generate Embedding"**
```javascript
# Only enabled after preprocessing
Perform Script ["RIS - Generate Embedding"]
```

### Or Combined Single Button

**Button: "Import & Generate Embedding"**
```javascript
# Does everything in one click
Perform Script ["RIS - Complete Workflow"]

# This script:
# 1. Import image
# 2. Export to server
# 3. Preprocess via API
# 4. Generate embedding
# 5. Clean up temp files
```

## Advantages of This Architecture

✅ **No Python on user devices** - Everything runs on server
✅ **Works with local files** - Users select files from their computer
✅ **Centralized processing** - Consistent preprocessing for all users
✅ **Scalable** - Server handles all heavy lifting
✅ **Simple UX** - User just imports image and clicks button
✅ **Cross-platform** - Works on Mac, Windows, iOS (FileMaker Go)

## Alternative: Pure FileMaker Approach

If you can't use Python API, you can use FileMaker's built-in tools:

```javascript
# Export container
Export Field Contents [field; path]

# Call shell script on server
Perform Script on Server ["Execute Shell Command"; 
    Parameter: "python3 /path/to/script.py " & $path
]

# Re-import processed thumbnail
Insert File [field; $processedPath]
```

But the API approach is more robust and easier to debug.

## Testing the Setup

### Test 1: Manual File

1. User imports a local JPG file
2. FileMaker exports to server temp directory
3. Check that file appears in `/Library/FileMaker Server/Data/Scripts/temp/`

### Test 2: API Call

```bash
# Manually test preprocessing
curl -X POST "http://localhost:8000/run/ris_preprocess_image" \
  -H "Content-Type: application/json" \
  -d '{"record_id": "184"}'
```

### Test 3: End-to-End

1. User clicks "Import & Process" button
2. Selects local image
3. Wait ~5 seconds
4. Check IMAGE_CONTAINER field populated
5. Click "Generate Embedding"
6. Verify EMBEDDING field populated

## Troubleshooting

### "Cannot export file to server"
- Check server temp directory exists
- Verify write permissions (777 or appropriate)
- Ensure FileMaker Server can write to that location

### "API call fails"
- Check Python API is running (`curl http://localhost:8000/health`)
- Verify network connectivity
- Check API logs for errors

### "Preprocessing times out"
- Increase timeout in FileMaker script
- Check Python script isn't hanging
- Monitor server resources

### "Thumbnail not uploaded"
- Verify Data API permissions (see FILEMAKER_DATA_API_PERMISSIONS.md)
- Check container field is editable
- Ensure temp file still exists when uploading

## Security Considerations

### Temp File Cleanup

Add cleanup script that runs periodically:

```javascript
# Scheduled Script: "Clean Temp Files"
# Runs every hour

# Delete temp files older than 1 hour
Set Variable [$cmd; 
    "find /Library/FileMaker\ Server/Data/Scripts/temp/ -mmin +60 -delete"
]
Perform Script on Server ["Execute Shell Command"; Parameter: $cmd]
```

### Container Field Security

- Don't store sensitive images in TEMP_CONTAINER longer than needed
- Clear TEMP_CONTAINER after processing
- Use privilege sets to restrict who can view/edit containers

## Cost Considerations

- **Server resources**: Python preprocessing uses CPU/memory
- **Storage**: Temp files and containers take disk space
- **Network**: Uploading images from clients to server

## Summary

✅ **For multi-user environments**: Use server-side preprocessing via API
✅ **Users**: Just import local files via FileMaker
✅ **Server**: Handles all Python preprocessing
✅ **Result**: Consistent embeddings, no per-device setup

🎯 **Next Steps**:
1. Fix Data API permissions (see FILEMAKER_DATA_API_PERMISSIONS.md)
2. Set up server temp directory
3. Ensure Python API is running
4. Create FileMaker scripts for import workflow
5. Test with one user/device first

