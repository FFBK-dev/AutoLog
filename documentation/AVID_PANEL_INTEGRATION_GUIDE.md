# Avid Panel Integration Guide
## `avid-find-similar` API Endpoint

### Overview
The `avid-find-similar` endpoint provides AI-powered similarity search across your media library. Given any media ID (stills, live footage, or archival), it returns a ranked list of visually or contextually similar items.

## API Configuration

### Base URL
```
http://10.0.222.144:8081
```

### Authentication
All requests require the API key header:
```
X-API-Key: supersecret
```

### Content Type
```
Content-Type: application/json
```

## Endpoint Details

### Submit Similarity Search Job
```
POST /run/avid-find-similar
```

**Request Body:**
```json
{
  "args": ["<media_id>"]
}
```

**Response:**
```json
{
  "job_id": "avid-find-similar_15_1753468123",
  "submitted": true
}
```

### Check Job Status
```
GET /job/{job_id}
```

**Response (Completed):**
```json
{
  "job_name": "avid-find-similar",
  "args": ["S01000"],
  "submitted_at": "2024-12-25T18:45:30.123456",
  "completed_at": "2024-12-25T18:45:45.789012",
  "status": "completed",
  "results": {
    "input_id": "S01000",
    "core_id": "S01000",
    "media_type": "stills",
    "total_results": 150,
    "similar_items": [
      "S00981",
      "S00982",
      "S00983",
      "S00984",
      "S00985"
    ]
  }
}
```

## Test Commands

### 1. Test Stills Similarity Search
```bash
# Submit job
curl -X POST "http://10.0.222.144:8081/run/avid-find-similar" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: supersecret" \
  -d '{"args": ["S01000"]}'

# Expected response:
# {"job_id": "avid-find-similar_X_XXXXXXXXXX", "submitted": true}

# Check status (replace with actual job_id)
curl -H "X-API-Key: supersecret" \
  "http://10.0.222.144:8081/job/avid-find-similar_X_XXXXXXXXXX"
```

### 2. Test Live Footage Similarity Search
```bash
# Submit job
curl -X POST "http://10.0.222.144:8081/run/avid-find-similar" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: supersecret" \
  -d '{"args": ["LF0022"]}'

# Check status (replace with actual job_id)
curl -H "X-API-Key: supersecret" \
  "http://10.0.222.144:8081/job/avid-find-similar_X_XXXXXXXXXX"
```

### 3. Test Archival Footage Similarity Search
```bash
# Submit job
curl -X POST "http://10.0.222.144:8081/run/avid-find-similar" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: supersecret" \
  -d '{"args": ["AF0009"]}'

# Check status (replace with actual job_id)
curl -H "X-API-Key: supersecret" \
  "http://10.0.222.144:8081/job/avid-find-similar_X_XXXXXXXXXX"
```

### 4. Test ID Cleaning (with suffixes)
```bash
# Test with stills ID that has suffixes
curl -X POST "http://10.0.222.144:8081/run/avid-find-similar" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: supersecret" \
  -d '{"args": ["S01000.sub.01"]}'

# Test with live footage ID that has suffixes  
curl -X POST "http://10.0.222.144:8081/run/avid-find-similar" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: supersecret" \
  -d '{"args": ["LF0022_test.mov"]}'

# Test with archival footage ID that has suffixes
curl -X POST "http://10.0.222.144:8081/run/avid-find-similar" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: supersecret" \
  -d '{"args": ["AF0009.final"]}'
```

## Media Type Detection

The system automatically detects media type based on ID format:

| **ID Format** | **Media Type** | **Example** | **Description** |
|---------------|----------------|-------------|-----------------|
| `S#####` | `stills` | `S01000` | Still images (5 digits) |
| `LF####` | `live` | `LF0022` | Live footage (4 digits) |
| `AF####` | `archival` | `AF0009` | Archival footage (4 digits) |

## ID Cleaning

The system automatically cleans input IDs:

| **Input** | **Cleaned To** | **Notes** |
|-----------|----------------|-----------|
| `S01000` | `S01000` | No cleaning needed |
| `S01000.sub.01` | `S01000` | Removes .sub.01 suffix |
| `S01000_001` | `S01000` | Removes _001 suffix |
| `S01000.mov` | `S01000` | Removes file extension |
| `s01000` | `S01000` | Converts to uppercase |
| `LF0022_test.mov` | `LF0022` | Removes suffix and extension |
| `AF0009.final` | `AF0009` | Removes .final suffix |

## Response Format

### Successful Response
```json
{
  "input_id": "S01000.sub.01",    // Original input
  "core_id": "S01000",            // Cleaned ID used for search
  "media_type": "stills",         // stills | live | archival
  "total_results": 150,           // Number of similar items found
  "similar_items": [              // Array of similar media IDs (ranked by similarity)
    "S00981",
    "S00982",
    "S00983"
  ]
}
```

### Job Status Values
- `"running"` - Job is still processing
- `"completed"` - Job finished successfully, check `results` field
- `"failed"` - Job failed, no results available

## Avid Panel Implementation

### 1. Basic Integration Example (JavaScript)
```javascript
class SimilaritySearchAPI {
  constructor() {
    this.baseURL = 'http://10.0.222.144:8081';
    this.apiKey = 'supersecret';
    this.headers = {
      'Content-Type': 'application/json',
      'X-API-Key': this.apiKey
    };
  }

  async findSimilarItems(mediaId) {
    try {
      // Submit job
      const submitResponse = await fetch(`${this.baseURL}/run/avid-find-similar`, {
        method: 'POST',
        headers: this.headers,
        body: JSON.stringify({ args: [mediaId] })
      });
      
      if (!submitResponse.ok) {
        throw new Error(`HTTP ${submitResponse.status}: ${submitResponse.statusText}`);
      }
      
      const { job_id } = await submitResponse.json();
      
      // Poll for completion
      return await this.pollForResults(job_id);
      
    } catch (error) {
      console.error('Similarity search failed:', error);
      throw error;
    }
  }

  async pollForResults(jobId, maxAttempts = 15, interval = 2000) {
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(resolve => setTimeout(resolve, interval));
      
      const statusResponse = await fetch(`${this.baseURL}/job/${jobId}`, {
        headers: { 'X-API-Key': this.apiKey }
      });
      
      if (!statusResponse.ok) {
        throw new Error(`HTTP ${statusResponse.status}: ${statusResponse.statusText}`);
      }
      
      const jobInfo = await statusResponse.json();
      
      if (jobInfo.status === 'completed') {
        return jobInfo.results;
      } else if (jobInfo.status === 'failed') {
        throw new Error('Similarity search job failed');
      }
      
      // Still running, continue polling
    }
    
    throw new Error('Similarity search timeout after 30 seconds');
  }
}

// Usage Example
const api = new SimilaritySearchAPI();

// Find similar stills
const stillsResults = await api.findSimilarItems('S01000');
console.log(`Found ${stillsResults.total_results} similar stills`);
console.log('Similar items:', stillsResults.similar_items);

// Find similar live footage  
const liveResults = await api.findSimilarItems('LF0022');
console.log(`Found ${liveResults.total_results} similar live footage`);

// Find similar archival footage
const archivalResults = await api.findSimilarItems('AF0009');
console.log(`Found ${archivalResults.total_results} similar archival footage`);
```

### 2. Result Processing
```javascript
function processSimilarityResults(results) {
  const { media_type, similar_items, total_results } = results;
  
  // Handle different media types
  switch (media_type) {
    case 'stills':
      return {
        type: 'Still Images',
        count: total_results,
        items: similar_items.map(id => ({
          id: id,
          type: 'Still Image',
          thumbnailURL: `http://your-server/thumbnails/stills/${id}.jpg`
        }))
      };
      
    case 'live':
      return {
        type: 'Live Footage',
        count: total_results,
        items: similar_items.map(id => ({
          id: id,
          type: 'Live Footage',
          thumbnailURL: `http://your-server/thumbnails/footage/${id}.jpg`
        }))
      };
      
    case 'archival':
      return {
        type: 'Archival Footage',
        count: total_results,
        items: similar_items.map(id => ({
          id: id,
          type: 'Archival Footage',
          thumbnailURL: `http://your-server/thumbnails/footage/${id}.jpg`
        }))
      };
      
    default:
      throw new Error(`Unknown media type: ${media_type}`);
  }
}
```

### 3. Error Handling
```javascript
async function safeSearchSimilar(mediaId) {
  try {
    const results = await api.findSimilarItems(mediaId);
    return { success: true, data: results };
  } catch (error) {
    // Handle different error types
    if (error.message.includes('Invalid ID format')) {
      return { 
        success: false, 
        error: 'Invalid media ID format. Must be S##### (stills) or LF####/AF#### (footage).' 
      };
    } else if (error.message.includes('timeout')) {
      return { 
        success: false, 
        error: 'Search took too long. Please try again.' 
      };
    } else {
      return { 
        success: false, 
        error: 'Search failed. Please check your connection and try again.' 
      };
    }
  }
}
```

## Performance Notes

- **Typical Duration**: 5-15 seconds
- **Recommended Polling**: Every 2 seconds
- **Max Timeout**: 30 seconds
- **Concurrent Requests**: Supported, but avoid flooding

## Troubleshooting

### Common Issues

1. **401 Unauthorized**
   - Check API key: `X-API-Key: supersecret`

2. **404 Job Not Found**  
   - Verify job_id from submission response
   - Job may have expired (check immediately after submission)

3. **Validation Error: Invalid ID format**
   - Ensure ID follows format: S##### or LF####/AF####
   - System will clean suffixes automatically

4. **Job Status: failed**
   - Media ID may not exist in database
   - Try with known valid IDs from test commands above

### Test Media IDs (Confirmed Working)
- **Stills**: `S01000`, `S00981`, `S00982`
- **Live Footage**: `LF0022`, `LF0021`, `LF0023`  
- **Archival Footage**: `AF0009`, `AF0008`, `AF0011`

## Support

For integration support or issues:
1. Test with provided curl commands first
2. Verify network connectivity to `10.0.222.144:8081`
3. Check API key configuration
4. Use test media IDs to isolate issues

---

**Ready to integrate? Start with the test commands above! 🚀** 