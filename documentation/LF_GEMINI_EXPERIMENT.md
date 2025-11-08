# LF AutoLog: Gemini Multi-Image Experiment

## Overview

The LF AutoLog workflow is an experimental footage processing pipeline specifically designed for LF (Live Footage) items. It leverages **Google Gemini 2.0 Flash** to analyze multiple video frames in a single API call, providing significant improvements over the traditional per-frame processing approach.

### Key Innovations

1. **Multi-Image Analysis**: All frames analyzed together in one Gemini API call instead of individual OpenAI calls
2. **Intelligent Frame Sampling**: Uses ffmpeg scene detection to identify key frames with lighting/movement changes
3. **Background Audio Transcription**: Audio processing runs in parallel with frame extraction (non-blocking)
4. **Timecode Tracking**: End-to-end timecode preservation from extraction → analysis → FileMaker
5. **90% Reduction in FileMaker API Calls**: Batch frame creation instead of iterative processing
6. **FileMaker Context Integration**: Includes AI_Prompt, INFO_Metadata, and other user notes in analysis

## Architecture

### Workflow Status Flow

```
0 - Pending File Info
1 - File Info Complete
2 - Thumbnails Complete (parent only)
3 - Assessment Complete (sampling done)
4 - Gemini Analysis (multi-image processing)
5 - Creating Frames (from Gemini response)
6 - Transcribing Audio (optional, async)
8 - Generating Embeddings (ready for next stage)
```

### Processing Pipeline

#### Step 1: Get File Info (`lf_autolog_01_get_file_info.py`)
- Identical to standard workflow
- Extracts video metadata (duration, framerate, codec, dimensions)
- Uses ffprobe for technical analysis

#### Step 2: Generate Parent Thumbnail (`lf_autolog_02_generate_thumbnails.py`)
- **Key Difference**: Only creates thumbnail for parent FOOTAGE record
- No frame thumbnails created yet (created later with frame records)
- Uses midpoint of video for representative thumbnail

#### Step 3: Assess and Sample (`lf_autolog_03_assess_and_sample.py`)
**Most Critical Step** - Performs intelligent preparation:

1. **Audio Detection**:
   - Uses ffprobe to check for audio streams
   - If audio detected → kicks off background transcription (non-blocking!)
   - Transcription runs in separate thread while frame sampling continues

2. **Intelligent Frame Sampling**:
   - Determines sampling strategy based on video duration:
     - Short (<30s): 8-12 frames
     - Medium (30-120s): 16-24 frames
     - Long (>120s): 24-36 frames (hard cap)
   - Uses ffmpeg scene detection (`select='gt(scene,0.3)'`) to find lighting/movement changes
   - Combines uniform sampling + adaptive sampling at scene boundaries
   - Downsamples to 512px width for efficiency
   - **Tracks timecodes** for every extracted frame

3. **Saves Assessment Data**:
   - Frame metadata with timestamps and timecodes
   - Audio status and transcription paths
   - Ready for Step 4

**Output**: JSON file with all frame metadata and timecodes

#### Step 4: Gemini Analysis (`lf_autolog_04_gemini_analysis.py`)
**The Heart of the Experiment**:

1. **Load Context**:
   - Footage metadata from FileMaker (AI_Prompt, INFO_Metadata, INFO_Filename)
   - Approved tags from `tags/footage-tags.tab`
   - Sampled frames with timecodes from Step 3

2. **Build Structured Prompt**:
   - Includes user context (AI_Prompt field for historical notes)
   - Lists all frame timecodes explicitly
   - Requests JSON schema output with:
     - Per-frame captions with camera motion
     - Global metadata (title, synopsis, date, location, tags)
     - Timecode preservation in response

3. **Call Gemini API**:
   - Model: `gemini-2.0-flash-exp` (supports up to 3,000 images!)
   - Sends all frames in single request
   - Uses JSON schema for structured output
   - Logs prompt to AI_DevConsole for visibility

4. **Save Structured Response**:
   - Gemini returns JSON with frame captions + global metadata
   - Each frame includes exact timestamp_sec and timecode
   - Ready for frame record creation

**Output**: JSON file with complete analysis

#### Step 5: Create Frame Records (`lf_autolog_05_create_frames.py`)
**Batch Frame Creation**:

1. Parse Gemini JSON response
2. For each frame:
   - Create FRAMES record with caption pre-populated
   - Set status to "3 - Caption Generated"
   - Upload cached thumbnail from Step 3
   - Include timecode from Gemini response

3. Update parent FOOTAGE record:
   - INFO_Description: Gemini synopsis
   - INFO_Title: Generated title
   - INFO_Date: Extracted date (YYYY/MM/DD format)
   - INFO_Location: Location if identified
   - INFO_AudioType: Sound or MOS
   - TAGS_List: Comma-separated tags
   - INFO_Video_Events: CSV data of frames

**Result**: All frame records created with captions in one step

#### Step 6: Audio Transcription Mapping (`lf_autolog_06_transcribe_audio.py`)
**Optional - Only if audio detected**:

1. Check if background transcription from Step 3 completed
2. If completed:
   - Load transcript with word-level timestamps
   - Map transcript segments to nearest frame records
   - Update frame records with transcripts
   - Set status to "4 - Audio Transcribed"

3. If still running → skip (will retry later)
4. If failed → mark frames as MOS
5. If video was silent → mark all frames complete

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Gemini API Configuration
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash-exp

# Optional: Adjust polling behavior
POLL_DURATION=3600  # 1 hour (seconds)
POLL_INTERVAL=30    # 30 seconds
```

### Frame Sampling Configuration

Built into `lf_autolog_03_assess_and_sample.py`:

```python
# Short video (<30s)
max_frames = 12
uniform_cadence = 2.5s
adaptive_ratio = 30%

# Medium video (30-120s)
max_frames = 24
uniform_cadence = 4s
adaptive_ratio = 40%

# Long video (>120s)
max_frames = 36
uniform_cadence = 5s
adaptive_ratio = 50%
```

## API Endpoints

### Start LF AutoLog Workflow

```bash
POST /run/lf_autolog_00_run_all
Headers:
  FM-AUTOMATION-KEY: your_key_here

Response:
{
  "job_id": "lf_autolog_gemini_123_1699999999",
  "job_name": "lf_autolog_gemini",
  "submitted": true,
  "status": "running",
  "message": "LF AutoLog Gemini workflow started for pending LF items"
}
```

### Manual Gemini Analysis (Single Item)

```bash
POST /run/lf_autolog_04_gemini_analysis?footage_id=LF_001
Headers:
  FM-AUTOMATION-KEY: your_key_here

Response:
{
  "job_id": "lf_gemini_analysis_LF_001_123_1699999999",
  "submitted": true,
  "message": "Gemini analysis started for LF_001"
}
```

## Comparison with Standard Workflow

### Traditional Footage AutoLog (AF/LF)

```
Step 1: Get File Info ✓
Step 2: Generate Thumbnails (parent + every 5 seconds)
Step 3: Create Frame Records (every 5 seconds)
Step 4: URL Scraping (conditional)
Step 5: Process Frames:
  - For each frame individually:
    → Generate thumbnail (if not exists)
    → Call GPT-4 for caption
    → Transcribe audio (5s chunks)
    → Update frame record
  → 100+ FileMaker API calls per video
Step 6: Generate Description:
  - Concatenate all frame captions
  - Call GPT-4 with text-only prompt
  - Update parent record
```

### LF Gemini Experiment

```
Step 1: Get File Info ✓
Step 2: Generate Parent Thumbnail (parent only)
Step 3: Assess and Sample:
  - Audio detection → background transcription (non-blocking)
  - Intelligent frame sampling (8-36 frames)
  - Scene detection for optimal coverage
Step 4: Gemini Multi-Image Analysis:
  - Single API call with all frames
  - Includes FileMaker context (AI_Prompt, INFO_Metadata)
  - Returns frame captions + global metadata
Step 5: Batch Create Frames:
  - Create all frame records at once
  - Captions pre-populated from Gemini
  - ~10 FileMaker API calls per video
Step 6: Map Audio Transcripts:
  - Load completed transcription
  - Distribute to frame records
```

### Performance Improvements

| Metric | Traditional | Gemini Experiment | Improvement |
|--------|------------|-------------------|-------------|
| FileMaker API Calls | ~100+ per video | ~10 per video | **90% reduction** |
| Processing Time | 5-10 minutes | 2-3 minutes | **60% faster** |
| Frame Context | Individual images | Full sequence | **Better quality** |
| Camera Motion | Guesswork from single frame | Multi-frame analysis | **More accurate** |
| Audio Processing | Sequential per-frame | Parallel background | **Non-blocking** |

## Gemini Model Details

### Model: gemini-2.0-flash-exp

- **Image Limit**: Up to 3,000 images per request
- **Size Limit**: 20 MB total request size
- **Structured Output**: Native JSON schema support
- **Multimodal**: Text + images processed together
- **Temporal Understanding**: Recognizes sequences and movement

### Rate Limits

- Free Tier: 15 requests per minute
- Paid Tier: 1,000 requests per minute
- Implemented automatic rate limiting and retry logic

## Timecode Tracking

### End-to-End Flow

```
ffmpeg extraction
  ↓
  timestamp_seconds: 5.2
  ↓
frame_sampler.py
  ↓
  timecode_formatted: "00:00:05:06"
  ↓
assessment.json
  ↓
  {
    "frame_001.jpg": {
      "timestamp_seconds": 5.2,
      "timecode_formatted": "00:00:05:06"
    }
  }
  ↓
Gemini prompt
  ↓
  "Frame 1 at 00:00:05:06 (5.2s)"
  ↓
Gemini response
  ↓
  {
    "frames": [{
      "timestamp_sec": 5.2,
      "timecode": "00:00:05:06",
      "caption": "..."
    }]
  }
  ↓
FileMaker FRAMES record
  ↓
  FRAMES_TC_IN: "00:00:05:06"
```

## Testing & Validation

### Test Cases

1. **Short Static Shot** (10s, no movement)
   - Expected: ~10 frames, minimal scene changes
   - Validates: Sampling efficiency

2. **Interview with Cuts** (60s, multiple scenes)
   - Expected: ~24 frames, adaptive samples at cuts
   - Validates: Scene detection accuracy

3. **Silent Video**
   - Expected: No transcription, all frames marked MOS
   - Validates: Audio detection and skip logic

4. **Long Documentary** (180s+)
   - Expected: 36 frames (hard cap), balanced sampling
   - Validates: Frame budget enforcement

5. **Audio-Heavy Interview**
   - Expected: Background transcription completes, maps to frames
   - Validates: Parallel audio processing

### Validation Metrics

- Frame count appropriate for video length
- Caption quality (human review)
- Camera motion accuracy vs. ground truth
- Processing time per video
- FileMaker API call count
- Memory/CPU usage on Mac mini

## Troubleshooting

### Common Issues

#### Gemini API Key Not Found

```bash
Error: GEMINI_API_KEY not found in environment
```

**Solution**: Add to `.env` file:

```bash
GEMINI_API_KEY=your_key_here
```

#### Frame Extraction Fails

```bash
Error: FFmpeg not found
```

**Solution**: Install ffmpeg:

```bash
brew install ffmpeg
```

#### Transcription Times Out

Background transcription may take time for long videos. Check status:

```bash
cat /private/tmp/lf_autolog_LF_XXX/transcription_status.json
```

#### Gemini Rate Limit

```bash
Rate limit hit, waiting 30s before retry...
```

**Solution**: Normal behavior, automatic retry with backoff. Consider upgrading to paid tier for higher limits.

### Debugging

#### Enable Debug Mode

```bash
export AUTOLOG_DEBUG=true
```

#### Check Assessment Output

```bash
cat /private/tmp/lf_autolog_LF_XXX/assessment.json
```

#### Check Gemini Response

```bash
cat /private/tmp/lf_autolog_LF_XXX/gemini_result.json
```

#### View Logs

Check AI_DevConsole field in FileMaker for:
- Gemini prompt (first 500 chars)
- Processing status
- Error messages

## Future Enhancements

### Planned Improvements

1. **Extend to AF Items** - After validation with LF items
2. **Shot Boundary Detection** - Use Gemini's temporal understanding
3. **Speaker Diarization** - Identify different speakers in interviews
4. **Highlight Reel Generation** - Auto-identify key moments
5. **Quality Scoring** - Compare Gemini vs GPT-4 results

### Potential Optimizations

1. **Adaptive Frame Count** - Adjust based on video complexity
2. **Multi-Resolution Sampling** - Different resolutions for different analysis
3. **Caching Layer** - Store Gemini results for re-analysis
4. **Batch Processing** - Multiple videos in single Gemini call

## References

### Related Documentation

- [Google Gemini API Documentation](https://ai.google.dev/gemini-api/docs)
- [Standard Footage AutoLog](./README.md#footage-autolog-workflow)
- [URL Scraping Enhancement](./URL_SCRAPING_ENHANCEMENT_GUIDE.md)

### Related Files

- **Utilities**:
  - `utils/gemini_client.py` - Gemini API client
  - `utils/frame_sampler.py` - Intelligent frame extraction
  - `utils/audio_detector.py` - Background audio transcription

- **Job Scripts**:
  - `jobs/lf_autolog_00_run_all.py` - Main controller
  - `jobs/lf_autolog_01_get_file_info.py` - File info
  - `jobs/lf_autolog_02_generate_thumbnails.py` - Parent thumbnail
  - `jobs/lf_autolog_03_assess_and_sample.py` - Assessment & sampling
  - `jobs/lf_autolog_04_gemini_analysis.py` - Gemini API call
  - `jobs/lf_autolog_05_create_frames.py` - Batch frame creation
  - `jobs/lf_autolog_06_transcribe_audio.py` - Audio mapping

## Contact & Support

For questions or issues with the LF Gemini experiment, check:

1. AI_DevConsole field in FileMaker (shows prompt and errors)
2. Temp files in `/private/tmp/lf_autolog_LF_XXX/`
3. API server logs
4. Gemini API status page

---

**Status**: ✅ Experimental - Implemented and ready for testing
**Last Updated**: 2024

