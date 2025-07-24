# Stills AutoLog Polling System Conversion

## Overview

We have successfully converted the stills autolog system from a sequential workflow approach (`stills_autolog_00_run_all.py`) to a modern polling-based system (`stills_autolog.py`), following the same architectural pattern used for the footage system conversion.

## Architecture Comparison

### Old System: Sequential Workflow (`stills_autolog_00_run_all.py`)
- **Batch Processing**: Processes items sequentially through all steps
- **Workflow State Management**: Complex step-by-step progression
- **Failure Sensitivity**: One failed item can impact the entire batch
- **Manual Retry**: Requires manual intervention for stuck workflows
- **Resource Inefficiency**: Items wait for others to complete

### New System: Polling-Based (`stills_autolog.py`)
- **Individual Record Processing**: Each record advances independently
- **Status-Based Polling**: Polls every 10 seconds for records at each status
- **Resilient**: Individual failures don't affect other records
- **Automatic Retries**: Seamless retry on next poll cycle
- **Efficient**: High concurrency with step chaining

## Key Benefits of Polling System

### 1. **Resilience**
- Individual record failures don't block others
- Seamless retries without manual intervention
- Graceful handling of network/system issues

### 2. **Performance**
- High concurrency (up to 30 workers for stills)
- Step chaining: records can advance through multiple steps in one cycle
- No waiting for batch completion

### 3. **Simplicity**
- No complex workflow state management
- Status-based processing is more intuitive
- Easier debugging and monitoring

### 4. **Scalability**
- Handles any number of records efficiently
- Auto-stops when all records reach completion
- Environment variable configuration

## Stills Workflow Steps

The polling system maintains the same 5-step workflow:

```
1. Get File Info           (0 → 1)
2. Copy to Server          (1 → 2) 
3. Parse Metadata          (2 → 3)
4. Scrape URL*             (3 → 4) - conditional if URL exists
5. Generate Description    (3/4 → 5 → 6) - with metadata evaluation
```

*Step 4 is skipped if no URL is present, proceeding directly to metadata evaluation.

## Polling Logic

### Core Polling Loop
```python
# Polls every 10 seconds
while time.time() - start_time < poll_duration:
    # Get ALL records from FileMaker
    # Filter by non-terminal statuses
    # Process each record independently
    # Chain steps when possible
    # Auto-stop when all complete
```

### Step Chaining
Records can advance through multiple steps in a single poll cycle:
- **Example**: A record at "0 - Pending File Info" could advance through steps 1→2→3 in one cycle
- **Benefit**: Faster overall processing time
- **Limit**: Maximum 5 steps per cycle to prevent infinite loops

### Special Handling

#### URL Scraping (Step 4)
```python
if current_status == "3 - Metadata Parsed":
    url = record_data.get("url", '')
    if not url:
        # Skip URL scraping, proceed to metadata evaluation
        evaluate_metadata_and_proceed()
    else:
        # Run URL scraping step
        run_url_scraping()
```

#### Metadata Evaluation
```python
if current_status == "4 - Scraping URL":
    # Get fresh data including scraped content
    metadata_quality = evaluate_metadata_quality(fresh_data)
    if metadata_quality_good:
        # Proceed to description generation
    else:
        # Set to "Awaiting User Input"
```

#### User Resume Logic
```python
if current_status == "Awaiting User Input":
    metadata_quality = evaluate_metadata_quality(current_data)
    if metadata_quality_good:
        # Resume from description generation
    else:
        # Keep waiting for user input
```

## Configuration

### Environment Variables
```bash
# Poll duration (default: 1 hour)
export POLL_DURATION=3600

# Poll interval (default: 10 seconds)  
export POLL_INTERVAL=10
```

### High Concurrency Settings
- **Max Workers**: 30 concurrent workers for stills processing
- **Optimized for**: M4 Mac Mini performance characteristics
- **Timeout**: 300 seconds per script execution

## Terminal States

The polling system recognizes these terminal states and stops early:
- `"6 - Generating Embeddings"` - Workflow complete
- `"Awaiting User Input"` - Needs manual intervention

## Usage Examples

### Basic Usage
```bash
# Run with defaults (1 hour duration, 10-second intervals)
python3 jobs/stills_autolog.py
```

### Custom Configuration
```bash
# Run for 30 minutes with 5-second intervals
POLL_DURATION=1800 POLL_INTERVAL=5 python3 jobs/stills_autolog.py
```

### Monitoring Output
```
[12:34:56.789] 🚀 Starting fast concurrent stills polling workflow
[12:34:56.790] 📊 Poll duration: 3600s, interval: 10s
[12:34:56.791] 📋 Will stop early if all records reach completion or 'Awaiting User Input'

=== POLL CYCLE 1 ===
[12:34:56.892] 📊 Found 15 stills records to process
[12:34:57.123] 🖼️ ST0001: 0 - Pending File Info
[12:34:57.124] ⚡ ST0001: Chaining to next step → 1 - File Info Complete
[12:34:57.234] ⚡ ST0001: Chaining to next step → 2 - Server Copy Complete
[12:34:57.456] 🚀 ST0001: Completed 2 steps in this cycle!
[12:34:58.123] Poll cycle 1 complete (1.2s)
[12:34:58.124] Cycle results: 15 successful, 0 failed
```

## Key Differences from Footage System

### Simpler Architecture
- **No Parent-Child Dependencies**: Stills has no frame records
- **Linear Workflow**: Straightforward 5-step progression
- **Single Layout**: Only manages "Stills" layout vs "FOOTAGE" + "FRAMES"

### Workflow-Specific Logic
- **URL Handling**: Conditional URL scraping based on URL presence
- **Metadata Evaluation**: Single evaluation point after URL scraping
- **No Frame Completion**: No need to wait for child record completion

### Field Mappings
- **Stills-Specific Fields**: Uses stills field mappings
- **OpenAI Keys**: Includes multiple API key fields for load balancing
- **Simplified Status**: Only one status field vs footage + frame statuses

## Migration Path

### Phase 1: Testing
1. Keep existing `stills_autolog_00_run_all.py` as backup
2. Test new `stills_autolog.py` with small batches
3. Monitor performance and error handling

### Phase 2: Gradual Rollout
1. Use polling system for new items
2. Run both systems in parallel initially
3. Monitor performance differences

### Phase 3: Full Migration
1. Switch all processing to polling system
2. Update API endpoints to use new system
3. Remove old sequential workflow system

## Performance Expectations

Based on footage system conversion results:
- **3-5x faster processing** due to parallelization
- **Better resource utilization** with step chaining
- **Improved reliability** with automatic retries
- **Faster failure recovery** with individual record processing

## Monitoring and Debugging

### Real-Time Monitoring
```bash
# Watch polling activity in real-time
tail -f /path/to/logs | grep "POLL CYCLE"
```

### Performance Metrics
- Poll cycles completed
- Records processed per cycle
- Success/failure rates
- Average processing time per record

### Debug Mode
```bash
# Enable verbose debugging
export AUTOLOG_DEBUG=true
python3 jobs/stills_autolog.py
```

## Integration with API

The new polling system integrates seamlessly with the existing API:
- Same script endpoints and arguments
- Compatible with existing job tracking
- Maintains all field mappings and status flows

This conversion brings the stills system up to the same modern, resilient architecture as the footage system, providing better performance, reliability, and maintainability. 