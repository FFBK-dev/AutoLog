# Frame Status Management Fix

## 🚨 CRITICAL RULE: NEVER Update Frame Statuses Beyond "4 - Audio Transcribed"

### What Was Fixed

1. **Removed automatic frame status updates** when footage completes Step 6
   - Previously: Frames were moved to "5 - Generating Embeddings" 
   - Now: Frames stay at "4 - Audio Transcribed" for PSOS to handle

2. **Updated polling target configuration**
   - Removed: `"update_frame_statuses_after": "5 - Generating Embeddings"`
   - Added clear comment about PSOS responsibility

3. **Fixed run_footage_script function**
   - Removed: Automatic `update_frame_statuses_for_footage()` call
   - Now: Only updates footage status, leaves frames alone

4. **Updated frame completion check**
   - Only checks for "4 - Audio Transcribed" or caption content
   - No longer looks for PSOS-managed statuses

5. **Conservative parent terminal states**
   - Frames only skip when parent reaches "8 - Applying Tags" or "9 - Complete"
   - Removed "7 - Generating Embeddings" to allow frames to finish naturally

### Expected Behavior Now

✅ **Frames progress naturally:** 1 → 2 → 3 → 4 (stops here)
✅ **PSOS handles beyond "4 - Audio Transcribed":** 5 → 6 → complete
✅ **No more status jumping or reprocessing**
✅ **Clean separation of responsibilities**

### Key Files Modified

- `jobs/footage_autolog.py` - Main polling logic
- Updated terminal states, parent checks, and removed auto-updates

This ensures the polling system only manages frame workflow up to "4 - Audio Transcribed" and PSOS takes over from there, preventing the chaotic status jumping. 