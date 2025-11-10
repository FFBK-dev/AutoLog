# Queue Management - Footage AutoLog Part B

## Automatic Queue Clearing on API Shutdown

As of the latest update, **RQ queues are automatically cleared when API.py shuts down**. This design decision reflects the coupled architecture where:

1. **Workers start when API.py starts** (via `startup_event()`)
2. **Workers stop when API.py stops** (via `shutdown_event()`)
3. **FileMaker clients require the API to be running**
4. **No one uses the system when API is down**

### Why This Makes Sense

Since the API is the "lifeblood" of the system and workers are lifecycle-coupled to it, restarting the API is effectively a **system restart**. Clearing queues on shutdown prevents:

- Stale/duplicate jobs from persisting across restarts
- Confusion about queue state after a restart
- Need for manual queue clearing

### What Happens on API Shutdown

When you stop `API.py` (via `Ctrl+C` or process termination):

```
🔄 Shutting down FileMaker Automation API
🛑 Stopping Footage AutoLog Part B workers...
  ✅ Footage AutoLog Part B workers stopped gracefully
🧹 Clearing RQ queues...
  ✅ Cleared Step 1: 258 items
  ✅ Cleared Step 1 failed: 5 items
  ✅ Cleared Step 2: 0 items
  ...
✅ Queue cleanup complete: 263 items cleared
```

### After API Restart

1. **API starts** → Workers start → Queues are empty
2. **Re-queue items** as needed:
   ```bash
   python3 jobs/ftg_autolog_B_00_run_all.py
   ```
3. **Dashboard shows clean state** → http://localhost:9181

### Manual Queue Clearing (While API is Running)

If you need to clear queues while the API is still running:

```bash
python3 utils/admin_clear_queues.py
```

This is useful for:
- Debugging while the system is running
- Resetting queues without restarting the entire API
- Testing queue behavior

### Best Practices

#### ✅ DO:
- Restart the API to get a clean system state
- Use the dashboard to monitor queue status
- Re-queue items after API restart if needed

#### ❌ DON'T:
- Worry about manually clearing queues on restart
- Expect queued jobs to persist across API restarts
- Run workers independently of the API

### Monitoring Queue State

**Dashboard**: http://localhost:9181
- Real-time view of all queued and processing items
- Filter by step, search by footage ID
- Auto-refreshes every 5 seconds

**Check queue status programmatically**:
```python
from jobs.ftg_autolog_B_queue_jobs import q_step1, q_step2, q_step3, q_step4

print(f"Step 1: {len(q_step1)} items")
print(f"Step 2: {len(q_step2)} items")
print(f"Step 3: {len(q_step3)} items")
print(f"Step 4: {len(q_step4)} items")
```

### Architecture Summary

```
┌─────────────────────────────────────────────┐
│              API.py (Lifeblood)             │
├─────────────────────────────────────────────┤
│  Startup:                                   │
│  1. Mount volumes                           │
│  2. Start workers (11 workers)              │
│  3. Ready to serve FileMaker clients        │
├─────────────────────────────────────────────┤
│  Shutdown:                                  │
│  1. Stop workers                            │
│  2. Clear all RQ queues                     │
│  3. Clean slate for next startup            │
└─────────────────────────────────────────────┘
```

### Related Files

- **API.py**: Startup/shutdown handlers (lines 142-241)
- **dashboard/ftg_dashboard.py**: Queue monitoring GUI
- **utils/admin_clear_queues.py**: Manual queue clearing utility
- **jobs/ftg_autolog_B_00_run_all.py**: Re-queue items at status "3 - Ready for AI"

### Questions?

This design reflects the reality that your system is used as a **unified whole**, not as independent components. The API, workers, and queues all start and stop together, which is why automatic queue clearing on shutdown makes perfect sense for this architecture.

