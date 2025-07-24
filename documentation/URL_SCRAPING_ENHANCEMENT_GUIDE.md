# URL Scraping Enhancement Guide

## Overview

This guide provides step-by-step instructions for adding new website sources to the FileMaker Backend URL scraping system. The scraping system is designed to be **additive** - new sources are always added without removing or breaking existing functionality.

## System Architecture

The URL scraping system consists of these key components:

### Core Files
- **`utils/url_scraper.py`** - Main scraping engine with specialized handlers
- **`utils/url_validator.py`** - URL validation and construction utilities
- **`utils/local_metadata_evaluator.py`** - Metadata quality evaluation

### Integration Points
- **`jobs/stills_autolog_04_scrape_url.py`** - Stills workflow scraping step
- **`jobs/footage_autolog_04_scrape_url.py`** - Footage workflow scraping step
- **Both workflows call**: `scrape_url_enhanced()` and `evaluate_metadata_quality()`

## Adding New Sources: Step-by-Step Process

### Step 1: Analyze the New Source

Before coding, analyze the target website:

1. **Visit the URL** and inspect the page structure
2. **View page source** to identify:
   - Metadata tables (table/tr/td structure)
   - Definition lists (dl/dt/dd structure)
   - JSON data in script tags
   - Meta tags with useful information
   - Content areas with metadata
3. **Check for JavaScript-rendered content** (view with developer tools)
4. **Identify unique domain patterns** for detection

### Step 2: Update Website Type Detection

**File**: `utils/url_scraper.py`
**Method**: `_detect_website_type(self, url)`

Add detection logic **BEFORE** the generic patterns:

```python
def _detect_website_type(self, url):
    """Detect the type of website for specialized handling."""
    domain = urlparse(url).netloc.lower()
    
    # NEW SOURCE - Add before existing sources
    if 'your-new-domain.edu' in domain:
        return "your_source_name"
    
    # Temple University Digital Library
    if 'digital.library.temple.edu' in domain:
        return "temple"
    
    # ... existing sources ...
```

**Important**: 
- Use descriptive source names (e.g., "temple", "yale", "harvard")
- Add new sources **at the top** to ensure they're checked first
- Never modify existing detection logic

### Step 3: Add Specialized Scraping Method

**File**: `utils/url_scraper.py`
**Location**: After existing `_scrape_*` methods, before `_scrape_general`

Create a new method following the naming pattern:

```python
def _scrape_your_source_name(self, url):
    """Specialized scraper for Your Institution Name."""
    try:
        response = requests.get(url, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        
        metadata_parts = []
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()
        
        # 1. Extract title (clean institution-specific patterns)
        title = soup.find('title')
        if title:
            title_text = title.get_text(strip=True)
            # Clean up institution-specific title patterns
            title_text = re.sub(r'\s*\|\s*Your Institution.*$', '', title_text)
            if title_text:
                metadata_parts.append(f"Title: {title_text}")
        
        # 2. Look for metadata tables
        tables = soup.find_all('table')
        for table in tables:
            if any(keyword in table.get_text().lower() for keyword in ['title', 'creator', 'date']):
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True).rstrip(':')
                        value = cells[1].get_text(strip=True)
                        if key and value and len(value) > 2:
                            metadata_parts.append(f"{key}: {value}")
        
        # 3. Look for definition lists
        dl_elements = soup.find_all('dl')
        for dl in dl_elements:
            dt_elements = dl.find_all('dt')
            dd_elements = dl.find_all('dd')
            for i, dt in enumerate(dt_elements):
                if i < len(dd_elements):
                    key = dt.get_text(strip=True).rstrip(':')
                    value = dd_elements[i].get_text(strip=True)
                    if key and value and len(value) > 2:
                        metadata_parts.append(f"{key}: {value}")
        
        # 4. Look for institution-specific patterns
        # Add custom parsing logic here based on your analysis
        
        # 5. Look for JSON data (if applicable)
        json_patterns = [
            r'window\.__INITIAL_STATE__ = JSON\.parse\("(.*?)"\);',
            r'var itemData = ({.*?});'
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, html_content, re.DOTALL)
            if match:
                try:
                    json_str = match.group(1)
                    if pattern.startswith('window'):
                        json_str = json_str.encode('utf-8').decode('unicode_escape')
                    data = json.loads(json_str)
                    # Extract metadata from JSON structure
                    # Add custom JSON parsing logic here
                    break
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
        
        # 6. Look for meta tags
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            name = meta.get('name') or meta.get('property', '')
            content = meta.get('content', '')
            if name and content and len(content) > 10:
                if any(keyword in name.lower() for keyword in ['description', 'subject', 'creator']):
                    clean_name = name.replace('_', ' ').replace('-', ' ').title()
                    metadata_parts.append(f"{clean_name}: {content}")
        
        # Return results
        if metadata_parts:
            return "\n\n".join(metadata_parts)
        
        # Fallback: extract general content
        content_selectors = [
            '.item-view', '.record-view', '.detail-view', '.metadata-view',
            '#main-content', '#content', 'main', 'article'
        ]
        
        for selector in content_selectors:
            elements = soup.select(selector)
            for element in elements:
                text = element.get_text(separator='\n', strip=True)
                if text and len(text) > 100:
                    lines = text.split('\n')
                    clean_lines = [line.strip() for line in lines if line.strip() and len(line.strip()) > 3]
                    if clean_lines:
                        return '\n'.join(clean_lines[:20])
                    break
        
        return None
        
    except Exception as e:
        print(f"  -> Your Institution scraping error: {e}")
        return None
```

### Step 4: Add Source to Main Scraping Logic

**File**: `utils/url_scraper.py`
**Method**: `scrape_url(self, url, client=None)`

Add your source **BEFORE** existing sources in the specialized scraper section:

```python
# Try specialized scraper first
if website_type == "your_source_name":
    content = self._scrape_your_source_name(url)
    if content:
        print(f"  -> Your Institution extraction successful ({len(content)} chars)")
        return content
elif website_type == "temple":
    content = self._scrape_temple(url)
    if content:
        print(f"  -> Temple University extraction successful ({len(content)} chars)")
        return content
# ... existing sources continue ...
```

### Step 5: Enhance Metadata Quality Evaluation (Optional)

**File**: `utils/url_scraper.py`
**Method**: `evaluate_metadata_quality(self, content)`

If your institution has specific valuable keywords, add them:

```python
# Check for Your Institution and academic keywords
your_institution_keywords = [
    "your university", "your library", "your collection",
    "institution-specific terms", "special collection names"
]

your_institution_count = sum(1 for keyword in your_institution_keywords if keyword in text_lower)
your_institution_bonus = min(your_institution_count * 2, 6)  # Higher bonus for institutional content

# Update total score calculation
total_score = useful_count + year_bonus + archival_bonus + temple_bonus + academic_bonus + your_institution_bonus

# Add special evaluation case
elif your_institution_bonus > 0 and total_score >= 2:
    return {
        "sufficient": True, 
        "score": total_score, 
        "reason": f"Your Institution content with good metadata (score: {total_score})"
    }
```

### Step 6: Test the New Source

Create a test script in `/temp/`:

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from utils.url_scraper import scrape_url_enhanced, evaluate_metadata_quality

def test_new_source():
    test_url = "https://your-institution.edu/path/to/item"
    
    print(f"🧪 Testing Your Institution URL scraping...")
    print(f"URL: {test_url}")
    
    try:
        scraped_content = scrape_url_enhanced(test_url, timeout=30)
        
        if scraped_content:
            print(f"✅ Scraping successful!")
            print(f"Content length: {len(scraped_content)} characters")
            print("\n=== SCRAPED CONTENT ===")
            print(scraped_content)
            print("=== END CONTENT ===\n")
            
            quality = evaluate_metadata_quality(scraped_content)
            print(f"📊 Metadata Quality Evaluation:")
            print(f"  Score: {quality['score']}")
            print(f"  Sufficient: {'✅ YES' if quality['sufficient'] else '❌ NO'}")
            print(f"  Reason: {quality['reason']}")
        else:
            print(f"❌ Scraping failed - no content extracted")
            
    except Exception as e:
        print(f"❌ Error during scraping: {e}")

if __name__ == "__main__":
    test_new_source()
```

Run the test:
```bash
python temp/test_your_source.py
```

## Important Guidelines

### ✅ DO:
- **Always add new sources additively** (never remove existing functionality)
- **Place new detection logic BEFORE existing patterns** to ensure priority
- **Use descriptive, institution-specific method names**
- **Include comprehensive error handling**
- **Add detailed comments explaining institution-specific parsing**
- **Test thoroughly with multiple URLs from the institution**
- **Clean up test files after verification**

### ❌ DON'T:
- **Never modify existing scraping methods** for other institutions
- **Don't change the order of existing detection logic**
- **Don't remove fallback mechanisms**
- **Don't hardcode specific URLs** (use domain patterns)
- **Don't leave test files in the repository**

## Integration Testing

After adding a new source, verify integration:

1. **Test with existing sources** to ensure no regression
2. **Test the new source** with multiple URLs
3. **Verify metadata quality evaluation** works correctly
4. **Check workflow integration** (run actual stills/footage scraping jobs)

## Common Patterns by Institution Type

### Academic Libraries
- Often use **table-based metadata display**
- May have **Dublin Core meta tags**
- Usually include **repository information**
- Common fields: Title, Creator, Date, Subject, Rights

### Museums
- Often use **structured definition lists**
- May have **rich media metadata**
- Include **provenance information**
- Common fields: Artist, Medium, Dimensions, Accession Number

### Government Archives
- Often use **formal metadata schemas**
- May have **classification information**
- Include **access restrictions**
- Common fields: Agency, Record Group, Classification, Date Range

### Digital Libraries
- Often use **CONTENTdm or similar systems**
- May have **JavaScript-rendered content**
- Include **collection hierarchy**
- Common fields: Collection, Item ID, Digital Format, Rights

## Troubleshooting

### Low Quality Scores
- Add institution-specific keywords to evaluation
- Check if content is being properly extracted
- Verify HTML structure matches parsing logic

### No Content Extracted
- Check if website uses JavaScript rendering (try Selenium fallback)
- Verify domain detection is working
- Check for anti-scraping measures (rate limiting, blocking)

### Parsing Errors
- Add more specific error handling
- Check for unusual HTML structures
- Verify JSON parsing logic if applicable

## Documentation Requirements

When adding a new source, update this document with:
- Institution name and domain pattern
- Specific parsing challenges encountered
- Example URLs for testing
- Any special considerations or requirements

## Example Implementations

See existing implementations for reference:
- **Temple University**: `_scrape_temple()` - Academic digital library
- **CONTENTdm**: `_scrape_contentdm()` - Digital collection platform
- **General**: `_scrape_general()` - Fallback for unknown sites

Each implementation demonstrates different parsing strategies and can serve as templates for similar institution types. 