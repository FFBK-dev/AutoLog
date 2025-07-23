# FileMaker Backend for Archival Research & Documentary Production

This backend system provides API endpoints and automated processing workflows for a FileMaker database supporting archival research and documentary production workflows.

## 🏗️ Architecture Overview

### Core Components

- **`API.py`** - Modern FastAPI server with job tracking and execution
- **`/jobs/`** - Individual endpoint scripts for specific operations
- **`config.py`** - Centralized FileMaker Data API session management and authentication
- **`/utils/`** - Local metadata evaluation and OpenAI client utilities

### System Capabilities

- **Manual Job Execution** - REST API endpoints for on-demand processing
- **Multi-ID Processing** - Individual endpoints support single IDs or multiple IDs in various formats
- **Automatic Pending Item Discovery** - Workflows automatically find and process pending items
- **Batch Processing** - High-throughput parallel processing for multiple items
- **Comprehensive Job Tracking** - Real-time monitoring and detailed logging with progress tracking
- **Dynamic Timeout Management** - Video length-aware timeouts and intelligent retry logic
- **Stuck Job Detection** - Automatic detection and recovery of stuck processing jobs
- **Resilient Error Handling** - Automatic retry mechanisms and graceful degradation
- **Modern FastAPI Architecture** - Background tasks and structured job management
- **Intelligent Metadata Evaluation** - URL-aware thresholds for optimal resource allocation
- **Flexible Workflow Continuation** - Individual endpoints can run complete workflows

### Supported Workflows

- **Stills Processing** - Complete automation from pending items to AI description and embedding fusion ✅ **COMPLETE**
- **Image Enhancement** - Upscaling, rotation, and thumbnail refresh utilities ✅ **COMPLETE**
- **Footage Processing** - Multi-stage keyframe analysis, transcription, and video description generation 🔄 **NEEDS CONVERSION**
- **Marker Generation** - AI-powered video marker creation 🔄 **NEEDS CONVERSION**

## 🚀 API Endpoints

### Main Workflow Execution

#### Stills Auto-Processing (Finds Pending Items Automatically)
```bash
# Process all items with "0 - Pending File Info" status
curl -X POST "http://localhost:8081/run/stills_autolog_00_run_all" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{}'
```

#### Individual Step Processing (with Multi-ID Support)

**Single ID Processing**
```bash
# Process a single item
curl -X POST "http://localhost:8081/run/stills_autolog_01_get_file_info" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": "S04871"}'
```

**Multiple IDs Processing (Multiple Formats Supported)**
```bash
# JSON array format
curl -X POST "http://localhost:8081/run/stills_autolog_01_get_file_info" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": ["S04871", "S04872", "S04873"]}'

# Comma-separated string format
curl -X POST "http://localhost:8081/run/stills_autolog_01_get_file_info" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": "S04871,S04872,S04873"}'

# Line-separated string format
curl -X POST "http://localhost:8081/run/stills_autolog_01_get_file_info" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": "S04871\nS04872\nS04873"}'

# Space-separated string format
curl -X POST "http://localhost:8081/run/stills_autolog_01_get_file_info" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": "S04871 S04872 S04873"}'
```

**Step 05 - Generate Description (Continues to Complete Workflow)**
```bash
# Processes step 05 and automatically continues through steps 06, 07, 08 to completion
curl -X POST "http://localhost:8081/run/stills_autolog_05_generate_description" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": "S04871"}'
```

### Monitoring and Recovery Tools

#### Job Monitor Utility
```bash
# Interactive tool to monitor and recover stuck jobs
python3 utils/job_monitor.py
```

The job monitor provides:
- **Real-time API status** - View current job statistics and stuck job count
- **Stuck item detection** - Find footage items stuck in processing states
- **Bulk recovery** - Reset multiple stuck items to appropriate processing states
- **Individual retry** - Retry specific failed items
- **Progress monitoring** - Real-time monitoring of job progress

#### Job Information Endpoints

**Get API Status**
```bash
curl -X GET "http://localhost:8000/status" \
  -H "x-api-key: supersecret"
```

**Get Detailed Job Information**
```bash
curl -X GET "http://localhost:8000/job/{job_id}" \
  -H "x-api-key: supersecret"
```

**List All Available Jobs**
```bash
curl -X GET "http://localhost:8000/jobs" \
  -H "x-api-key: supersecret"
```

### Image Enhancement Utilities

#### Upscale Image
```bash
# Upscale image using AI enhancement
curl -X POST "http://localhost:8081/run/stills_upscale_image" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": "S04871"}'
```

#### Rotate Thumbnail
```bash
# Rotate thumbnail 90 degrees clockwise
curl -X POST "http://localhost:8081/run/stills_rotate_thumbnail" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": "S04871"}'
```

#### Refresh Thumbnail
```bash
# Regenerate thumbnail from source image
curl -X POST "http://localhost:8081/run/stills_refresh_thumbnail" \
  -H "x-api-key: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"stills_id": "S04871"}'
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

## 🧠 Intelligent Metadata Evaluation System

The system uses an advanced **URL-aware metadata evaluation** approach that optimizes resource allocation based on improvement potential.

### Two-Tiered Evaluation Thresholds

#### When URL is Available (Stricter Threshold: 0.5)
- **Logic**: "We can improve metadata via scraping, so be demanding"
- **Outcome**: More likely to trigger URL scraping for additional metadata
- **Benefits**: Maximizes metadata quality when enhancement is possible

#### When No URL Available (Lenient Threshold: 0.3)
- **Logic**: "Cannot improve metadata anyway, so be forgiving"
- **Outcome**: More likely to proceed with existing metadata
- **Benefits**: Avoids wasted effort on impossible improvements

### Evaluation Process

```python
# Step 4 (URL Scraping) - Conditional Logic
1. Check URL availability FIRST
2. Choose appropriate threshold:
   - URL exists → Use stricter threshold (0.5)
   - No URL → Use lenient threshold (0.3)
3. Evaluate combined metadata quality
4. Decision:
   - GOOD → Skip scraping, proceed to Step 5
   - BAD + URL → Run URL scraping
   - BAD + No URL → Skip scraping, proceed to Step 5
```

### Enhanced URL Scraping (`utils/url_scraper.py`)

The system now includes a comprehensive URL scraping utility that provides:

#### **Website Type Detection & Specialized Handling**
- **CONTENTdm Sites** - Extracts rich metadata from JavaScript JSON data
- **Library of Congress** - Specialized parsing for LOC.gov
- **New York Public Library** - Enhanced NYPL.org extraction
- **Internet Archive** - Archive.org specific handling
- **HarpWeek** - Historical newspaper content extraction
- **Generic Archival Sites** - Library, museum, and archive detection

#### **Multi-Level Scraping Approach**
1. **Specialized Scrapers** - Website-specific extraction methods
2. **General HTML Parsing** - Enhanced content area detection
3. **Structured Data Extraction** - JSON-LD, definition lists, tables
4. **Selenium Fallback** - JavaScript-heavy site handling

#### **Content Quality Features**
- **Intelligent Cleaning** - Removes navigation noise and boilerplate
- **Metadata Quality Evaluation** - Advanced scoring system
- **Robust Error Handling** - Graceful degradation on failures
- **Retry Logic** - Automatic retry with exponential backoff

### Metadata Sources Evaluated

The system combines and evaluates:
- **EXIF/Technical Metadata** - Camera settings, technical specs
- **Original Description** - Embedded or parsed descriptions
- **Copyright/Attribution** - Rights and creator information
- **Source Archive** - Institutional source information
- **Archival ID** - Reference numbers and identifiers
- **Enhanced URL Content** - Rich metadata from specialized scraping

### Evaluation Criteria

- **Historical Keywords** (30% weight) - Era-specific terminology
- **Named Entity Recognition** (30% weight) - People, places, dates, organizations
- **Archival Quality Indicators** (20% weight) - Professional archival terms
- **Basic Text Quality** (20% weight) - Length and substance
- **Date Pattern Bonus** - Additional points for temporal information

### Performance Improvements

#### **Enhanced Scraping Results**
- **S05437 Example**: Improved from 182 characters to 1,600 characters (780% increase)
- **Quality Score**: Improved from 2 to 22 (1,000% increase)
- **Metadata Coverage**: Now extracts comprehensive archival metadata including:
  - Title, Creator, Date, Physical Description
  - Subject Terms, Keywords, Form/Genre
  - Collection Information, Rights, Call Numbers
  - Digitization Details, Archival Location

## 🔄 Complete Workflow Architecture

### Main Workflow Steps (`stills_autolog_00_run_all.py`)

```
Step 1: Get File Info
├── Extract file dimensions, format, size
├── Generate URL from source + archival ID
└── Status: "1 - File Info Complete"

Step 2: Copy to Server
├── Convert and copy to server location
├── Generate optimized thumbnail
└── Status: "2 - Server Copy Complete"

Step 3: Parse Metadata
├── Extract EXIF metadata
├── Parse embedded descriptions and copyright
├── Extract additional URL from EXIF if needed
└── Status: "3 - Metadata Parsed"

Step 4: Enhanced URL Scraping (Conditional - URL-Aware)
├── Check URL availability
├── Evaluate metadata quality with appropriate threshold
├── If GOOD → Skip scraping
├── If BAD + URL → Run enhanced URL scraping
├── If BAD + No URL → Skip scraping, continue workflow
└── Status: "4 - Scraping URL" (if run) or remains "3 - Metadata Parsed"

Step 5: Generate Description
├── AI analysis of image + metadata
├── Generate structured description and date
├── **AUTOMATICALLY CONTINUES** to Steps 6, 7, 8 when called as individual endpoint
└── Status: "5 - Generating Description"

Step 6: Generate Embeddings
├── Create image and text embeddings
├── Store in FileMaker for similarity search
└── Status: "6 - Generating Embeddings"

Step 7: Apply Tags (Conditional - Checkbox-Aware)
├── Check INFO_Reviewed_Checkbox value
├── If checkbox = 0 → Skip tag application
├── If checkbox = 1 or empty → Apply AI-generated tags
└── Status: "7 - Applying Tags" (if run) or remains "6 - Generating Embeddings"

Step 8: Fuse Embeddings
├── Combine image and text embeddings
├── Create final searchable embedding
└── Status: "9 - Complete"
```

### Conditional Logic Details

#### Step 4 - URL Scraping (Smart Resource Allocation)
```python
# URL-Aware Evaluation Process
if url_exists:
    threshold = 0.5  # Stricter - we can improve metadata
    context = "URL available - using stricter threshold"
else:
    threshold = 0.3  # Lenient - cannot improve metadata
    context = "No URL available - using lenient threshold"

if metadata_score >= threshold:
    skip_url_scraping()  # Metadata sufficient for threshold level
else:
    if url_exists:
        run_url_scraping()  # Try to improve metadata
    else:
        skip_and_continue()  # No improvement possible, proceed anyway
```

#### Step 7 - Tag Application (Checkbox-Aware)
```python
# INFO_Reviewed_Checkbox Logic
reviewed_checkbox = record_data.get("INFO_Reviewed_Checkbox")

if reviewed_checkbox == 0:
    skip_tag_application()  # User explicitly disabled tagging
    proceed_to_step_8()
elif reviewed_checkbox == 1 or reviewed_checkbox is empty:
    run_tag_application()  # Apply AI-generated tags
```

### Workflow Continuation Modes

#### Mode 1: Complete Workflow (`stills_autolog_00_run_all.py`)
- Automatically discovers pending items
- Runs all steps 1-8 sequentially
- Handles all conditional logic
- Optimized for batch processing

#### Mode 2: Individual Endpoint with Continuation (`stills_autolog_05_generate_description.py`)
- Can be called for specific items
- Runs step 5 (Generate Description)
- **Automatically continues** through steps 6, 7, 8 to completion
- Perfect for manual processing or re-running from step 5

#### Mode 3: Individual Step Only (Any step as subprocess)
- Called as part of main workflow
- Runs only the specific step
- Returns control to parent workflow

## 📁 Directory Structure

```
/
├── API.py                          # Main FastAPI server
├── config.py                       # FileMaker session/auth management
├── README.md                       # This file
├── .cursorrules                    # Development conventions
├── requirements.txt                # Python dependencies
├── /jobs/                          # API endpoint scripts
│   ├── stills_autolog_00_run_all.py           # Main workflow - auto-finds pending items
│   ├── stills_autolog_01_get_file_info.py     # Extract file info and generate URLs
│   ├── stills_autolog_02_copy_to_server.py    # Server copy and thumbnail generation
│   ├── stills_autolog_03_parse_metadata.py    # EXIF parsing and metadata extraction
│   ├── stills_autolog_04_scrape_url.py        # URL scraping (conditional)
│   ├── stills_autolog_05_generate_description.py  # AI description + workflow continuation
│   ├── stills_autolog_06_generate_embeddings.py   # Image/text embedding generation
│   ├── stills_autolog_07_apply_tags.py        # AI tagging (conditional)
│   ├── stills_autolog_08_fuse_embeddings.py   # Final embedding fusion
│   ├── stills_refresh_thumbnail.py            # Regenerate thumbnails
│   ├── stills_rotate_thumbnail.py             # Rotate thumbnails 90°
│   ├── stills_upscale_image.py               # AI image upscaling
│   └── template.py                           # Script template for new jobs
├── /utils/                         # Utility modules
│   ├── __init__.py
│   ├── input_parser.py                      # Multi-ID input parsing and validation
│   ├── local_metadata_evaluator.py           # URL-aware metadata evaluation
│   └── openai_client.py                     # Multi-key OpenAI client with rotation
├── /prompts/                       # AI prompt management
│   ├── prompts.json                # AI prompts (auto-generated)
│   ├── update_prompts.py           # Script to rebuild prompts.json
│   ├── caption_AF.txt              # Individual prompt files (edit these!)
│   ├── caption_LF.txt
│   ├── description_AF.txt
│   ├── description_LF.txt
│   └── stills_ai_description.txt
├── /legacy/                        # Scripts to be converted
│   ├── AutoLog_Footage.py          # ➡️ Convert to footage workflow
│   └── Generate_Markers.py         # ➡️ Convert to marker workflow
└── /workfiles/                     # Development and diagnostic scripts
    ├── audio_detection.py
    ├── Diagnostic_KeyframeInfo.py
    ├── footage_record_description.py
    ├── fuse_embeddings_OG.py
    ├── keyframes.py
    └── scene_changes.py
```

## 🖼️ Image Enhancement System

### Upscaling Workflow (`stills_upscale_image.py`)

The system provides AI-powered image upscaling with intelligent fallback mechanisms:

#### Features
- **AI Upscaling** - Uses advanced algorithms for quality enhancement
- **Automatic Fallback** - Falls back to traditional methods if AI fails
- **Format Preservation** - Maintains original image format and quality settings
- **Size Optimization** - Balances quality with file size constraints
- **Error Recovery** - Graceful handling of processing failures

#### Process
```python
1. Load original image from server path
2. Attempt AI upscaling (primary method)
3. If AI fails → Use traditional bicubic upscaling
4. Optimize for FileMaker display requirements
5. Update server file with enhanced version
6. Maintain original as backup
```

### Thumbnail Management

#### Thumbnail Rotation (`stills_rotate_thumbnail.py`)
- **Purpose**: Fix orientation issues in thumbnails
- **Operation**: 90-degree clockwise rotation
- **Preservation**: Maintains aspect ratio and quality
- **Updates**: Both thumbnail file and FileMaker container

#### Thumbnail Refresh (`stills_refresh_thumbnail.py`)
- **Purpose**: Regenerate thumbnails from source images
- **Smart Path Selection**: Prefers server path over import path
- **Quality Optimization**: Consistent thumbnail generation
- **Error Handling**: Graceful fallbacks for missing files

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

- `stills_ai_description.txt` - Historical image description generation (actively used in stills workflow)
- `caption_AF.txt` - Archival footage frame captioning (used in legacy footage processing)
- `caption_LF.txt` - Live footage captioning (used in footage processing)
- `description_AF.txt` - Archival footage description generation (used in legacy footage processing)
- `description_LF.txt` - Live footage description (used in footage processing)

### Benefits

✅ **User-friendly editing** - Plain text files with natural formatting  
✅ **Version control friendly** - Individual files are easier to track in git  
✅ **IDE support** - Full syntax highlighting and editing features  
✅ **Simple workflow** - Edit text files and run one update script  
✅ **No JSON syntax errors** - System handles all JSON formatting automatically
✅ **Automatic cleanup** - Only actively used prompts are maintained

## 🔧 Modern Architecture Patterns

### FastAPI Application with Enhanced Job Tracking
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
@app.post("/run/{job}", dependencies=[Depends(check_key)])
def run_job(job: str, background_tasks: BackgroundTasks, payload: dict = Body({})):
    """Execute a job with tracking and background processing."""
    job_id = job_tracker.submit_job(job, args)
    background_tasks.add_task(run_job_with_tracking, job_id, cmd)
    return {"job_id": job_id, "submitted": True}
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
            self.current_jobs[job_id] = {
                "job_name": job_name,
                "args": args,
                "submitted_at": datetime.now(),
                "status": "running"
            }
            return job_id
```

## 🔧 Core Conventions

### 1. Main Workflow Script Pattern

The primary workflow script (`stills_autolog_00_run_all.py`) follows this pattern with intelligent conditional logic:

```python
#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.local_metadata_evaluator import evaluate_metadata_local

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

def evaluate_metadata_quality(record_data, token, has_url=False):
    """Evaluate metadata quality using URL-aware thresholds."""
    # Combine all available metadata sources
    combined_metadata = combine_metadata(record_data)
    
    # Use local evaluator with URL awareness
    evaluation = evaluate_metadata_local(combined_metadata, has_url)
    return evaluation.get("sufficient", False)

if __name__ == "__main__":
    token = config.get_token()
    stills_ids = find_pending_items(token)
    
    if not stills_ids:
        print("✅ No pending items found")
        sys.exit(0)
    
    # Process items in batch with enhanced parallel processing
    results = run_batch_workflow(stills_ids, token)
```

### 2. Individual Job Script Pattern with Multi-ID Support

Enhanced pattern supporting both single and multiple ID processing:

```python
#!/usr/bin/env python3
import sys
import warnings
import concurrent.futures
from pathlib import Path

# Standard setup
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.input_parser import parse_input_ids, format_input_summary, validate_ids

# Script arguments definition
__ARGS__ = ["stills_id"]

# Field mapping dictionary
FIELD_MAPPING = {
    "local_key": "FILEMAKER_FIELD_NAME",
    "status": "AutoLog_Status",
    # Always use descriptive local keys
}

# Expected ID prefixes for validation
EXPECTED_ID_PREFIXES = ['S', 'F', 'AF', 'FTG']

def process_single_item(stills_id: str, token: str) -> bool:
    """Process a single item. Override with your specific logic."""
    try:
        # Your processing logic here
        print(f"  -> Processing {stills_id}")
        # ... implementation ...
        print(f"  -> ✅ Successfully processed {stills_id}")
        return True
    except Exception as e:
        print(f"  -> ❌ Error processing {stills_id}: {e}")
        return False

def process_batch_items(stills_ids: list, token: str, max_workers: int = 8) -> dict:
    """Process multiple items in parallel."""
    # Standardized batch processing implementation
    # Returns results dictionary with success/failure counts

def run_subsequent_workflow_steps(stills_id, record_id, token):
    """Continue workflow after current step (used in step 05)."""
    # Implementation for automatic workflow continuation
    
def process_single_item_with_workflow(stills_id, token, continue_workflow=False):
    """Process item with optional workflow continuation."""
    # Main processing logic
    if continue_workflow:
        # Continue through remaining workflow steps
        return run_subsequent_workflow_steps(stills_id, record_id, token)

if __name__ == "__main__":
    if len(sys.argv) == 2:
        # Direct API call mode - continue workflow
        token = config.get_token()
        continue_workflow = True
    elif len(sys.argv) == 3:
        # Subprocess mode - step only
        token = sys.argv[2] 
        continue_workflow = False
```

### 3. URL-Aware Metadata Evaluation

```python
def evaluate_metadata_quality(record_data, token, has_url=False):
    """Evaluate metadata quality with URL-aware thresholds."""
    try:
        # Combine all metadata sources
        combined_metadata = combine_metadata(record_data)
        
        url_context = "with URL available" if has_url else "without URL"
        print(f"  -> Evaluating combined metadata ({len(combined_metadata)} chars) {url_context}")
        
        # Use local evaluator with URL awareness
        evaluation = evaluate_metadata_local(combined_metadata, has_url)
        
        is_sufficient = evaluation.get("sufficient", False)
        reason = evaluation.get("reason", "No reason provided")
        score = evaluation.get("score", 0.0)
        
        print(f"  -> Local AI Evaluation: {'GOOD' if is_sufficient else 'BAD'}")
        print(f"     Score: {score:.2f}")
        print(f"     Reason: {reason}")
        
        return is_sufficient
        
    except Exception as e:
        # URL-aware fallback thresholds
        fallback_threshold = 100 if has_url else 50
        combined_metadata = combine_metadata(record_data)
        return len(combined_metadata) > fallback_threshold
```

### 4. Enhanced Error Handling with Retry Logic

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

### 5. Logging Standards with Enhanced Context

```python
# Emoji-based logging for visual clarity with context
logging.info(f"🚀 Starting operation: {operation_name}")
logging.info(f"📋 Processing item: {item_id}")
logging.info(f"🔍 URL found for {item_id}: {url}")
logging.info(f"⚖️ Will use STRICTER metadata evaluation (can improve via scraping)")
logging.info(f"✅ Success: {operation_description}")
logging.error(f"❌ Error: {error_description}")
logging.warning(f"⚠️ Warning: {warning_description}")
```

## 🚀 Development Workflow

### Adding New Job Scripts

1. Create script in `/jobs/` following naming convention: `{workflow}_{step}_description.py`
2. Define `__ARGS__` and `FIELD_MAPPING` at the top
3. Implement main function with proper error handling and logging
4. Add conditional logic and URL-awareness if applicable
5. Test with both single items and batch processing
6. Add to API.py's job discovery system

### Modern API Development

1. Use FastAPI with proper startup/shutdown events
2. Implement background tasks with comprehensive job tracking
3. Add detailed logging with emoji indicators and contextual information
4. Include health check and status endpoints
5. Follow resilient error handling patterns with URL-aware logic

### Converting Legacy Scripts

Legacy scripts should be modernized with:

1. **Individual job scripts** for each processing stage
2. **API integration** instead of standalone controllers
3. **Enhanced error handling** with retry logic
4. **Batch processing support** for improved performance
5. **Automatic item discovery** instead of manual specification
6. **Conditional logic** for intelligent resource allocation

## 🔐 Environment Variables

Required environment variables:

```bash
FILEMAKER_SERVER=10.0.222.144
FILEMAKER_USERNAME=Background  
FILEMAKER_PASSWORD=july1776
OPENAI_API_KEY=sk-proj-...
FM_AUTOMATION_KEY=supersecret  # API authentication
AUTOLOG_DEBUG=false           # Enable debug mode for real-time output
```

## 📊 FileMaker Integration

### Field Naming Conventions

- `AutoLog_Status` - Workflow status tracking
- `AI_DevConsole` - User-friendly error messages  
- `INFO_*` - Metadata fields (e.g., INFO_Metadata, INFO_Description)
- `SPECS_*` - Technical specification fields (e.g., SPECS_URL, SPECS_Filepath_Server)
- `AI_*` - AI-generated content fields (e.g., AI_Prompt)
- `INFO_Reviewed_Checkbox` - Controls conditional tag application

### Status Management with Intelligent Progression

```python
# Enhanced status progression with conditional logic
WORKFLOW_STEPS = [
    {
        "step_num": 1,
        "status_before": "0 - Pending File Info",
        "status_after": "1 - File Info Complete",
        "script": "stills_autolog_01_get_file_info.py",
        "description": "Get File Info"
    },
    {
        "step_num": 4,
        "status_before": "3 - Metadata Parsed",
        "status_after": "4 - Scraping URL",
        "script": "stills_autolog_04_scrape_url.py",
        "description": "Scrape URL",
        "conditional": True,  # Only run if metadata is insufficient
        "evaluate_metadata_first": True  # URL-aware evaluation
    },
    {
        "step_num": 7,
        "status_before": "6 - Generating Embeddings",
        "status_after": "7 - Applying Tags",
        "script": "stills_autolog_07_apply_tags.py",
        "description": "Apply Tags",
        "conditional": True,  # Only run if INFO_Reviewed_Checkbox != 0
        "check_reviewed_flag": True  # Checkbox-aware execution
    }
    # ... more steps
]
```

### Multi-ID Input Parsing and Validation

The system includes a standardized input parser that supports multiple ID formats:

```python
from utils.input_parser import parse_input_ids, validate_ids, format_input_summary

# Parse various input formats
input_string = "S04871,S04872,S04873"  # Comma-separated
ids = parse_input_ids(input_string)  # ['S04871', 'S04872', 'S04873']

# Validate IDs against expected prefixes
valid_ids, invalid_ids = validate_ids(ids, ['S', 'F', 'AF'])

# Format summary for logging
summary = format_input_summary(valid_ids, "script_name")
```

**Supported Input Formats:**
- **Single ID**: `"S04871"`
- **JSON Array**: `'["S04871", "S04872", "S04873"]'`
- **Comma-separated**: `"S04871,S04872,S04873"`
- **Line-separated**: `"S04871\nS04872\nS04873"`
- **Space-separated**: `"S04871 S04872 S04873"`

### Automatic Pending Item Query with Enhanced Batching

```python
def find_pending_items(token):
    """Find all items with '0 - Pending File Info' status."""
    query = {
        "query": [{FIELD_MAPPING["status"]: "0 - Pending File Info"}],
        "limit": 100  # Reasonable batch size for optimal performance
    }
    
    response = requests.post(
        config.url("layouts/Stills/records/_find"),
        headers=config.api_headers(token),
        json=query,
        verify=False
    )
    
    if response.status_code == 404:
        print("📋 No pending items found")
        return []
    
    # Extract and return stills_ids with validation
    return stills_ids
```

## 🧪 Testing & Debugging

### Debug Mode Support
```bash
# Enable debug mode for real-time output
export AUTOLOG_DEBUG=true
```

### Enhanced Monitoring Features
- Real-time job tracking via `/status` endpoint
- Detailed console logging with emoji indicators and context
- Individual item progress tracking in batch operations
- URL-aware evaluation logging with threshold explanations
- Conditional logic decision logging
- Graceful error reporting with FileMaker integration

### Testing URL-Aware Thresholds
```python
# Test the evaluation system
from utils.local_metadata_evaluator import evaluate_metadata_local

# Test metadata with different URL scenarios
test_metadata = "Historical photograph from 1920s"

# Without URL (lenient threshold = 0.3)
result_no_url = evaluate_metadata_local(test_metadata, has_url=False)

# With URL (stricter threshold = 0.5)  
result_with_url = evaluate_metadata_local(test_metadata, has_url=True)
```

## 📈 Performance & Scalability

### Enhanced Concurrency Management
- **API-level**: FastAPI BackgroundTasks for job submission
- **Job-level**: ThreadPoolExecutor with dynamic limits based on batch size
- **Batch-level**: Automatic discovery and intelligent parallel processing
- **Resource-aware**: URL-aware evaluation reduces unnecessary processing

### Optimized Resource Allocation
```python
# Dynamic worker allocation based on batch size
if len(items) > 50:
    workers = 12  # Large batch optimization
elif len(items) > 20:
    workers = 14  # Medium batch optimization  
else:
    workers = min(16, len(items))  # Small batch optimization
```

### Intelligent Processing Decisions
- **URL-aware thresholds** - Avoid scraping when URLs don't exist
- **Metadata quality evaluation** - Skip unnecessary processing when quality is sufficient
- **Conditional tag application** - Respect user preferences for AI tagging
- **Workflow continuation** - Step 05 can complete entire workflow when called individually

## 🔄 System Resilience

### Automatic Recovery Features
- **Token refresh** - Handles FileMaker authentication expiration
- **Retry mechanisms** - Exponential backoff for network issues
- **Graceful degradation** - Continues processing on partial failures
- **Resilient workflows** - Individual item failures don't stop batch processing
- **URL-aware fallbacks** - Basic length checks when evaluation fails
- **Intelligent skipping** - Proceeds with workflow when improvements aren't possible

### Health Monitoring with Enhanced Metrics
```python
# Enhanced system health indicators
{
    "jobs_submitted": 45,
    "jobs_completed": 42,
    "currently_running": 3,
    "running_jobs": ["stills_autolog_00_run_all()", "..."],
    "metadata_evaluations": {
        "total": 156,
        "url_available": 89,
        "no_url": 67,
        "scraping_triggered": 23,
        "scraping_skipped": 133
    }
}
```

## 🔧 Configuration & Timeout Management

### Dynamic Timeout Management

The system now includes intelligent timeout management based on video characteristics:

- **Video Length Detection** - Automatically estimates processing time based on video duration
- **Frame Count Awareness** - Considers frame count for accurate timeout estimation
- **Processing Overhead** - Includes AI processing and file operation overhead
- **Reasonable Limits** - Minimum 10 minutes, maximum 2 hours for most operations
- **Step-Specific Timeouts** - Different timeouts for different processing steps

**Timeout Calculation Formula:**
```
Base Timeout = 5 minutes (300s)
Video Factor = 2 × video duration in seconds
Processing Overhead = 5 minutes (300s)
Final Timeout = Base + Video Factor + Overhead
Capped between 10 minutes and 2 hours
```

### Retry Logic and Recovery

**Automatic Retry Features:**
- **Exponential Backoff** - Retry delays increase with each attempt (1s, 2s, 4s)
- **Maximum 3 Retries** - Prevents infinite retry loops
- **Progress Tracking** - Monitors job progress to detect truly stuck jobs
- **Stuck Detection** - Identifies jobs with no progress for 3+ minutes
- **Graceful Degradation** - Continues processing other items if individual items fail

**Recovery Mechanisms:**
- **Status Reset** - Reset stuck items to appropriate processing states
- **Frame Status Reset** - Reset child frame statuses when parent footage is reset
- **Manual Retry** - Individual item retry through API or monitor utility
- **Bulk Recovery** - Reset multiple stuck items simultaneously

### Environment Variables

```bash
# API Configuration
FM_AUTOMATION_KEY=supersecret  # API authentication key
AUTOLOG_DEBUG=false            # Enable debug mode for real-time output

# FileMaker Configuration (in config.py)
FM_SERVER=your_filemaker_server
FM_DATABASE=your_database_name
FM_USERNAME=your_username
FM_PASSWORD=your_password
```

## 📋 Next Steps

1. **Convert Footage Workflow**
   - Break down `AutoLog_Footage.py` into individual job scripts
   - Integrate with modern API architecture
   - Add automatic pending item discovery
   - Implement intelligent conditional logic

2. **Convert Marker Generation**
   - Modularize `Generate_Markers.py` functionality
   - Add to API endpoint system
   - Integrate with footage workflow
   - Add URL-aware evaluation for video metadata

3. **Enhanced Monitoring Dashboard**
   - Add web dashboard for job monitoring
   - Implement alerting for system issues
   - Add performance metrics collection
   - URL-aware evaluation statistics

4. **Advanced Image Processing**
   - Expand upscaling options with different AI models
   - Add batch image enhancement capabilities
   - Integrate with main workflow for automatic enhancement
   - Add quality assessment metrics

5. **Documentation & Testing**
   - Document new field mappings and conditional workflows
   - Create comprehensive test suite for URL-aware logic
   - Update deployment procedures
   - Add integration tests for workflow continuation 