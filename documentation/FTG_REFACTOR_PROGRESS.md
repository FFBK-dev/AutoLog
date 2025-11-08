# Footage Autolog Two-Workflow Refactor

## Status: ✅ COMPLETE - Ready for Testing

## Overview
Restructuring LF autolog into two independent workflows:
- **Part A (Import)**: Fast, sequential processing (specs/thumbnails/URL)
- **Part B (AI)**: Queued, complex processing (frames/Gemini/transcription)

## Completed ✅

### Part A: Import Flow (Complete)
- ✅ `jobs/ftg_import_00_run_all.py` - Main runner
- ✅ `jobs/ftg_import_01_get_file_info.py` - Extract specs + false start detection
- ✅ `jobs/ftg_import_02_generate_thumbnail.py` - Parent thumbnail
- ✅ `jobs/ftg_import_03_scrape_url.py` - URL scraping (optional)
- Status progression: 0 - Pending Import → 1 - Imported → 2 - Thumbnail Ready → Awaiting User Input

### Part B: AI Flow (Complete)
- ✅ `jobs/ftg_ai_00_run_all.py` - Main runner
- ✅ `jobs/ftg_ai_01_assess_and_sample.py` - Frame sampling
- ✅ `jobs/ftg_ai_02_gemini_analysis.py` - Gemini API
- ✅ `jobs/ftg_ai_03_create_frames.py` - Frame records
- ✅ `jobs/ftg_ai_04_transcribe_audio.py` - Audio mapping
- ✅ `jobs/ftg_ai_queue_jobs.py` - RQ job definitions + workflow logic
- ✅ `workers/start_ftg_ai_workers.sh` - Worker management (20 workers)
- Status progression: 3 - Ready for AI → 4 - Frames Sampled → 5 - AI Analysis Complete → 6 - Frames Created → 7 - Avid Description

### API Endpoints (Complete)
- ✅ `POST /run/ftg_import_00_run_all` - Trigger Part A
- ✅ `POST /run/ftg_ai_00_run_all` - Trigger Part B
- ✅ `POST /run/ftg_ai_batch_ready` - Set items ready + queue (primary endpoint)
- ✅ `GET /queue/ftg_ai_status` - Check queue status

### Documentation (Complete)
- ✅ `documentation/FTG_TWO_WORKFLOW_IMPLEMENTATION.md` - Complete implementation guide
- ✅ False start protection at two layers
- ✅ Testing guide with curl examples
- ✅ Troubleshooting section
- ✅ FileMaker integration instructions

## Remaining Work (None - Implementation Complete)

### Part A: Import Flow - Step Scripts
1. **ftg_import_01_get_file_info.py**
   - Copy from lf_autolog_01
   - Update status: "1 - Imported"
   - Keep false start detection (< 5s → "False Start" status)
   
2. **ftg_import_02_generate_thumbnail.py**
   - Copy from lf_autolog_02
   - Update status: "2 - Thumbnail Ready"
   - No false start check (handled in Step 1)

3. **ftg_import_03_scrape_url.py**
   - Adapt from old footage_autolog_04
   - Gracefully skip if no URL
   - Update status: "Awaiting User Input"

### Part B: AI Flow - All Components
1. **ftg_ai_00_run_all.py** - Discovers "3 - Ready for AI"
2. **ftg_ai_01_assess_and_sample.py** - Copy from lf_autolog_03
3. **ftg_ai_02_gemini_analysis.py** - Copy from lf_autolog_04
4. **ftg_ai_03_create_frames.py** - Copy from lf_autolog_05
5. **ftg_ai_04_transcribe_audio.py** - Copy from lf_autolog_06
6. **ftg_ai_queue_jobs.py** - RQ job definitions
7. **workers/start_ftg_ai_workers.sh** - Worker management script

### API Endpoints
1. `/run/ftg_import_00_run_all` - Trigger Part A
2. `/run/ftg_ai_00_run_all` - Trigger Part B
3. `/run/ftg_ai_batch_ready` - Set multiple items to "3 - Ready for AI"

### False Start Protection in Part B
- Check at beginning of Step 1 (assess & sample)
- If false start detected, set to "False Start" and exit
- Prevents accidental AI processing of false starts

## New Status List

### Part A Statuses
- `0 - Pending Import` (start)
- `1 - Imported` (Step 1 complete)
- `2 - Thumbnail Ready` (Step 2 complete)
- `Awaiting User Input` (Part A complete, HALT)
- `False Start` (< 5s videos)

### Part B Statuses
- `3 - Ready for AI` (user sets this to trigger Part B)
- `4 - Frames Sampled` (Step 1 complete)
- `5 - AI Analysis Complete` (Step 2 complete)
- `6 - Frames Created` (Step 3 complete)
- `7 - Avid Description` (Part B complete, triggers FM server scripts)

## Design Decisions Confirmed

1. ✅ Part A: No queueing (sequential)
2. ✅ Part B trigger: User button sets "3 - Ready for AI"
3. ✅ No migration (new system for new records)
4. ✅ URL scraping: Fail gracefully
5. ✅ False start: Keep in Step 1, protect in Part B

## Next Steps

1. Complete Part A step scripts (3 files)
2. Create Part B workflow (7 files)
3. Add API endpoints
4. Test import flow end-to-end
5. Test AI flow end-to-end
6. Document for FileMaker team

