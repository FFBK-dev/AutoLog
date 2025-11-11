# AF (Archival Footage) URL Research & Construction Guide

## Overview
Research findings for adding intelligent URL construction for archival footage from multiple sources.

**Research Date**: November 11, 2025  
**Location**: `/Volumes/6 E2E/11 Footage_Audio/1 OFFLINE`

---

## Archive File Naming Patterns

### 1. Getty Images ✅ (ALREADY SUPPORTED)
**Naming Pattern**: `GettyImages-[ID].mov`
- Example: `GettyImages-482875966.mov`
- Archival ID: `482875966`

**URL Pattern**: `https://www.gettyimages.com/detail/video/[ID]`
- Example: `https://www.gettyimages.com/detail/video/482875966`

**Current Status**: Already has cleaning logic in `url_validator.py` (lines 32-62)
- Removes `GettyImages-` prefix
- Removes suffixes like `-640_adpp`, `-640`, etc.

**Action Required**: ✅ Already in URLs table, just verify URL root is correct

---

### 2. Critical Past 🔍 (NEW)
**Naming Pattern**: `[ID]----1080-24p-Screening.mov`
- Example: `65675076731----1080-24p-Screening.mov`
- Archival ID: `65675076731` (everything before first `----`)

**URL Pattern** (NEEDS VERIFICATION):
- Option A: `https://www.criticalpast.com/video/[ID]`
- Option B: `https://criticalpast.com/clip/[ID]`

**Cleaning Logic Needed**:
```python
# Remove everything after ----
if "----" in filename:
    archival_id = filename.split("----")[0]
```

**Action Required**: 
1. ⚠️ VERIFY actual URL structure on criticalpast.com
2. Add to `url_validator.py` cleaning logic
3. Add to FileMaker URLs table

---

### 3. Pond5 🔍 (NEW)
**Naming Pattern**: `[ID]-[description].mp4`
- Example: `236704593-water-mosquitos-sliding-and-ju.mp4`
- Archival ID: `236704593` (everything before first `-`)

**URL Pattern** (NEEDS VERIFICATION):
- Most likely: `https://www.pond5.com/stock-footage/item/[ID]`
- Example: `https://www.pond5.com/stock-footage/item/236704593`

**Cleaning Logic Needed**:
```python
# Take only digits before first hyphen
if "-" in filename:
    archival_id = filename.split("-")[0]
```

**Action Required**:
1. ⚠️ VERIFY actual URL structure on pond5.com
2. Add to `url_validator.py` cleaning logic
3. Add to FileMaker URLs table

---

### 4. ArtGrid 🔍 (NEW)
**Naming Pattern**: `[ID]_[Description]_By_[Artist]_Artlist_HD.mp4`
- Example: `557465_Plants_Field_Weeds_Blur_By_Ami_Bornstein_Artlist_HD.mp4`
- Archival ID: `557465` (everything before first `_`)

**URL Pattern** (NEEDS VERIFICATION):
- Possible: `https://artgrid.io/clip/[ID]`
- Possible: `https://www.artgrid.io/stock-footage/[ID]`
- Example: `https://artgrid.io/clip/557465`

**Cleaning Logic Needed**:
```python
# Take only digits before first underscore
if "_" in filename:
    archival_id = filename.split("_")[0]
```

**Action Required**:
1. ⚠️ VERIFY actual URL structure on artgrid.io
2. Add to `url_validator.py` cleaning logic
3. Add to FileMaker URLs table

---

### 5. FilmSupply 🔍 (NEW)
**Naming Pattern**: `[Creator]-[description]-[ID]-filmsupply.mov`
- Example: `Marco Schott-foggy-field-59522-filmsupply.mov`
- Archival ID: `59522` (number before `-filmsupply`)

**URL Pattern** (NEEDS VERIFICATION):
- Possible: `https://www.filmsupply.com/footage/[ID]`
- Possible: `https://filmsupply.com/catalog/footage/[ID]`
- Example: `https://www.filmsupply.com/footage/59522`

**Cleaning Logic Needed**:
```python
# Extract ID before '-filmsupply'
if "-filmsupply" in filename.lower():
    # Get portion before '-filmsupply'
    parts = filename.lower().split("-filmsupply")[0].split("-")
    # ID is likely the last numeric part
    archival_id = parts[-1]
```

**Action Required**:
1. ⚠️ VERIFY actual URL structure on filmsupply.com
2. Add to `url_validator.py` cleaning logic (complex pattern)
3. Add to FileMaker URLs table

---

### 6. LOC (Library of Congress) 🔍 (NEW)
**Naming Pattern**: `service-mbrs-ntscrm-[ID]-[ID].mov`
- Example: `service-mbrs-ntscrm-00060780-00060780.mov`
- Archival ID: `00060780` (either occurrence of the ID)

**URL Pattern** (NEEDS VERIFICATION):
- Most likely: `https://www.loc.gov/item/[ID]`
- Possible: `https://catalog.loc.gov/vwebv/search?searchArg=[ID]`
- Example: `https://www.loc.gov/item/00060780`

**Cleaning Logic Needed**:
```python
# Extract ID from LOC pattern
if "service-mbrs-ntscrm-" in filename.lower():
    # Get part after the third hyphen
    parts = filename.split("-")
    if len(parts) >= 4:
        archival_id = parts[3]  # Fourth part
```

**Action Required**:
1. ⚠️ VERIFY actual URL structure on loc.gov
2. Add to `url_validator.py` cleaning logic
3. Add to FileMaker URLs table

---

### 7. UNC (University of North Carolina) 🔍 (NEW)
**Naming Pattern**: `[CollectionID]_[FileID]_[SequenceID].mp4`
- Example: `04773_F0012_0001.mp4`
- Archival ID: `04773_F0012` or full `04773_F0012_0001`

**URL Pattern** (NEEDS RESEARCH):
- Possible: `https://library.unc.edu/wilson/shc/finding-aids/[ID]`
- Possible: `https://finding-aids.lib.unc.edu/[CollectionID]`
- ⚠️ UNC Southern Historical Collection - complex finding aid system

**Cleaning Logic Needed**:
```python
# UNC pattern is complex - may need collection ID + file ID
# Pattern: XXXXX_FXXXX_XXXX
if filename.count("_") >= 2:
    parts = filename.split("_")
    collection_id = parts[0]
    file_id = parts[1]
    archival_id = f"{collection_id}_{file_id}"
```

**Action Required**:
1. ⚠️ RESEARCH UNC Southern Historical Collection online catalog structure
2. Determine if URL construction is feasible
3. May not have direct video URLs (finding aids only)

---

### 8. Smithsonian 🔍 (NEW)
**Status**: No files found yet in directory

**URL Pattern** (KNOWN):
- Smithsonian uses complex digital asset management
- Format: `https://ids.si.edu/ids/manifest/[ID]`
- Or: `https://www.si.edu/object/[category]:[ID]`

**Action Required**:
1. Wait for actual files to arrive
2. Examine filename pattern when available
3. Research Smithsonian digital asset URLs

---

### 9. Hagley Museum 🔍 (NEW)
**Status**: No complete files found yet (only .crdownload)

**URL Pattern** (KNOWN):
- Hagley Digital Archives
- Format: `https://digital.hagley.org/[ID]`
- Example: `https://digital.hagley.org/item/[item_id]`

**Action Required**:
1. Wait for actual files to arrive
2. Examine filename pattern when available
3. Research Hagley digital archive URL structure

---

### 10. JR (Custom Library) ❌ (NO URL)
**Naming Pattern**: `JR[ID].mov`
- Example: `JR0659.mov`
- This appears to be custom library footage (no public URL)

**Action Required**: None - no URL construction needed

---

### 11. Hunter Nichols (Custom Filmmaker) ❌ (NO URL)
**Status**: Custom filmmaker footage - no public archive

**Action Required**: None - no URL construction needed

---

### 12. CCWP ❓ (UNKNOWN)
**Status**: Mostly image files, need more info

**Action Required**: Research what CCWP stands for

---

### 13. Public Domain (Generic) ❌ (NO URL)
**Status**: Generic public domain sources - no single URL pattern

**Action Required**: None - too varied for systematic URL construction

---

## Implementation Priority

### HIGH PRIORITY (Clear Patterns, Major Archives)
1. ✅ **Getty Images** - Already supported
2. 🔥 **Pond5** - Clear ID pattern, major stock footage site
3. 🔥 **Critical Past** - Clear ID pattern, historical footage specialist
4. 🔥 **ArtGrid** - Clear ID pattern, popular stock footage

### MEDIUM PRIORITY (Need URL Verification)
5. 📋 **FilmSupply** - More complex pattern, need URL structure
6. 📋 **LOC** - Clear ID, need URL format confirmation

### LOW PRIORITY (Research Required)
7. ❓ **UNC** - Complex academic archive system
8. ❓ **Smithsonian** - Waiting for files
9. ❓ **Hagley Museum** - Waiting for files

### NO URL NEEDED
10. ❌ **JR** - Custom library
11. ❌ **Hunter Nichols** - Custom filmmaker
12. ❌ **Public Domain** - Too varied

---

## FileMaker URLs Table Structure

Based on existing implementation, the URLs table should have:

| Field | Type | Example |
|-------|------|---------|
| Archive | Text | "Getty Images" |
| URL Root | Text | "https://www.gettyimages.com/detail/video/" |

### Proposed New Entries

```
Archive: Critical Past
URL Root: https://www.criticalpast.com/video/

Archive: Pond5
URL Root: https://www.pond5.com/stock-footage/item/

Archive: ArtGrid
URL Root: https://artgrid.io/clip/

Archive: FilmSupply
URL Root: https://www.filmsupply.com/footage/

Archive: LOC
URL Root: https://www.loc.gov/item/
```

---

## Code Changes Required

### 1. Update `utils/url_validator.py` - Add Cleaning Logic

```python
def clean_archival_id_for_url(archival_id, source):
    """Clean archival ID by removing source-specific prefixes and suffixes."""
    if not archival_id:
        return archival_id
    
    cleaned_id = archival_id.strip()
    
    # Getty Images (EXISTING)
    if source and "getty" in source.lower():
        # ... existing Getty logic ...
    
    # Critical Past (NEW)
    elif source and "critical" in source.lower():
        # Remove ---- and everything after
        if "----" in cleaned_id:
            cleaned_id = cleaned_id.split("----")[0]
    
    # Pond5 (NEW)
    elif source and "pond5" in source.lower():
        # Take only the ID before first hyphen
        if "-" in cleaned_id:
            cleaned_id = cleaned_id.split("-")[0]
    
    # ArtGrid (NEW)
    elif source and "artgrid" in source.lower():
        # Take only the ID before first underscore
        if "_" in cleaned_id:
            cleaned_id = cleaned_id.split("_")[0]
    
    # FilmSupply (NEW)
    elif source and "filmsupply" in source.lower():
        # Extract ID before '-filmsupply'
        if "-filmsupply" in cleaned_id.lower():
            parts = cleaned_id.lower().split("-filmsupply")[0].split("-")
            # Last numeric part is the ID
            for part in reversed(parts):
                if part.isdigit():
                    cleaned_id = part
                    break
    
    # LOC (NEW)
    elif source and ("loc" in source.lower() or "library of congress" in source.lower()):
        # Extract from service-mbrs-ntscrm-[ID]-[ID] pattern
        if "service-mbrs-ntscrm-" in cleaned_id.lower():
            parts = cleaned_id.split("-")
            if len(parts) >= 4:
                cleaned_id = parts[3]
    
    return cleaned_id
```

### 2. Update FileMaker URLs Table

Add entries for:
- Critical Past
- Pond5
- ArtGrid
- FilmSupply  
- LOC

### 3. Test with Real Files

Create test script to verify URL construction for each archive.

---

## Next Steps

### Immediate Actions Needed:
1. **Manual URL Verification** - Visit each site with sample IDs to confirm URL patterns:
   - [ ] Critical Past: Test `https://www.criticalpast.com/video/65675076731`
   - [ ] Pond5: Test `https://www.pond5.com/stock-footage/item/236704593`
   - [ ] ArtGrid: Test `https://artgrid.io/clip/557465`
   - [ ] FilmSupply: Test `https://www.filmsupply.com/footage/59522`
   - [ ] LOC: Test `https://www.loc.gov/item/00060780`

2. **Update Code** - Add cleaning logic to `url_validator.py`

3. **Update FileMaker** - Add entries to URLs layout/table

4. **Testing** - Run test with sample AF files to verify URL construction

---

## Research Notes

### Questions to Resolve:
- **Critical Past**: Is it `/video/` or `/clip/` in the URL?
- **Pond5**: Is `/stock-footage/item/` the correct path?
- **ArtGrid**: Is it `artgrid.io` or `www.artgrid.io`?
- **FilmSupply**: What's the exact URL structure?
- **LOC**: Does `/item/` work for all video content?
- **UNC**: Do they have direct video URLs or just finding aids?

### Follow-up Research:
- Test actual URLs with sample IDs
- Check if URLs require authentication
- Verify URL stability (do they change?)
- Check if URLs work for embedded video or just info pages

---

**Status**: 🔄 Research Phase Complete - Ready for URL Verification

**Next Phase**: Manual URL testing with sample IDs from each archive

