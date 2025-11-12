# Unified API Monitoring Dashboard Guide

## Overview

The Unified API Monitoring Dashboard is a real-time web interface for monitoring **all** FileMaker automation activity across the entire system. It provides a comprehensive view of API jobs and Redis queue processing for all workflows (Stills, Footage, Music, Metadata, and more).

## Quick Start

### 1. Start the API Server

The API must be running for the dashboard to work:

```bash
python3 API.py
```

The API runs on **port 8081**.

### 2. Start the Dashboard

```bash
python3 dashboard/ftg_dashboard.py
```

### 3. Access in Browser

Open: **http://localhost:9181**

The dashboard will auto-refresh every 5 seconds.

## What You'll See

### Connection Status

At the top, you'll see an **API Connection** indicator:
- **Green "API Connected"**: Dashboard is receiving data from API
- **Red "API Disconnected"**: Cannot reach API server (check that API is running on port 8081)

### Statistics Bar

Real-time metrics across all workflows:
- **Total Jobs**: Total number of jobs submitted since API startup
- **API Running**: Jobs currently being processed by the API
- **Redis Queued**: Items waiting in Redis queues (Footage Part B)
- **Redis Processing**: Items currently being processed by Redis workers
- **Completed**: Total completed jobs
- **Failed**: Total failed jobs (may need attention)

### Jobs Table

Clean, unified table showing all activity with the following columns:

#### 1. FileMaker ID
The record identifier from FileMaker (e.g., `S12345`, `LF1554`, `FTG001`, `MX042`)
- Bold, monospace font for easy scanning
- Shows `-` if no ID available

#### 2. Media Type
Color-coded badge indicating the asset type:
- **Blue**: Stills
- **Red**: Footage
- **Green**: Music
- **Purple**: Metadata
- **Orange**: Avid Integration
- **Teal**: System Jobs
- **Gray**: Other

#### 3. Job Name
The specific job or workflow being executed (e.g., `stills_autolog_00_run_all`)
- Truncated with tooltip showing full name on hover
- Includes Redis queue step names (e.g., "Footage Part B - Step2 Gemini")

#### 4. Status
Current state of the job:
- **Black (pulsing)**: Running - actively processing
- **Green**: Completed - finished successfully
- **Red**: Failed - encountered an error
- **Gray**: Queued - waiting in Redis queue

#### 5. Duration
How long the job has been running or took to complete:
- Format: `45s` for seconds, `3m 12s` for minutes
- Shows `-` for queued items or if timing unavailable

## Filtering & Search

### Search Box
Type to filter by:
- FileMaker ID (e.g., search "S12345" to find specific stills)
- Job name (e.g., search "gemini" to find AI analysis jobs)

### Media Type Filters
Click to show only specific asset types:
- **All**: Show everything (default)
- **Stills**: Only stills autolog and processing
- **Footage**: Only footage workflows (Live, Archival, Part A, Part B)
- **Music**: Only music autolog
- **Metadata**: Only metadata bridge operations
- **Avid**: Only Avid integration jobs (search, similar, etc.)
- **Other**: Jobs that don't fit other categories

### Status Filters
Click to show only specific job states:
- **All**: Show everything (default)
- **Running**: Only actively processing jobs
- **Queued**: Only items waiting in Redis queues
- **Completed**: Only finished jobs
- **Failed**: Only jobs that encountered errors

**Tip**: Filters combine! Search for "LF" and select "Running" to see only Live Footage jobs currently processing.

## Understanding the Data

### API Jobs vs. Redis Queues

The dashboard shows two types of activity:

**API Jobs** (Direct execution):
- Submitted via API endpoints (e.g., `/run/stills_autolog_00_run_all`)
- Processed directly by the API server
- Examples: Stills AutoLog, Footage Part A, Music AutoLog, Metadata queries

**Redis Queued Jobs** (Queue-based execution):
- Submitted to Redis queues for parallel processing
- Currently used for: Footage AutoLog Part B (AI processing)
- Processed by dedicated RQ workers
- Items show as "Queued" until a worker picks them up

### Job Lifecycle

1. **Submitted** → Job sent to API or Redis queue
2. **Running** → Actively being processed
3. **Completed** or **Failed** → Finished (success or error)

Redis queued items follow: **Queued** → **Running** → **Completed/Failed**

### Display Priority

Jobs are ordered by importance:
1. **Running API jobs** (most urgent)
2. **Running Redis jobs** (actively processing)
3. **Queued Redis jobs** (waiting for workers)
4. **Recent completed/failed** (last 50 shown)

## Workflow Examples

### Stills AutoLog
- **Media Type**: Stills (Blue)
- **FileMaker ID**: S12345
- **Typical Jobs**: `stills_autolog_00_run_all`

### Footage AutoLog Part A (Import)
- **Media Type**: Footage (Red)
- **FileMaker ID**: LF1554 or AF0234 or FTG001
- **Typical Jobs**: `ftg_autolog_A_00_run_all`

### Footage AutoLog Part B (AI Processing)
- **Media Type**: Footage (Red)
- **FileMaker ID**: LF1554 or AF0234 or FTG001
- **Shows in Redis Queues**:
  - Step 1: Assess & Sample Frames
  - Step 2: Gemini AI Analysis
  - Step 3: Create Frame Records
  - Step 4: Audio Transcription
- **Workers**: 20 parallel workers process these queues

### Music AutoLog
- **Media Type**: Music (Green)
- **FileMaker ID**: MX042
- **Typical Jobs**: `music_autolog_00_run_all`

### Metadata Bridge
- **Media Type**: Metadata (Purple)
- **Typical Jobs**: `metadata-query`, `metadata-export`
- **Purpose**: Sync between FileMaker and Avid Media Composer

## Troubleshooting

### Dashboard Won't Start

**Error: Cannot connect to API**
- Check that API.py is running: `python3 API.py`
- Verify API is on port 8081
- Test: `curl http://localhost:8081/health`

**Error: Flask not found**
```bash
pip3 install flask
```

**Error: Redis connection refused**
- Only affects Footage Part B queue display
- API jobs will still show
- Start Redis: `redis-server`

### No Jobs Showing

**If API is connected but table is empty:**
- System is idle (no jobs currently running or recently completed)
- Trigger a test job to verify dashboard is working
- Check that auto-refresh is working (footer shows "Last updated" time)

### Jobs Not Updating

**Check auto-refresh:**
- Footer should show "⟳ Auto-refreshing every 5 seconds"
- Timestamp should update every 5 seconds
- If frozen, refresh browser manually

### Failed Jobs

**Red "Failed" badges indicate:**
1. Check API logs (`api.log`) for error details
2. Look at FileMaker `AI_DevConsole` field for user-facing errors
3. Common issues:
   - File not found (check volume mounts)
   - Token expired (API handles automatically)
   - OpenAI rate limits (uses multiple keys with rotation)
   - Network timeouts

## Architecture

### Data Flow

```
FileMaker Record → API Endpoint → Job Tracker → Dashboard
                                      ↓
                                Redis Queue → Workers → Dashboard
```

### Behind the Scenes

**Dashboard** (`dashboard/ftg_dashboard.py`):
- Flask web app on port 9181
- Fetches data from `/dashboard/data` endpoint every 5 seconds
- Client-side filtering via JavaScript

**API Endpoint** (`/dashboard/data` in `API.py`):
- Aggregates JobTracker data (all API jobs)
- Queries Redis queues (Footage Part B)
- Extracts FileMaker IDs and categorizes by media type
- Returns JSON for dashboard consumption

**JobTracker** (in `API.py`):
- Tracks every job submitted via API
- Stores: job name, arguments, timestamps, status
- Thread-safe for concurrent access

**Redis Queues** (Footage Part B only):
- 4 queues: step1, step2, step3, step4
- 20 workers processing in parallel
- Independent of main API processing

## Performance Notes

### Scalability
- Dashboard shows last 100 API jobs (most recent)
- Shows up to 20 queued items per Redis queue
- Minimal performance impact on API server
- Safe to leave running continuously

### Network Usage
- Auto-refresh: ~5-10KB per request
- No impact on workflow processing
- Can be accessed by multiple users simultaneously

## Port Reference

- **API Server**: 8081
- **Dashboard**: 9181
- **Redis**: 6379 (internal)

Make sure these ports are available before starting services.

## Tips & Best Practices

1. **Monitor failures**: Check red "Failed" badges regularly
2. **Use filters**: Combine search + media type + status for focused monitoring
3. **Watch queue depths**: High Redis queued counts indicate backlog
4. **Check worker status**: If queued items aren't processing, workers may be stopped
5. **Keep it open**: Dashboard is lightweight and designed for continuous monitoring
6. **Multiple users**: Safe to access from multiple browsers/devices on the network

## Related Files

- **Dashboard**: `dashboard/ftg_dashboard.py`
- **API Server**: `API.py`
- **Data Endpoint**: `API.py` → `@app.get("/dashboard/data")`
- **Job Tracker**: `API.py` → `class JobTracker`
- **Redis Queues**: `jobs/ftg_autolog_B_queue_jobs.py`

## Advanced Usage

### Custom Monitoring

The `/dashboard/data` endpoint returns JSON that can be consumed by other tools:

```bash
curl http://localhost:8081/dashboard/data | jq
```

### Programmatic Access

Build custom monitoring tools using the dashboard endpoint:
- Check queue depths
- Alert on failures
- Track processing times
- Monitor system health

### Integration

The dashboard data is designed to be integration-friendly:
- Clean JSON format
- Stable schema
- Consistent media type categorization
- FileMaker ID extraction

## Support

For issues or questions:
1. Check API logs: `api.log`
2. Review FileMaker `AI_DevConsole` fields
3. Verify network connectivity
4. Ensure all dependencies installed: `pip3 install -r requirements.txt`

