# Footage AutoLog Quick Reference Card

## File Naming Convention

### Part A (Import Flow) - Fast & Simple
```
ftg_autolog_A_XX_description.py
```
- **A** = Import workflow (Part A)
- **00** = Main runner
- **01-03** = Sequential steps

### Part B (AI Flow) - Queued & Complex
```
ftg_autolog_B_XX_description.py
```
- **B** = AI workflow (Part B)
- **00** = Main runner
- **01-04** = Queue job steps

## Quick Commands

### Start Part B Workers
```bash
./workers/start_ftg_autolog_B_workers.sh start
```

### Check Status
```bash
./workers/start_ftg_autolog_B_workers.sh status
```

### Stop Workers
```bash
./workers/start_ftg_autolog_B_workers.sh stop
```

## API Endpoints

### Trigger Part A (Import)
```bash
POST /run/ftg_autolog_A_00_run_all
```

### Trigger Part B (AI)
```bash
POST /run/ftg_autolog_B_00_run_all
```

### Batch Set Ready + Queue (Primary)
```bash
POST /run/ftg_ai_batch_ready
Body: ["FTG001", "FTG002"]
```

### Queue Status
```bash
GET /queue/ftg_autolog_B_status
```

## Status Flow

### Part A
```
0 - Pending Import
  ↓
1 - Imported
  ↓
2 - Thumbnail Ready
  ↓
Awaiting User Input (HALT)
```

### Part B
```
3 - Ready for AI
  ↓
4 - Frames Sampled
  ↓
5 - AI Analysis Complete
  ↓
6 - Frames Created
  ↓
7 - Avid Description (COMPLETE)
```

## Log Files
```
/tmp/ftg_autolog_B_worker_step1_*.log
/tmp/ftg_autolog_B_worker_step2_*.log
/tmp/ftg_autolog_B_worker_step3_*.log
/tmp/ftg_autolog_B_worker_step4_*.log
```

## File Structure
```
jobs/
├── ftg_autolog_A_00_run_all.py           # Part A: Main
├── ftg_autolog_A_01_get_file_info.py     # Part A: Step 1
├── ftg_autolog_A_02_generate_thumbnail.py # Part A: Step 2
├── ftg_autolog_A_03_scrape_url.py        # Part A: Step 3
├── ftg_autolog_B_00_run_all.py           # Part B: Main
├── ftg_autolog_B_01_assess_and_sample.py # Part B: Step 1
├── ftg_autolog_B_02_gemini_analysis.py   # Part B: Step 2
├── ftg_autolog_B_03_create_frames.py     # Part B: Step 3
├── ftg_autolog_B_04_transcribe_audio.py  # Part B: Step 4
└── ftg_autolog_B_queue_jobs.py           # Part B: Queue defs

workers/
└── start_ftg_autolog_B_workers.sh        # Worker manager

archive/
└── lf_autolog_queue_system/              # Old LF files
```

## Worker Configuration
- **Step 1**: 12 workers (Assess & Sample)
- **Step 2**: 2 workers (Gemini - rate limited)
- **Step 3**: 4 workers (Create Frames)
- **Step 4**: 2 workers (Audio Transcription)
- **Total**: 20 workers

## Testing
```bash
# Test Part A
curl -X POST http://localhost:8081/run/ftg_autolog_A_00_run_all \
  -H "X-API-Key: YOUR_KEY"

# Test Part B
curl -X POST http://localhost:8081/run/ftg_autolog_B_00_run_all \
  -H "X-API-Key: YOUR_KEY"

# Check queue
curl http://localhost:8081/queue/ftg_autolog_B_status \
  -H "X-API-Key: YOUR_KEY"
```

## Documentation
- **Implementation Guide**: `documentation/FTG_TWO_WORKFLOW_IMPLEMENTATION.md`
- **Quick Start**: `FTG_QUICKSTART.md`
- **Renaming Summary**: `RENAMING_COMPLETE.md`
- **This Card**: `QUICK_REFERENCE.md`


