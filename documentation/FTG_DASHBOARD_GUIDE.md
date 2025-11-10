# Footage AutoLog Part B Dashboard Guide

## Overview

The Footage AutoLog Part B Dashboard is a real-time web interface for monitoring the AI processing workflow. It shows exactly which footage items are queued in each step and provides live statistics on queue status.

## Quick Start

### 1. Start the Dashboard

```bash
python3 dashboard/ftg_dashboard.py
```

### 2. Access in Browser

Open: **http://localhost:9181**

The dashboard will auto-refresh every 5 seconds.

## What You'll See

### Statistics Panel
- **Total Queued**: Total number of items across all 4 queues
- **Total Failed**: Items that failed processing (can be retried)
- **Active Workers**: Number of Redis workers processing jobs (20)

### Step Panels

#### Step 1: Assess & Sample Frames
- Queue: `ftg_ai_step1`
- Timeout: 30 minutes
- Purpose: Intelligent scene detection and frame sampling
- **False Start Protection**: Automatically blocks videos < 5 seconds

#### Step 2: Gemini AI Analysis
- Queue: `ftg_ai_step2`
- Timeout: 30 minutes
- Purpose: Multi-image analysis via Google Gemini API

#### Step 3: Create Frame Records
- Queue: `ftg_ai_step3`
- Timeout: 20 minutes
- Purpose: Create FileMaker frame records from AI data

#### Step 4: Audio Transcription
- Queue: `ftg_ai_step4`
- Timeout: 10 minutes
- Purpose: Map audio transcriptions to frame records (background)

## Status Indicators

- **Blue pill with pulse animation**: Items currently queued
- **Red pill**: Failed items (check logs)
- **Gray "Idle" pill**: No items in queue

## Footage IDs

The dashboard shows FileMaker footage IDs (e.g., "FTG1234") for each item in the queue. Up to 10 items are displayed per queue.

## Behind the Scenes

The dashboard connects to the Redis queues defined in:
- `jobs/ftg_autolog_B_queue_jobs.py`

It displays real-time status without affecting the processing workers.

## Troubleshooting

### Dashboard Won't Start

**Error: Connection refused to Redis**
```bash
# Start Redis server
redis-server
```

**Error: Flask not found**
```bash
# Install Flask
pip3 install flask
```

### No Items Showing

**Check if workers are running:**
```bash
# Workers should be started with:
# rq worker ftg_ai_step1 ftg_ai_step2 ftg_ai_step3 ftg_ai_step4 --burst
```

**Check API queue status:**
```bash
curl -H "X-API-Key: YOUR_KEY" http://localhost:8080/queue/ftg_autolog_B_status
```

### Items Stuck in Queue

1. Check worker logs for errors
2. Check Redis queue status: `redis-cli`
3. Review FileMaker status field for the stuck footage ID
4. Check job failures in Redis: Failed Job Registry

## Architecture

```
FileMaker Record (Status: "3 - Ready for AI")
    ↓
API Endpoint: /run/ftg_autolog_B_00_run_all
    ↓
Queue Step 1 (ftg_ai_step1) → Dashboard shows here
    ↓
Queue Step 2 (ftg_ai_step2) → Dashboard shows here
    ↓
Queue Step 3 (ftg_ai_step3) → Dashboard shows here
    ↓
Queue Step 4 (ftg_ai_step4) → Dashboard shows here (if audio)
    ↓
Final Status: "7 - Avid Description"
```

## Related Files

- **Dashboard**: `dashboard/ftg_dashboard.py`
- **Queue Definitions**: `jobs/ftg_autolog_B_queue_jobs.py`
- **API Endpoints**: `API.py` (lines 1493-1668)
- **Workflow Documentation**: `documentation/FTG_TWO_WORKFLOW_IMPLEMENTATION.md`

## Tips

1. **Keep it running**: The dashboard is lightweight and can run continuously
2. **Monitor failures**: Red "failed" badges indicate items needing attention
3. **Worker count**: 20 workers means up to 20 items processing simultaneously
4. **Background transcription**: Step 4 runs after workflow completion (status already at "7")

## Port Information

- Dashboard runs on: **9181**
- API runs on: **8080**
- Redis runs on: **6379**

Make sure these ports are available before starting services.

