# FileMaker Data API Permissions Setup

## Problem

The `REVERSE_IMAGE_SEARCH` layout returns 500 errors when accessed via Data API, indicating permission restrictions.

## Solution: Enable Data API Access for Layout

### Step 1: Open FileMaker Pro

1. Open your database: **"Emancipation to Exodus"**
2. Go to **File → Manage → Layouts**

### Step 2: Configure Layout Permissions

#### Option A: Enable for Specific Privilege Set (Recommended)

1. Go to **File → Manage → Security**
2. Find the privilege set used by your API user (likely "Background" based on your config)
3. Click **Edit** on that privilege set
4. Go to **Records** tab
5. For the `REVERSE_IMAGE_SEARCH` table:
   - **View**: Set to "Yes" or "All"
   - **Edit**: Set to "Yes" or "All"
   - **Create**: Set to "Yes" (if creating records via API)
   - **Delete**: Set to "No" (unless needed)

6. Go to **Layouts** tab
7. Find `REVERSE_IMAGE_SEARCH` layout
8. Set **Records via this layout**: "Modifiable" or "View Only"

9. **IMPORTANT**: Check **"Accessible via FileMaker Data API"** checkbox
   - This is often the missing piece!

10. Click **OK** to save

#### Option B: Enable for All Users (Less Secure)

1. **File → Manage → Security**
2. Select **[Full Access]** privilege set (or the one your API uses)
3. Ensure Data API access is enabled
4. Save

### Step 3: Verify Table Occurrence

The layout must be based on a table occurrence that the API user can access:

1. **File → Manage → Database → Relationships**
2. Find the `REVERSE_IMAGE_SEARCH` table occurrence
3. Note its name (might be different from the layout name)
4. In **Manage → Security**, verify the privilege set can access this table

### Step 4: Enable Data API for Layout

This is crucial and often overlooked:

1. **File → Manage → Layouts**
2. Select `REVERSE_IMAGE_SEARCH` layout
3. Click **Edit Layout**
4. **Layouts → Layout Setup** (or double-click layout name)
5. Go to **General** tab
6. **Check**: "Include in Data API"
7. **Save** and exit layout mode

### Step 5: Restart FileMaker Server (if needed)

If using FileMaker Server:
1. Admin Console → Database Server
2. Stop database
3. Start database
4. This refreshes API permissions

### Step 6: Test Access

```bash
# Test if layout is now accessible
curl -X POST "https://10.0.222.144/fmi/data/vLatest/databases/Emancipation%20to%20Exodus/sessions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic <base64_credentials>" \
  -d '{}' \
  --insecure

# Get token, then test layout access
curl -X GET "https://10.0.222.144/fmi/data/vLatest/databases/Emancipation%20to%20Exodus/layouts/REVERSE_IMAGE_SEARCH/records?_limit=1" \
  -H "Authorization: Bearer <token>" \
  --insecure
```

## Common Issues

### Issue: "102 - Field is missing"
**Solution**: Layout is based on wrong table occurrence, or fields are not accessible via this layout

### Issue: "500 - Server Error"
**Solution**: Layout not enabled for Data API, or privilege set doesn't have access

### Issue: "401 - Unauthorized"
**Solution**: API user credentials don't have proper privilege set assigned

### Issue: Layout works in FileMaker Pro but not via API
**Solution**: "Include in Data API" checkbox not enabled in Layout Setup

## Security Best Practices

### Create Dedicated API Privilege Set

Instead of using [Full Access], create a specific privilege set for API:

1. **File → Manage → Security → Privilege Sets → New**
2. Name: "Data API Access"
3. **Data Access and Design**:
   - Records: Custom (select specific tables)
   - Layouts: Custom (select specific layouts)
   - Value Lists: View only
   - Scripts: Execute only (select specific scripts)

4. **Extended Privileges**:
   - ✅ Check "Access via FileMaker Data API [fmrest]"
   - ❌ Uncheck other extended privileges unless needed

5. **Available menu commands**: Minimum

6. **Assign to API user** ("Background" in your case)

### Minimal Permissions for REVERSE_IMAGE_SEARCH

```
Table: REVERSE_IMAGE_SEARCH
- View: Yes
- Edit: Yes (for updating IMAGE_CONTAINER and EMBEDDING)
- Create: No (if users create via different method)
- Delete: No

Layout: REVERSE_IMAGE_SEARCH
- Records via this layout: Modifiable
- Include in Data API: ✓ Yes

Fields (via this layout):
- PATH: View only
- IMAGE_CONTAINER: Editable
- EMBEDDING: Editable
- MATCH COUNT: Editable
- MATCHES: Editable
```

## Alternative: Use Different Layout

If you can't modify REVERSE_IMAGE_SEARCH layout permissions:

1. Create a new layout: "REVERSE_IMAGE_SEARCH_API"
2. Base it on the same table
3. Include only necessary fields
4. Enable for Data API
5. Update Python scripts to use "REVERSE_IMAGE_SEARCH_API" instead

## Verification

After making changes, test with:

```bash
cd /Users/admin/Documents/Github/Filemaker-Backend
python3 jobs/ris_preprocess_image.py 184
```

If successful, you'll see:
```
✅ SUCCESS: Record 184 preprocessed
```

If still failing with 500 error, review:
1. Layout includes Data API checkbox
2. Privilege set has access to table and layout
3. API user assigned to correct privilege set
4. FileMaker Server restarted (if applicable)

