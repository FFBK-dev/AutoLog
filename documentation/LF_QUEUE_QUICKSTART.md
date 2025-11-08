# LF AutoLog Queue System - Quick Start Guide

## 🚀 Get Started in 3 Steps

### 1. Start Workers (One Time)

```bash
cd /Users/admin/Documents/Github/Filemaker-Backend
./workers/start_lf_workers.sh start
```

This starts **31 workers** across all 6 steps. You only need to do this once - workers keep running in the background.

**Verify workers are running:**
```bash
./workers/start_lf_workers.sh status
```

### 2. Queue Items

**From FileMaker (Recommended):**

Your existing import script already works! Just make sure the API is running:
```bash
# Check API status
curl http://localhost:8081/status -H "X-API-Key: YOUR_KEY"
```

**From Terminal (Testing):**
```bash
# Single item
curl -X POST "http://localhost:8081/run/lf_queue?footage_id=LF1409" \
  -H "X-API-Key: YOUR_KEY"

# Batch
curl -X POST http://localhost:8081/run/lf_queue_batch \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '["LF1409", "LF1410", "LF1411"]'
```

### 3. Monitor Progress

**Check queue status:**
```bash
curl http://localhost:8081/queue/status -H "X-API-Key: YOUR_KEY"
```

**Or use the web dashboard:**
```bash
rq-dashboard
```
Then open: http://localhost:9181

## 📊 What You'll See

### In FileMaker
Items move through statuses automatically:
1. `0 - Pending File Info` → `1 - File Info Complete`
2. `1 - File Info Complete` → `2 - Thumbnails Complete`
3. `2 - Thumbnails Complete` → `Awaiting User Input` (add prompt)
4. **After adding prompt:** Set to `Force Resume`
5. `Force Resume` → `3 - Creating Frames` → `5 - Processing Frame Info`
6. `5 - Processing Frame Info` → `7 - Avid Description`

### In Web Dashboard (http://localhost:9181)
- See queued jobs per step
- Watch workers processing items
- View failed jobs with error details
- Monitor processing times

## 🔧 Common Tasks

### Stop Old Pollers (If Running)
```bash
curl -X POST http://localhost:8081/stop/lf_pollers_all -H "X-API-Key: YOUR_KEY"
```

### Restart Workers
```bash
./workers/start_lf_workers.sh restart
```

### Force Resume All
```bash
curl -X POST http://localhost:8081/run/lf_force_resume_all \
  -H "X-API-Key: YOUR_KEY"
```

### Auto-Discovery (Optional)
Start a poller that automatically queues new imports:
```bash
curl -X POST http://localhost:8081/run/lf_discovery \
  -H "X-API-Key: YOUR_KEY"
```

## ❓ Troubleshooting

### "No workers running"
```bash
./workers/start_lf_workers.sh start
```

### "Redis connection error"
```bash
brew services start redis
redis-cli ping  # Should return PONG
```

### "Items stuck in queue"
Check RQ Dashboard for errors: http://localhost:9181

### Check worker logs
```bash
tail -f /tmp/lf_worker_step*.log
```

## 📈 Performance

- **Steps 1-2:** 8 workers each (fast - thumbnails in 30-60s)
- **Step 3:** 6 workers (medium - scene detection)
- **Step 4:** 2 workers (slow - Gemini rate limited)
- **Steps 5-6:** 3-4 workers each (medium)

**Expected throughput:**
- Import 10 items → Steps 1-2 done in ~2 minutes
- Gemini analysis → ~30s per item (2 parallel)
- Total end-to-end → ~5-10 minutes per item

## 🎯 Key Benefits vs Old Pollers

✅ **No race conditions** - Status only updates after work completes
✅ **True parallel processing** - All steps run independently
✅ **Better monitoring** - Web dashboard with job details
✅ **Automatic dependencies** - Step 2 waits for Step 1 to complete
✅ **Failed job visibility** - See what failed and why
✅ **Scalable** - Queue 100+ items without issues

## 📚 Full Documentation

See [LF_QUEUE_SYSTEM.md](LF_QUEUE_SYSTEM.md) for complete details.

