# FileMaker Backend for Archival Research & Documentary Production

This backend system provides API endpoints and automated processing workflows for a FileMaker database supporting archival research and documentary production workflows.

## 🏗️ Architecture Overview

### Core Components

- **`api.py`** - Main FastAPI server that routes requests to job scripts
- **`/jobs/`** - Individual endpoint scripts for specific operations
- **`/controllers/`** - Long-running polling services for automated workflows  
- **`config.py`** - Centralized FileMaker Data API session management and authentication

### Supported Workflows

- **Stills Processing** - Complete automation from URL/file input to AI description and embedding fusion ✅ **COMPLETE**
- **Footage Processing** - Multi-stage keyframe analysis, transcription, and video description generation 🔄 **NEEDS CONVERSION**
- **Marker Generation** - AI-powered video marker creation 🔄 **NEEDS CONVERSION**

## 📁 Directory Structure

```
/
├── api.py                          # Main API server
├── config.py                       # FileMaker session/auth management
├── README.md                       # This file
├── .cursorrules                    # Development conventions
├── /jobs/                          # API endpoint scripts
│   ├── stills_autolog_01_get_file_info.py
│   ├── stills_autolog_02_copy_to_server.py
│   ├── stills_autolog_03_parse_metadata.py
│   ├── stills_autolog_04_scrape_url.py
│   ├── stills_autolog_05_generate_description.py
│   └── stills_autolog_06_fuse_embeddings.py
├── /controllers/                   # Long-running services
│   └── stills_autolog_controller.py
└── /legacy/                        # Scripts to be converted
    ├── AutoLog_Footage.py          # ➡️ Convert to footage workflow
    └── Generate_Markers.py         # ➡️ Convert to marker workflow
```

## 🔧 Core Conventions

### 1. Job Scripts (`/jobs/`)

Every job script follows this pattern:

```python
#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Script arguments definition
__ARGS__ = ["stills_id"]  # Always define expected arguments

# Field mapping dictionary
FIELD_MAPPING = {
    "local_key": "FILEMAKER_FIELD_NAME",
    "status": "AutoLog_Status",
    # ... other mappings
}

def main(stills_id):
    """Main processing function"""
    # Implementation here
    pass

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <stills_id>")
        sys.exit(1)
    
    main(sys.argv[1])
```

### 2. Controller Scripts (`/controllers/`)

Controllers manage automated workflows with these patterns:

```python
# Workflow step definitions
WORKFLOW_STEPS = {
    "1 - Status Name": {"script": "job_script.py", "next_status": "2 - Next Status"},
    # ... other steps
}

# Error formatting for user-friendly console output
def format_error_message(record_id, step_name, error_details, error_type="Processing Error"):
    """Format errors for AI_DevConsole field"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[{timestamp}] {error_type} - {step_name}\nRecord: {record_id}\nIssue: {error_details}"

# Parallel processing with ThreadPoolExecutor
def process_records_parallel(records):
    max_workers = min(10, len(records))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_record, record) for record in records]
        concurrent.futures.wait(futures)
```

### 3. Configuration Management

All FileMaker API access goes through `config.py`:

```python
import config

# Get authenticated token
token = config.get_token()

# Find records
record_id = config.find_record_id(token, "Layout_Name", {"field": "==value"})

# API calls use consistent patterns
response = requests.post(
    config.url("layouts/Layout_Name/_find"),
    headers=config.api_headers(token),
    json=query,
    verify=False  # SSL handling
)
```

### 4. SSL & Warning Handling

Consistent SSL warning suppression:

```python
import warnings
import urllib3

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)
urllib3.disable_warnings()  # If using urllib3 directly
```

### 5. Error Handling & Logging

- **User-facing errors** → FileMaker `AI_DevConsole` field with formatted messages
- **System errors** → Console output with full details
- **Timeouts** → 5-minute default for subprocess operations
- **Graceful degradation** → Continue processing other records on individual failures

### 6. Status-Based Workflows

All workflows use status fields to track progress:

```python
# Status progression
STATUSES = {
    'PENDING': '1 - Pending',
    'PROCESSING': '2 - Processing', 
    'COMPLETE': '3 - Complete',
    'ERROR': '9 - Error'
}

# State transitions in controllers
def update_status(record_id, new_status):
    payload = {"fieldData": {"Status_Field": new_status}}
    return requests.patch(config.url(f"layouts/Layout/records/{record_id}"), ...)
```

## 🚀 Development Workflow

### Adding New Job Scripts

1. Create script in `/jobs/` following naming convention: `{workflow}_{step}_description.py`
2. Define `__ARGS__` and `FIELD_MAPPING` at the top
3. Implement main function with proper error handling
4. Add to appropriate controller's `WORKFLOW_STEPS`

### Adding New Controllers

1. Create controller in `/controllers/` following naming convention: `{workflow}_controller.py`
2. Define workflow steps, field mappings, and error formatting
3. Implement polling loop with parallel processing
4. Add status-based workflow management

### Converting Legacy Scripts

Legacy scripts like `AutoLog_Footage.py` should be broken down into:

1. **Individual job scripts** for each processing stage
2. **Controller script** to manage the workflow
3. **Status field mapping** for progress tracking
4. **Error handling** with user-friendly messages

## 🔐 Environment Variables

Required environment variables:

```bash
FILEMAKER_SERVER=10.0.222.144
FILEMAKER_USERNAME=Background  
FILEMAKER_PASSWORD=july1776
OPENAI_API_KEY=sk-proj-...
```

## 📊 FileMaker Integration

### Common Field Patterns

- `AutoLog_Status` - Workflow status tracking
- `AI_DevConsole` - User-friendly error messages  
- `INFO_*` - Metadata fields
- `SPECS_*` - Technical specification fields
- `AI_*` - AI-generated content fields

### Layout Conventions

- Primary layouts match record type (e.g., "Stills", "Footage", "Keyframes")
- Consistent field naming across layouts
- Status fields for workflow management

## 🧪 Testing & Debugging

- Controllers support both polling mode and batch mode with specific IDs
- Use `AI_DevConsole` field for user-visible debugging
- Console output for system-level debugging
- Graceful error handling prevents workflow interruption

## 📈 Performance Considerations

- Parallel processing with appropriate worker limits
- Chunked record processing to prevent memory issues
- Optimized FileMaker API calls with pagination
- Resource cleanup for temporary files
- Thread-safe operations for concurrent processing

## 🔄 Workflow Status Management

Each workflow uses status fields to ensure:
- **Idempotent operations** - Safe to re-run
- **Progress tracking** - Clear workflow state
- **Error recovery** - Resume from last successful step
- **User visibility** - Status updates in FileMaker UI 

## 📋 Next Steps

1. **Convert Footage Workflow**
   - Break down `AutoLog_Footage.py` into individual job scripts
   - Create `footage_autolog_controller.py` 
   - Test with existing FileMaker data

2. **Convert Marker Generation**
   - Modularize `Generate_Markers.py` functionality
   - Create `markers_controller.py`
   - Integrate with footage workflow

3. **API Integration**
   - Add footage and marker endpoints to `api.py`
   - Ensure consistent error handling across all workflows

4. **Documentation & Testing**
   - Document new field mappings and status flows
   - Create test scripts for each workflow
   - Update deployment procedures 