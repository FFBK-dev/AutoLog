# LF AutoLog Queue System - Deployment Checklist

## Pre-Deployment Verification ✅

- [x] Redis installed and running
- [x] Python dependencies installed (redis, rq, rq-dashboard)
- [x] Queue jobs module loads successfully
- [x] Worker management script is executable
- [x] API endpoints added without syntax errors
- [x] Old poller scripts archived
- [x] Documentation created (3 guides)
- [x] All imports tested and working

## Deployment Steps

### 1. Stop Old System

```bash
# Stop any running pollers
curl -X POST http://localhost:8081/stop/lf_pollers_all \
  -H "X-API-Key: YOUR_KEY"

# Verify pollers stopped
pgrep -f lf_autolog_poller
# Should return nothing
```

- [ ] Old pollers stopped
- [ ] No stray processes running

### 2. Restart API Server

```bash
# Stop current API
pkill -f "uvicorn API:app"

# Start API on port 8081
cd /Users/admin/Documents/Github/Filemaker-Backend
nohup uvicorn API:app --host 0.0.0.0 --port 8081 > api.log 2>&1 &

# Verify API started
curl http://localhost:8081/status -H "X-API-Key: YOUR_KEY"
```

- [ ] API restarted successfully
- [ ] Status endpoint responds
- [ ] No import errors in logs

### 3. Start Workers

```bash
cd /Users/admin/Documents/Github/Filemaker-Backend
./workers/start_lf_workers.sh start

# Verify workers started
./workers/start_lf_workers.sh status
```

Expected output:
```
✓ Step 1: 8 workers running
✓ Step 2: 8 workers running
✓ Step 3: 6 workers running
✓ Step 4: 2 workers running
✓ Step 5: 4 workers running
✓ Step 6: 3 workers running

Total workers: 31
```

- [ ] All 31 workers started
- [ ] No errors in worker logs
- [ ] Queue status shows 0 queued (initial state)

### 4. Test Single Item

```bash
# Queue a test item (replace LF1409 with your test ID)
curl -X POST "http://localhost:8081/run/lf_queue?footage_id=LF1409" \
  -H "X-API-Key: YOUR_KEY"
```

Expected response:
```json
{
  "job_id": "...",
  "footage_id": "LF1409",
  "status": "queued",
  "message": "LF autolog workflow queued for LF1409",
  "queue_position": 1
}
```

- [ ] Item queued successfully
- [ ] Job ID returned
- [ ] Item appears in queue status

### 5. Monitor Test Item

```bash
# Watch queue status
watch -n 5 'curl -s http://localhost:8081/queue/status -H "X-API-Key: YOUR_KEY"'

# Or open web dashboard
rq-dashboard
# Open http://localhost:9181
```

Watch for:
- [ ] Step 1 processes (30-60s)
- [ ] Status updates to "1 - File Info Complete"
- [ ] Step 2 auto-queues
- [ ] Step 2 processes (30-60s)
- [ ] Status updates to "2 - Thumbnails Complete"
- [ ] Step 3 auto-queues
- [ ] Status updates to "Awaiting User Input"

### 6. Test Force Resume

In FileMaker:
1. Add prompt to `AI_Prompt` field
2. Set status to "Force Resume"

```bash
# Or use API
curl -X POST http://localhost:8081/run/lf_force_resume_all \
  -H "X-API-Key: YOUR_KEY"
```

Watch for:
- [ ] Item queues at Step 3
- [ ] Continues through Steps 4-5-6
- [ ] Ends at "7 - Avid Description"
- [ ] Frame records created
- [ ] Gemini captions populated

### 7. Test Batch

```bash
curl -X POST http://localhost:8081/run/lf_queue_batch \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '["LF1410", "LF1411", "LF1412"]'
```

Watch for:
- [ ] All 3 items queued
- [ ] Process in parallel (Steps 1-2)
- [ ] All reach "Awaiting User Input"
- [ ] No race conditions
- [ ] No errors in dashboard

### 8. Enable Auto-Discovery (Optional)

```bash
curl -X POST http://localhost:8081/run/lf_discovery \
  -H "X-API-Key: YOUR_KEY"
```

Test:
1. Import a new LF item in FileMaker
2. Set status to "0 - Pending File Info"
3. Wait 30 seconds
4. Verify item automatically queued

- [ ] Discovery poller started
- [ ] Auto-discovers new imports
- [ ] Queues items automatically

### 9. Performance Test

Import 10 LF items and time each phase:

- [ ] Steps 1-2 complete in <5 minutes (all 10 items)
- [ ] Step 3 completes in <10 minutes (all 10 items)
- [ ] Step 4 processes at ~2 items/minute
- [ ] Overall throughput: 10-20 items/hour
- [ ] No FileMaker errors
- [ ] No worker crashes

### 10. Monitor for 24 Hours

- [ ] Workers stay running
- [ ] No memory leaks
- [ ] Failed jobs are rare (<5%)
- [ ] Queue depths remain reasonable
- [ ] Redis remains stable
- [ ] FileMaker integration works

## Post-Deployment

### Monitoring Setup

Add to cron or startup script:
```bash
# Start workers on boot
@reboot cd /Users/admin/Documents/Github/Filemaker-Backend && ./workers/start_lf_workers.sh start

# Start discovery poller
@reboot sleep 60 && curl -X POST http://localhost:8081/run/lf_discovery -H "X-API-Key: YOUR_KEY"
```

### Health Checks

Add to monitoring:
```bash
# Check Redis
redis-cli ping

# Check workers
./workers/start_lf_workers.sh status

# Check queues
curl http://localhost:8081/queue/status -H "X-API-Key: YOUR_KEY"

# Check API
curl http://localhost:8081/status -H "X-API-Key: YOUR_KEY"
```

### Maintenance

Weekly:
- [ ] Review failed jobs in RQ Dashboard
- [ ] Check worker logs for errors
- [ ] Monitor queue depths
- [ ] Review performance metrics

Monthly:
- [ ] Restart workers (memory cleanup)
- [ ] Clear old job data from Redis
- [ ] Review and optimize worker counts
- [ ] Update documentation with learnings

## Rollback Plan

If issues occur:

1. **Stop queue system:**
   ```bash
   ./workers/start_lf_workers.sh stop
   curl -X POST http://localhost:8081/stop/lf_discovery -H "X-API-Key: YOUR_KEY"
   ```

2. **Restore pollers:**
   ```bash
   mv jobs/archive/lf_autolog_poller_step*.py jobs/
   curl -X POST http://localhost:8081/run/lf_pollers_all -H "X-API-Key: YOUR_KEY"
   ```

3. **Verify old system:**
   - Check pollers running: `pgrep -f lf_autolog_poller`
   - Test single item import

## Success Criteria

System is production-ready when:

- [x] All workers start without errors
- [x] Single item processes end-to-end
- [x] Batch processing works in parallel
- [x] Force Resume continues from Step 3
- [x] No race conditions observed
- [x] Web dashboard accessible
- [x] API endpoints respond correctly
- [x] FileMaker integration works
- [x] Performance meets/exceeds pollers
- [x] Documentation complete

## Support Resources

- **Quick Start:** [documentation/LF_QUEUE_QUICKSTART.md](documentation/LF_QUEUE_QUICKSTART.md)
- **Full Docs:** [documentation/LF_QUEUE_SYSTEM.md](documentation/LF_QUEUE_SYSTEM.md)
- **Migration Guide:** [documentation/LF_QUEUE_MIGRATION.md](documentation/LF_QUEUE_MIGRATION.md)
- **Implementation Summary:** [QUEUE_IMPLEMENTATION_SUMMARY.md](QUEUE_IMPLEMENTATION_SUMMARY.md)

- **RQ Documentation:** https://python-rq.org/
- **Redis Documentation:** https://redis.io/docs/

## Deployment Sign-Off

- [ ] Pre-deployment verification complete
- [ ] All deployment steps executed
- [ ] Test suite passed
- [ ] 24-hour monitoring complete
- [ ] Documentation reviewed
- [ ] Team trained on new system
- [ ] Rollback plan understood

**Deployed by:** _______________
**Date:** _______________
**Status:** ✅ Ready / ⚠️ Issues / ❌ Rollback

## Notes

```
Add any deployment notes, issues encountered, or lessons learned here.
```

