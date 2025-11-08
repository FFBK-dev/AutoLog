# LF AutoLog Job Queue System (Redis + Python RQ)

## Overview

The LF AutoLog workflow now uses a **proper job queue system** instead of polling, built on **Redis** and **Python RQ**. This eliminates race conditions, provides better monitoring, and enables true parallel processing with automatic job dependencies.

## Architecture

### Before (Polling):
```
6 independent pollers → FileMaker (every 10-30s) → Find records → Process → Update status
```

**Problems:**
- Race conditions (status updated before work completed)
- No job dependencies (steps couldn't wait for each other)
- Constant FileMaker queries (even when idle)
- No monitoring/visibility
- Manual process management

### After (Job Queue):
```
API Endpoint → Queue Job → Redis → Workers → Process → Update Status → Queue Next Job
```

**Benefits:**
- ✅ **No race conditions** (by design)
- ✅ **Job dependencies** (Step 2 only runs after Step 1 completes)
- ✅ **No polling overhead** (event-driven)
- ✅ **Web dashboard** for monitoring
- ✅ **Built-in retry logic**
- ✅ **Scalable workers** per step
- ✅ **Failed job visibility** with tracebacks

## Installation

### 1. Redis Setup

Redis is installed and running:
```bash
brew install redis
brew services start redis
```

Verify:
```bash
redis-cli ping  # Should return PONG
```

### 2. Python Dependencies

Already installed:
```
redis>=4.5.0
rq>=1.15.0
rq-dashboard>=0.6.1
```

## Usage

### Starting the System

**1. Start Workers** (31 workers across 6 steps):
```bash
./workers/start_lf_workers.sh start
```

Or via API:
```bash
curl -X POST http://localhost:8081/workers/start -H "X-API-Key: YOUR_KEY"
```

**Worker Distribution:**
- Step 1 (File Info): 8 workers
- Step 2 (Thumbnails): 8 workers
- Step 3 (Assess & Sample): 6 workers
- Step 4 (Gemini Analysis): 2 workers (rate limited)
- Step 5 (Create Frames): 4 workers
- Step 6 (Audio Transcription): 3 workers

**2. Queue Items for Processing**

**Single Item:**
```bash
curl -X POST "http://localhost:8081/run/lf_queue?footage_id=LF1409" \
  -H "X-API-Key: YOUR_KEY"
```

**Batch:**
```bash
curl -X POST http://localhost:8081/run/lf_queue_batch \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"footage_ids": ["LF1409", "LF1410", "LF1411"]}'
```

**Force Resume (reprocess from Step 3):**
```bash
curl -X POST http://localhost:8081/run/lf_force_resume_all \
  -H "X-API-Key: YOUR_KEY"
```

**3. Optional: Auto-Discovery**

Start a poller that automatically finds new imports:
```bash
curl -X POST http://localhost:8081/run/lf_discovery \
  -H "X-API-Key: YOUR_KEY"
```

This polls FileMaker every 30s for records at "0 - Pending File Info" and queues them automatically.

### Monitoring

**Check Queue Status:**
```bash
curl http://localhost:8081/queue/status -H "X-API-Key: YOUR_KEY"
```

Returns:
```json
{
  "queues": {
    "step1_file_info": {"queued": 5, "failed": 0},
    "step2_thumbnails": {"queued": 3, "failed": 0},
    ...
  },
  "total_queued": 15,
  "total_failed": 0
}
```

**Check Worker Status:**
```bash
curl http://localhost:8081/workers/status -H "X-API-Key: YOUR_KEY"
```

**Web Dashboard:**
```bash
rq-dashboard --redis-host localhost --redis-port 6379
```

Then open: `http://localhost:9181`

Shows:
- Queued jobs per step
- Active workers
- Failed jobs with full tracebacks
- Job durations and performance

### Stopping

**Stop Workers:**
```bash
./workers/start_lf_workers.sh stop
```

Or via API:
```bash
curl -X POST http://localhost:8081/workers/stop -H "X-API-Key: YOUR_KEY"
```

**Stop Discovery Poller:**
```bash
curl -X POST http://localhost:8081/stop/lf_discovery -H "X-API-Key: YOUR_KEY"
```

## Workflow Steps

Each step is a separate job that runs when conditions are met:

### Step 1: Get File Info
- **Status:** `0 - Pending File Info` → `1 - File Info Complete`
- **Script:** `lf_autolog_01_get_file_info.py`
- **On Success:** Queue Step 2

### Step 2: Generate Thumbnails
- **Status:** `1 - File Info Complete` → `2 - Thumbnails Complete`
- **Script:** `lf_autolog_02_generate_thumbnails.py`
- **On Success:** Queue Step 3

### Step 3: Assess & Sample Frames
- **Status:** `2 - Thumbnails Complete` → `Awaiting User Input` (normal) OR `3 - Creating Frames` (Force Resume)
- **Script:** `lf_autolog_03_assess_and_sample.py`
- **On Success:**
  - Normal: Halt at "Awaiting User Input" (wait for user prompt)
  - Force Resume: Queue Step 4

### Step 4: Gemini Multi-Image Analysis
- **Status:** `3 - Creating Frames` → `5 - Processing Frame Info`
- **Script:** `lf_autolog_04_gemini_analysis.py`
- **On Success:** Queue Step 5

### Step 5: Create Frame Records
- **Status:** `5 - Processing Frame Info` → `7 - Avid Description` (no audio) OR `6 - Generating Description` (has audio)
- **Script:** `lf_autolog_05_create_frames.py`
- **On Success:**
  - Has audio: Queue Step 6
  - No audio: Complete at "7 - Avid Description"

### Step 6: Map Audio Transcription
- **Status:** `6 - Generating Description` → `7 - Avid Description`
- **Script:** `lf_autolog_06_transcribe_audio.py`
- **On Success:** Complete

## API Endpoints

### Job Queueing

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/run/lf_queue` | POST | Queue a single LF item |
| `/run/lf_queue_batch` | POST | Queue multiple LF items |
| `/run/lf_force_resume_all` | POST | Find and queue all Force Resume items |

### Monitoring

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/queue/status` | GET | Get queue depths and failed counts |
| `/workers/status` | GET | Get worker counts per step |

### Control

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/workers/start` | POST | Start all 31 workers |
| `/workers/stop` | POST | Stop all workers |
| `/run/lf_discovery` | POST | Start auto-discovery poller |
| `/stop/lf_discovery` | POST | Stop auto-discovery poller |

## How It Works

### Job Dependencies

Each job **only** queues the next step after successfully completing its work:

```python
def job_step1_file_info(footage_id, token):
    # 1. Run script
    success = run_script("lf_autolog_01_get_file_info.py", footage_id, token)
    
    if success:
        # 2. Update status ONLY after work completes
        if update_status(footage_id, token, "1 - File Info Complete"):
            # 3. Queue next step ONLY if status updated
            q_step2.enqueue(job_step2_thumbnail, footage_id, token)
```

This prevents race conditions where records move to the next status before work is done.

### Worker Pools

Each step has dedicated workers:
- **Fast steps** (1-2): 8 workers each for parallel imports
- **Medium steps** (3, 5): 4-6 workers for frame processing
- **Slow steps** (4): 2 workers (rate limited by Gemini API)
- **Optional steps** (6): 3 workers for audio transcription

Workers process jobs from their queue as soon as they're available.

### Failure Handling

If a job fails:
1. Record stays at current status (not advanced)
2. Job goes to failed registry
3. Can be retried manually or automatically
4. Full traceback available in RQ Dashboard

## Troubleshooting

### Redis Not Running
```bash
brew services start redis
redis-cli ping  # Should return PONG
```

### Workers Not Starting
Check logs:
```bash
tail -f /tmp/lf_worker_step*.log
```

### Jobs Stuck in Queue
Check worker status:
```bash
./workers/start_lf_workers.sh status
```

If no workers are running:
```bash
./workers/start_lf_workers.sh start
```

### High Queue Depth
Check RQ Dashboard for failed jobs or slow workers:
```bash
rq-dashboard
```

Open: `http://localhost:9181`

### Clear Failed Jobs
```bash
rq worker --burst lf_step1 --failed-queue
```

Or use RQ Dashboard to retry/delete failed jobs.

## Migration from Pollers

The old polling system has been archived:
- `jobs/lf_autolog_poller_step*.py` → `jobs/archive/`

Old poller endpoints still exist but are deprecated:
- `/run/lf_pollers_all` (deprecated)
- `/stop/lf_pollers_all` (deprecated)

**Recommended:** Use the new queue system for all new work.

## Performance Characteristics

### Throughput
- **Steps 1-2:** ~50 items in 5-10 minutes (parallel)
- **Step 3:** ~20 items in 5-10 minutes (scene detection)
- **Step 4:** ~2-3 items per minute (Gemini rate limit)
- **Steps 5-6:** ~10-15 items per minute

### Scalability
- Can queue 100+ items without issues
- Workers process in parallel across all steps
- No blocking between steps
- Automatic load balancing

### Resource Usage
- **Redis:** <50 MB RAM
- **Workers:** ~100-200 MB per worker
- **Total:** ~3-4 GB RAM for 31 workers

## Advanced Usage

### Custom Worker Counts

Edit `workers/start_lf_workers.sh` and adjust the loop counts:

```bash
# Increase Step 1 workers to 16
for i in {1..16}; do
    nohup rq worker lf_step1 --path "$PROJECT_ROOT" > /tmp/lf_worker_step1_$i.log 2>&1 &
done
```

### Queue Priority

Items are processed FIFO (first in, first out) within each queue.

### Job Timeouts

Configured per queue in `jobs/lf_queue_jobs.py`:
- Steps 1-2: 10 minutes
- Steps 3-4: 30 minutes
- Step 5: 20 minutes
- Step 6: 10 minutes

### Retry Logic

Failed jobs don't auto-retry by default. Use RQ Dashboard to manually retry or implement custom retry logic.

## Files

| File | Purpose |
|------|---------|
| `jobs/lf_queue_jobs.py` | Job definitions and queue setup |
| `workers/start_lf_workers.sh` | Worker management script |
| `jobs/lf_queue_discovery.py` | Optional auto-discovery poller |
| `API.py` | Queue-based endpoints |

## See Also

- [LF Gemini Experiment Documentation](LF_GEMINI_EXPERIMENT.md)
- [Python RQ Documentation](https://python-rq.org/)
- [Redis Documentation](https://redis.io/docs/)

