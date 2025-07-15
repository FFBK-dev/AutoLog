# FileMaker Backend for Archival Research & Documentary Production

This backend system provides API endpoints and automated processing workflows for a FileMaker database supporting archival research and documentary production workflows.

## 🏗️ Architecture Overview

### Core Components

- **`API.py`** - Modern FastAPI server with job tracking and execution
- **`/jobs/`** - Individual endpoint scripts for specific operations
- **`config.py`** - Centralized FileMaker Data API session management and authentication

### System Capabilities

- **Manual Job Execution** - REST API endpoints for on-demand processing
- **Automatic Pending Item Discovery** - Workflows automatically find and process pending items
- **Batch Processing** - High-throughput parallel processing for multiple items
- **Comprehensive Job Tracking** - Real-time monitoring and detailed logging
- **Resilient Error Handling** - Automatic retry mechanisms and graceful degradation
- **Modern FastAPI Architecture** - Background tasks and structured job management

### Supported Workflows

- **Stills Processing** - Complete automation from pending items to AI description and embedding fusion ✅ **COMPLETE**
- **Footage Processing** - Multi-stage keyframe analysis, transcription, and video description generation 🔄 **NEEDS CONVERSION**
- **Marker Generation** - AI-powered video marker creation 🔄 **NEEDS CONVERSION**

## 🚀 API Endpoints

### Job Execution

#### Stills Auto-Processing (Finds Pending Items Automatically)
```bash
# Process all items with "0 - Pending File Info" status
curl -X POST "http://localhost:8081/run/stills_autolog_00_run_all" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{}'
```

#### Individual Step Processing
```bash
# Process specific step for a single item
curl -X POST "http://localhost:8081/run/stills_autolog_01_get_file_info" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": "S04871"}'
```

#### Batch Processing (Legacy - for specific items)
```bash
curl -X POST "http://localhost:8081/run/stills_autolog_complete_workflow" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_ids": ["S04871", "S04872", "S04873"]}'
```

### System Monitoring

#### Job Status and Statistics
```bash
curl -X GET "http://localhost:8081/status" \
  -H "x-api-key: supersecret"
```

Returns:
```json
{
  "jobs_submitted": 45,
  "jobs_completed": 42,
  "currently_running": 3,
  "running_jobs": ["stills_autolog_01_file_info(S04871)", "..."]
}
```

### Workflow Benefits
- **Automatic Discovery**: No need to specify which items to process
- **Reduced HTTP overhead**: One API call processes all pending items
- **Parallel processing**: Items processed simultaneously on server
- **Comprehensive reporting**: Detailed status for each item
- **Better performance**: Significant speedup for large batches

## 🔄 Automatic Pending Item Discovery

The main workflow (`stills_autolog_00_run_all`) automatically discovers and processes pending items instead of requiring manual specification.

### How It Works

1. **Automatic Query**: The workflow queries FileMaker for all records with "0 - Pending File Info" status
2. **Batch Processing**: Found items are processed in parallel for efficiency
3. **Comprehensive Logging**: Each item's progress is tracked and logged
4. **Resilient Processing**: Temporary failures don't stop the entire batch

### Benefits

- **Simplified Usage**: No need to query FileMaker separately to find pending items
- **Efficient Processing**: Server-side batching reduces API overhead
- **Automatic Scaling**: Handles any number of pending items
- **Better Error Handling**: Individual item failures don't affect others

## 📁 Directory Structure

```
/
├── API.py                          # Main FastAPI server
├── config.py                       # FileMaker session/auth management
├── README.md                       # This file
├── .cursorrules                    # Development conventions
├── /jobs/                          # API endpoint scripts
│   ├── stills_autolog_00_run_all.py           # Main workflow - auto-finds pending items
│   ├── stills_autolog_01_get_file_info.py
│   ├── stills_autolog_02_copy_to_server.py
│   ├── stills_autolog_03_parse_metadata.py
│   ├── stills_autolog_04_scrape_url.py
│   ├── stills_autolog_05_generate_description.py
│   ├── stills_autolog_06_generate_embeddings.py
│   ├── stills_autolog_07_apply_tags.py
│   ├── stills_autolog_08_fuse_embeddings.py
│   └── stills_autolog_complete_workflow.py     # Legacy - for specific items
├── /prompts/                       # AI prompt management
│   ├── prompts.json                # AI prompts (auto-generated)
│   ├── update_prompts.py           # Script to rebuild prompts.json
│   ├── caption_AF.txt              # Individual prompt files (edit these!)
│   ├── caption_OCF.txt
│   ├── description_AF.txt
│   ├── description_OCF.txt
│   └── stills_ai_description.txt
└── /legacy/                        # Scripts to be converted
    ├── AutoLog_Footage.py          # ➡️ Convert to footage workflow
    └── Generate_Markers.py         # ➡️ Convert to marker workflow
```

## 📝 Prompt Management

The system uses AI prompts for various processing tasks. These are managed through an easy-to-edit text file system.

### Workflow

1. **Edit prompts** - Navigate to the `prompts/` directory and edit any `.txt` file using your favorite text editor
2. **Update the system** - Run the update script when you're ready to apply changes:
   ```bash
   cd prompts
   python update_prompts.py
   ```
3. **Automatic deployment** - The script rebuilds `prompts.json` which is used by the application

### Available Prompts

- `caption_AF.txt` - Archival footage frame captioning (used in legacy footage processing)
- `caption_OCF.txt` - Original camera footage captioning (used in legacy footage processing)
- `description_AF.txt` - Archival footage description generation (used in legacy footage processing)
- `description_OCF.txt` - Original camera footage description (used in legacy footage processing)
- `stills_ai_description.txt` - Historical image description generation (actively used in stills workflow)

### Benefits

✅ **User-friendly editing** - Plain text files with natural formatting  
✅ **Version control friendly** - Individual files are easier to track in git  
✅ **IDE support** - Full syntax highlighting and editing features  
✅ **Simple workflow** - Edit text files and run one update script  
✅ **No JSON syntax errors** - System handles all JSON formatting automatically
✅ **Automatic cleanup** - Only actively used prompts are maintained

### Example Usage

```bash
# Edit a prompt for better results
nano prompts/stills_ai_description.txt

# Apply the changes
cd prompts && python update_prompts.py

# The updated prompts.json is now ready for use
```

## 🔧 Modern Architecture Patterns

### FastAPI Application
```python
app = FastAPI(title="FM Automation API")

@app.on_event("startup")
async def startup_event():
    logging.info("🚀 Starting FM Automation API")

@app.on_event("shutdown")
async def shutdown_event():
    logging.info("🔄 Shutting down FM Automation API")
```

### Background Task Management
```python
@app.post("/run/{job}")
def run_job(background_tasks: BackgroundTasks):
    job_id = job_tracker.submit_job(job_name, args)
    background_tasks.add_task(run_job_with_tracking, job_id, cmd)
    return {"job_id": job_id}
```

### Enhanced Job Tracking
```python
class JobTracker:
    def __init__(self):
        self.jobs_submitted = 0
        self.jobs_completed = 0
        self.current_jobs = {}
        self.lock = threading.Lock()
    
    def submit_job(self, job_name: str, args: list) -> str:
        with self.lock:
            job_id = f"{job_name}_{self.jobs_submitted}_{int(time.time())}"
            # Track job details with timestamps
            return job_id
```

## 🔧 Core Conventions

### 1. Main Workflow Script Pattern

The primary workflow script (`stills_autolog_00_run_all.py`) follows this pattern:

```python
#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# No longer takes arguments - auto-discovers pending items
__ARGS__ = []

def find_pending_items(token):
    """Find all items with '0 - Pending File Info' status."""
    query = {
        "query": [{FIELD_MAPPING["status"]: "0 - Pending File Info"}],
        "limit": 100
    }
    # Query FileMaker and extract stills_ids
    return stills_ids

if __name__ == "__main__":
    token = config.get_token()
    stills_ids = find_pending_items(token)
    
    if not stills_ids:
        print("✅ No pending items found")
        sys.exit(0)
    
    # Process items in batch
    results = run_batch_workflow(stills_ids, token)
```

### 2. Individual Job Script Pattern

Individual job scripts follow this enhanced pattern:

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
__ARGS__ = ["stills_id"]

# Field mapping dictionary
FIELD_MAPPING = {
    "local_key": "FILEMAKER_FIELD_NAME",
    "status": "AutoLog_Status",
    # Always use descriptive local keys
}

def main(stills_id):
    """Main processing function with enhanced error handling"""
    try:
        # Processing logic with retry mechanisms
        print(f"SUCCESS [script_name]: {stills_id}")
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"ERROR [script_name] on {stills_id}: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(1)
    main(sys.argv[1])
```

### 3. Enhanced Error Handling with Retry Logic

```python
def get_current_record_data(record_id, token, max_retries=3):
    """Get current record data from FileMaker with retry logic."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            response = requests.get(
                config.url(f"layouts/Stills/records/{record_id}"), 
                headers=config.api_headers(current_token), 
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                current_token = config.get_token()  # Refresh token
                continue
            
            response.raise_for_status()
            return response.json()['response']['data'][0], current_token
            
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
    
    return None, current_token
```

### 4. Logging Standards

```python
# Emoji-based logging for visual clarity
logging.info(f"🚀 Starting operation: {operation_name}")
logging.info(f"📋 Processing item: {item_id}")
logging.info(f"✅ Success: {operation_description}")
logging.error(f"❌ Error: {error_description}")
logging.warning(f"⚠️ Warning: {warning_description}")
logging.info(f"🔍 Debug: {debug_info}")
```

### 5. Configuration Management

All FileMaker API access goes through `config.py`:

```python
import config

# Get authenticated token
token = config.get_token()

# Find records
record_id = config.find_record_id(token, "Layout_Name", {"field": "==value"})

# Enhanced API calls with error handling
response = requests.post(
    config.url("layouts/Layout_Name/_find"),
    headers=config.api_headers(token),
    json=query,
    verify=False
)

if response.status_code == 401:
    raise Exception("Token expired")
elif response.status_code == 404:
    logging.info("No records found")
    return []
else:
    response.raise_for_status()
```

## 🚀 Development Workflow

### Adding New Job Scripts

1. Create script in `/jobs/` following naming convention: `{workflow}_{step}_description.py`
2. Define `__ARGS__` and `FIELD_MAPPING` at the top
3. Implement main function with proper error handling and logging
4. Test with both single items and batch processing
5. Add to API.py's job discovery system

### Modern API Development

1. Use FastAPI with proper startup/shutdown events
2. Implement background tasks with comprehensive job tracking
3. Add detailed logging with emoji indicators
4. Include health check and status endpoints
5. Follow resilient error handling patterns

### Converting Legacy Scripts

Legacy scripts should be modernized with:

1. **Individual job scripts** for each processing stage
2. **API integration** instead of standalone controllers
3. **Enhanced error handling** with retry logic
4. **Batch processing support** for improved performance
5. **Automatic item discovery** instead of manual specification

## 🔐 Environment Variables

Required environment variables:

```bash
FILEMAKER_SERVER=10.0.222.144
FILEMAKER_USERNAME=Background  
FILEMAKER_PASSWORD=july1776
OPENAI_API_KEY=sk-proj-...
FM_AUTOMATION_KEY=supersecret  # API authentication
AUTOLOG_DEBUG=false           # Enable debug mode
```

## 📊 FileMaker Integration

### Field Naming Conventions

- `AutoLog_Status` - Workflow status tracking
- `AI_DevConsole` - User-friendly error messages  
- `INFO_*` - Metadata fields
- `SPECS_*` - Technical specification fields
- `AI_*` - AI-generated content fields

### Status Management

```python
# Modern status progression
WORKFLOW_STEPS = [
    {
        "step_num": 1,
        "status_before": "0 - Pending File Info",
        "status_after": "1 - File Info Complete",
        "script": "stills_autolog_01_get_file_info.py",
        "description": "Get File Info"
    },
    # ... more steps
]
```

### Automatic Pending Item Query

```python
def find_pending_items(token):
    """Find all items with '0 - Pending File Info' status."""
    query = {
        "query": [{FIELD_MAPPING["status"]: "0 - Pending File Info"}],
        "limit": 100  # Reasonable batch size
    }
    
    response = requests.post(
        config.url("layouts/Stills/records/_find"),
        headers=config.api_headers(token),
        json=query,
        verify=False
    )
    
    # Extract and return stills_ids
    return stills_ids
```

## 🧪 Testing & Debugging

### Debug Mode Support
```bash
# Enable debug mode for real-time output
export AUTOLOG_DEBUG=true
```

### Comprehensive Monitoring
- Real-time job tracking via `/status` endpoint
- Detailed console logging with emoji indicators
- Individual item progress tracking in batch operations
- Graceful error reporting with context

## 📈 Performance & Scalability

### Concurrency Management
- **API-level**: FastAPI BackgroundTasks for job submission
- **Job-level**: ThreadPoolExecutor with reasonable limits (max 10 workers)
- **Batch-level**: Automatic discovery and parallel processing

### Resource Optimization
- Automatic batching of pending items (limit: 100 per query)
- Efficient parallel processing with progress tracking
- Graceful error handling to prevent cascade failures
- Automatic cleanup of completed job records

## 🔄 System Resilience

### Automatic Recovery Features
- **Token refresh** - Handles FileMaker authentication expiration
- **Retry mechanisms** - Exponential backoff for network issues
- **Graceful degradation** - Continues processing on partial failures
- **Resilient workflows** - Individual item failures don't stop batch processing

### Health Monitoring
```python
# System health indicators
{
    "jobs_submitted": 45,
    "jobs_completed": 42,
    "currently_running": 3,
    "running_jobs": ["stills_autolog_00_run_all()", "..."]
}
```

## 📋 Next Steps

1. **Convert Footage Workflow**
   - Break down `AutoLog_Footage.py` into individual job scripts
   - Integrate with modern API architecture
   - Add automatic pending item discovery

2. **Convert Marker Generation**
   - Modularize `Generate_Markers.py` functionality
   - Add to API endpoint system
   - Integrate with footage workflow

3. **Enhanced Monitoring**
   - Add web dashboard for job monitoring
   - Implement alerting for system issues
   - Add performance metrics collection

4. **Documentation & Testing**
   - Document new field mappings and workflows
   - Create comprehensive test suite
   - Update deployment procedures 