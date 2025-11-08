# Footage AutoLog Workers - Auto-Start with API

## What Changed

The Footage AutoLog Part B (AI Processing) workers now **automatically start and stop with the API server**.

### Before
```bash
# Had to manually start workers separately
./workers/start_ftg_autolog_B_workers.sh start

# Then start API
python3 -m uvicorn API:app --host 0.0.0.0 --port 8081
```

### After
```bash
# Just start the API - workers start automatically!
python3 -m uvicorn API:app --host 0.0.0.0 --port 8081 --reload
```

## How It Works

### On API Startup
1. API starts
2. Mounts network volumes (footage, stills)
3. **Automatically starts 20 Footage AutoLog Part B workers**
4. Ready to process!

### On API Shutdown
1. API receives shutdown signal (Ctrl+C or SIGTERM)
2. **Gracefully stops all 20 workers**
3. API shuts down cleanly

## Benefits

✅ **Convenience**: No need to remember to start workers separately  
✅ **Reliability**: Workers always available when API is running  
✅ **Clean Shutdown**: Workers stop gracefully with API  
✅ **Fewer Steps**: One command to start everything  

## Implementation Details

**File**: `API.py`

**Startup Event** (`@app.on_event("startup")`):
```python
# Start Footage AutoLog Part B (AI) Workers
logging.info("🤖 Starting Footage AutoLog Part B workers...")
worker_script = Path(__file__).resolve().parent / "workers" / "start_ftg_autolog_B_workers.sh"
subprocess.run([str(worker_script), "start"], timeout=30)
logging.info("✅ Footage AutoLog Part B workers started (20 workers)")
```

**Shutdown Event** (`@app.on_event("shutdown")`):
```python
# Stop Footage AutoLog Part B (AI) Workers
logging.info("🛑 Stopping Footage AutoLog Part B workers...")
worker_script = Path(__file__).resolve().parent / "workers" / "start_ftg_autolog_B_workers.sh"
subprocess.run([str(worker_script), "stop"], timeout=10)
logging.info("✅ Footage AutoLog Part B workers stopped gracefully")
```

## Startup Logs

When you start the API, you'll see:
```
🚀 Starting FileMaker Automation API
🔧 Mounting network volumes...
✅ Footage volume mounted successfully
✅ Stills volume mounted successfully
🤖 Starting Footage AutoLog Part B workers...
✅ Footage AutoLog Part B workers started (20 workers)
⚠️ Using direct OpenAI API calls
```

## Shutdown Logs

When you stop the API (Ctrl+C), you'll see:
```
🔄 Shutting down FileMaker Automation API
🛑 Stopping Footage AutoLog Part B workers...
✅ Footage AutoLog Part B workers stopped gracefully
```

## Manual Worker Management (Still Available)

You can still manually manage workers if needed:

```bash
# Check status
./workers/start_ftg_autolog_B_workers.sh status

# Manually restart (if API is already running)
./workers/start_ftg_autolog_B_workers.sh restart

# Manually stop (if needed)
./workers/start_ftg_autolog_B_workers.sh stop
```

## Testing

### Test Auto-Start
1. Stop current API (if running)
2. Stop any running workers: `./workers/start_ftg_autolog_B_workers.sh stop`
3. Start API: `python3 -m uvicorn API:app --host 0.0.0.0 --port 8081 --reload`
4. Check logs for "✅ Footage AutoLog Part B workers started (20 workers)"
5. Verify: `./workers/start_ftg_autolog_B_workers.sh status`

### Test Auto-Stop
1. With API running, press Ctrl+C
2. Check logs for "✅ Footage AutoLog Part B workers stopped gracefully"
3. Verify: `./workers/start_ftg_autolog_B_workers.sh status` (should show 0 workers)

## Troubleshooting

### Workers Don't Start
- Check worker script is executable: `chmod +x workers/start_ftg_autolog_B_workers.sh`
- Check Redis is running: `redis-cli ping` (should return PONG)
- Check API logs for error messages

### Workers Don't Stop
- They may already be stopped (check with `status` command)
- Manual stop: `./workers/start_ftg_autolog_B_workers.sh stop`
- Force kill: `pkill -f "rq worker ftg_ai_step"`

## Production Deployment

### Using systemd (Linux)
```ini
[Unit]
Description=FileMaker Automation API
After=network.target redis.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/Filemaker-Backend
ExecStart=/usr/bin/python3 -m uvicorn API:app --host 0.0.0.0 --port 8081
Restart=always

[Install]
WantedBy=multi-user.target
```

Workers will start/stop automatically with the service.

### Using Docker
```dockerfile
CMD ["uvicorn", "API:app", "--host", "0.0.0.0", "--port", "8081"]
```

Workers will start/stop automatically with the container.

## Notes

- Workers only start if Redis is accessible
- 30-second timeout for worker startup (should take ~2 seconds)
- 10-second timeout for worker shutdown (should take ~1 second)
- Error handling: API will continue even if worker start/stop fails
- Logs all worker management events for debugging

---

**This change makes managing the Footage AutoLog system much simpler!** 🚀


