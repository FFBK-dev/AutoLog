# AI Prompt Engineering Visibility

## Overview

The FileMaker Backend now includes comprehensive prompt logging functionality that allows users to see exactly what prompts are being sent to AI APIs during the automated generation processes. This feature is essential for prompt engineering, debugging, and understanding how the AI is being instructed to generate content.

## What Gets Logged

### 1. Stills Description Generation
- **Location**: `jobs/stills_autolog_05_generate_description.py`
- **Target Field**: `AI_DevConsole` in the Stills layout
- **Content**: 
  - Prompt template used (AF/LF specific)
  - Fully formatted prompt with all dynamic fields populated
  - User-provided AI_Prompt content
  - Metadata and existing description context

### 2. Footage Description Generation
- **Location**: `jobs/footage_autolog_06_generate_description.py`
- **Target Field**: `AI_DevConsole` in the FOOTAGE layout
- **Content**:
  - Prompt template used (AF/LF specific)
  - Fully formatted prompt with frame data CSV
  - Audio status information (silent/with audio)
  - Metadata and duration context

### 3. Frame Caption Generation
- **Location**: `jobs/frames_generate_captions.py`
- **Target Field**: `AI_DevConsole` in the parent FOOTAGE record (not individual frame records)
- **Content**:
  - Fully formatted prompt with metadata context
  - **Important**: Only logged once per footage item, not per frame (prevents duplicates)
  - **Coexistence**: Can coexist with video description prompts in the same console field

## Implementation Details

### Logging Format
All prompt logs follow this consistent format:
```
[2024-01-15 14:30:22] AI Prompt Engineering - [Type] Generation
[Complete formatted prompt with all dynamic fields populated]
```

### Duplicate Prevention
For frame caption generation, the system checks if a prompt has already been logged for the footage item to prevent duplicate entries when processing multiple frames in parallel.

### Error Handling
- All prompt logging operations are wrapped in try-catch blocks
- Failures to log prompts don't interrupt the main AI generation process
- Warning messages are printed to console if logging fails

## Benefits for Users

### 1. Prompt Engineering
- **Visibility**: See exactly what prompts are being used
- **Iteration**: Understand how prompt changes affect AI output
- **Debugging**: Identify issues with prompt formatting or context

### 2. Quality Assurance
- **Consistency**: Verify that the right prompts are being used for each content type
- **Context**: Understand what information the AI has access to
- **Validation**: Ensure metadata and user prompts are being properly incorporated

### 3. Development Support
- **Testing**: Verify prompt changes before deployment
- **Documentation**: Maintain a record of prompt evolution
- **Collaboration**: Share prompt strategies with team members

## Technical Implementation

### Functions Added
- `write_to_dev_console()` - Standard console logging for stills and footage
- `write_to_footage_dev_console()` - Specialized logging for frame captions
- `get_footage_dev_console()` - Retrieves current console content for duplicate checking

### Integration Points
- **Stills**: Integrated into `process_single_item()` function
- **Footage**: Integrated into `generate_video_description()` function  
- **Frames**: Integrated into `generate_caption()` function with duplicate prevention

### FileMaker Field Usage
- Uses existing `AI_DevConsole` fields in both Stills and FOOTAGE layouts
- **Appends** new entries with timestamps (does not overwrite existing content)
- Preserves existing console content from previous operations
- Multiple prompt logs can coexist in the same console field

## Example Log Entries

### Stills Description
```
[2024-01-15 14:30:22] AI Prompt Engineering - Description Generation
Please generate a description for this image.

The context is a database entry for a documentary production about the American reconstruction era through to the Great Migration (1865-1920s).

Focus on historical significance and visual details.

Keep the description to 2 sentences MAXIMUM please. Always include the date the image was taken as the last sentence. If there is no date provided, estimate a decade. Use Circa when estimating. Stay away from starting phrases like "This image is" or "The estimated date is". Avoid using unnecessary adjectives or editorial descriptions of the historical period.

For the description, use natural date formatting like "January 1, 2020" or "Circa 2020" or "Circa January 2020" if only partial information is known.

Finally, all the information that we have from the source archive for this image follows at the end of this prompt. Please utilize this information in your description as it is a good starting point and known to be accurate, but exclude any copyright info or identification numbers.

Return your answer as a JSON object with exactly these two fields:
- `description`: [Your 2-sentence description with natural date formatting at the end]
- `date`: [The date in structured format: YYYY/MM/DD, or YYYY/MM, or just YYYY. If no date available, return an empty string.]

Archive information:
Photograph of workers constructing a railroad bridge, circa 1870s. Original caption: "Railroad construction crew at work on bridge spanning river."

Existing description: 
```

### Frame Caption
```
[2024-01-15 14:30:22] AI Prompt Engineering - Frame Caption Generation
You are an assistant editor expert in cataloging live footage. You'll be captioning a single frame from a longer video file. Generate a vivid, precise caption. Describe people, setting, action, objects, and shot type (wide, medium, close, aerial). Skip phrases like "this image shows" or "the frame depicts." Information below is known to be true and should be the basis for your description:

Focus on historical significance and visual details.

IMPORTANT: Use the existing metadata to identify specific people, places, and historical context. If the metadata identifies a specific entity or person, use their name in the caption instead of generic descriptions.

Use this information for context:
- Metadata: Historical footage of civil rights march, 1963. Original source: National Archives.
```

## Future Enhancements

### Potential Improvements
1. **Prompt Versioning**: Track prompt template versions and changes
2. **Performance Metrics**: Log AI response times and token usage
3. **Quality Scoring**: Include prompt effectiveness metrics
4. **A/B Testing**: Support for comparing different prompt strategies

### Configuration Options
1. **Logging Levels**: Enable/disable prompt logging per workflow
2. **Content Filtering**: Option to exclude sensitive information from logs
3. **Retention Policies**: Automatic cleanup of old prompt logs

## Troubleshooting

### Common Issues
1. **Missing Logs**: Check if `AI_DevConsole` field exists in FileMaker layouts
2. **Duplicate Entries**: Verify duplicate prevention logic is working
3. **Permission Errors**: Ensure proper FileMaker API access

### Debug Mode
Enable debug mode to see detailed logging information:
```bash
export AUTOLOG_DEBUG=true
```

## Conclusion

The prompt engineering visibility feature provides unprecedented transparency into the AI generation process, enabling better prompt optimization, quality assurance, and collaborative development. Users can now see exactly how their AI_Prompt content and metadata are being used to generate descriptions and captions. 