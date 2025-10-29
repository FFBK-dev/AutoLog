# Supported URL Sources

This document lists all website sources currently supported by the FileMaker Backend URL scraping system.

## Currently Implemented Sources

### Academic Institutions

#### Temple University Digital Library
- **Domain**: `digital.library.temple.edu`
- **Source Type**: `temple`
- **Scraper Method**: `_scrape_temple()`
- **Specializations**:
  - CONTENTdm backend compatibility
  - Blockson Afro-American Collection support
  - Metadata table extraction
  - JSON data parsing from JavaScript
  - Institution-specific title cleaning
- **Example URL**: `https://digital.library.temple.edu/digital/collection/p16002coll7/id/60/rec/107`
- **Special Features**:
  - Enhanced quality evaluation with Temple-specific keywords
  - Fallback content extraction from multiple selectors
  - Support for both table and definition list metadata formats

### Digital Collection Platforms

#### CONTENTdm Sites
- **Domain Patterns**: `contentdm`, `digitalcollections`
- **Source Type**: `contentdm`
- **Scraper Method**: `_scrape_contentdm()`
- **Specializations**:
  - JavaScript JSON data extraction (`window.__INITIAL_STATE__`)
  - Item metadata and collection information
  - Field-based metadata structure
- **Example Domains**: Sites using CONTENTdm platform
- **Special Features**:
  - JSON string unescaping
  - Structured field extraction
  - Collection hierarchy support

### Museums & Cultural Institutions

#### The Valentine Museum
- **Domains**: `valentine.rediscoverysoftware.com`, `thevalentine.org`
- **Source Type**: `valentine`
- **Scraper Method**: `_scrape_valentine()`
- **Platform**: Re:discovery Collections Management System
- **Specializations**:
  - Selenium-based JavaScript rendering (required for dynamic content)
  - Re:discovery specific element extraction (`#redtitle`, `#robjres`, `#redboxARH`)
  - Metadata table parsing
  - Archive number extraction
  - Collection hierarchy capture
- **Example URL**: `https://valentine.rediscoverysoftware.com/MADetailB.aspx?rID=PHC0015/-0005.0092#V.86.153.278&db=biblio&dir=VALARCH`
- **Special Features**:
  - Enhanced quality evaluation with Valentine-specific keywords
  - Handles dynamic JavaScript-loaded content
  - Extracts Richmond Chamber of Commerce photograph metadata
  - Summary Note field mapped to Description
  - Support for archival numbering system
- **Typical Metadata Fields**:
  - Title, Item Number, Collection Number, File Unit Number
  - Physical Description, Creator, Creator Role, Dates
  - Summary Note (comprehensive descriptions)
  - Extent, Inscriptions/Marks, Citation format
  - Geographic Name, Genre-Form, Archive Number

### Government Institutions

#### Library of Congress
- **Domain**: `loc.gov`
- **Source Type**: `loc`
- **Status**: Detected but uses general scraper
- **Notes**: Ready for specialized implementation if needed

#### New York Public Library
- **Domains**: `nypl.org`, `digitalcollections.nypl.org`
- **Source Type**: `nypl`
- **Status**: Detected but uses general scraper
- **Notes**: Ready for specialized implementation if needed

#### Internet Archive
- **Domain**: `archive.org`
- **Source Type**: `archive`
- **Status**: Detected but uses general scraper
- **Notes**: Ready for specialized implementation if needed

#### HarpWeek
- **Domain**: `harpweek.com`
- **Source Type**: `harpweek`
- **Status**: Detected but uses general scraper
- **Notes**: Historical newspaper content, ready for specialized implementation

### Generic Handlers

#### Archival Sites
- **Domain Patterns**: `library`, `archive`, `museum`, `digital`
- **Source Type**: `archival`
- **Scraper Method**: `_scrape_general()` with enhanced structured metadata extraction
- **Specializations**:
  - Definition list extraction (dl/dt/dd)
  - Metadata table parsing
  - JSON-LD structured data
  - Meta tag extraction
- **Purpose**: Fallback for academic and cultural institutions

#### General Sites
- **Domain Pattern**: All others
- **Source Type**: `generic`
- **Scraper Method**: `_scrape_general()`
- **Purpose**: Basic content extraction for unknown sites

## Enhancement Priority List

Based on common sources in FileMaker records, consider implementing specialized scrapers for:

### High Priority
1. **Yale University** - Academic digital collections
2. **Harvard University** - Digital repositories
3. **Smithsonian Institution** - Museum collections
4. **National Archives** - Government records

### Medium Priority
1. **Getty Research Institute** - Art and cultural materials
2. **Boston Public Library** - Regional collections
3. **Princeton University** - Academic materials
4. **Columbia University** - Digital collections

### Low Priority
1. Regional historical societies
2. State archives
3. Municipal libraries
4. Specialized subject repositories

## Quality Evaluation Enhancements

### Current Institution-Specific Keywords

#### The Valentine Museum
```python
valentine_keywords = [
    "valentine museum", "the valentine", "richmond", "virginia",
    "phil flournoy", "flournoy", "richmond chamber of commerce",
    "photograph collection", "tobacco", "archive no", "item nbr",
    "collection nbr", "phys desc", "circa", "stamped", "verso"
]
```

#### Temple University
```python
temple_keywords = [
    "temple university", "temple libraries", "blockson", "afro-american",
    "philadelphia", "pennsylvania", "delaware valley", "scrc",
    "special collections", "research center", "manuscript", "oral history",
    "digital collections", "finding aid", "archival", "university archives"
]
```

#### Academic Institutions (General)
```python
academic_keywords = [
    "library", "university", "college", "institution", "archives",
    "special collections", "rare books", "manuscripts", "digitized",
    "repository", "finding aids", "catalog", "collection", "holdings"
]
```

### Scoring Bonuses
- **Valentine Museum**: Up to 6 points (2x multiplier)
- **Temple University**: Up to 6 points (2x multiplier)
- **Academic Institutions**: Up to 2 points
- **Historical Content**: Up to 3 points
- **Year Matches**: 2 points per year found

## Common Metadata Patterns

### Academic Digital Libraries
- **Table-based metadata** (most common)
- **Dublin Core meta tags**
- **Repository and collection information**
- **Rights and access statements**

### Museum Collections
- **Definition lists** for artwork details
- **Provenance information**
- **Media and dimension specifications**
- **Accession numbers and catalog data**

### Government Archives
- **Formal metadata schemas**
- **Classification systems**
- **Agency and record group information**
- **Access restrictions and permissions**

## Testing Coverage

### Verified URLs
- ✅ The Valentine Museum (Re:discovery platform)
- ✅ Temple University Digital Library
- ✅ CONTENTdm-based sites
- ✅ Generic archival sites (fallback)

### Recommended Test URLs for Future Sources
When implementing new sources, test with:
1. **Item detail pages** (primary target)
2. **Different collections** within the institution
3. **Various content types** (images, documents, audio, etc.)
4. **Different time periods** of content

## Integration Notes

### Workflow Integration
All sources automatically integrate with:
- `stills_autolog_04_scrape_url.py`
- `footage_autolog_04_scrape_url.py`
- Metadata quality evaluation system
- URL validation and testing

### Error Handling
Each source includes:
- Institution-specific error messages
- Graceful fallback to general scraper
- Timeout and connection error handling
- Comprehensive logging for debugging

## Future Enhancements

### Planned Features
1. **Rate limiting** for respectful scraping
2. **Caching** for frequently accessed sources
3. **Parallel processing** for batch operations
4. **Machine learning** metadata quality prediction

### Architecture Improvements
1. **Plugin system** for easier source addition
2. **Configuration files** for institution-specific settings
3. **Source-specific user agents** for better compatibility
4. **Automated testing** for all supported sources

## Maintenance

### Regular Tasks
1. **Test existing sources** quarterly for website changes
2. **Update domain patterns** as institutions change URLs
3. **Monitor quality scores** and adjust thresholds as needed
4. **Review extraction patterns** for improved metadata capture

### Documentation Updates
When adding new sources, update:
1. This document with source details
2. `URL_SCRAPING_ENHANCEMENT_GUIDE.md` with any new patterns
3. Test URLs and example outputs
4. Quality evaluation keyword lists 