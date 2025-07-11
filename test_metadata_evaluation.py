#!/usr/bin/env python3
import sys
import json
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent))
import config

def test_metadata_evaluation():
    """Test the new OpenAI-powered metadata sufficiency evaluation."""
    print(f"🧪 TESTING METADATA SUFFICIENCY EVALUATION")
    print("=" * 60)
    
    # Setup OpenAI client
    try:
        import openai
        token = config.get_token()
        system_globals = config.get_system_globals(token)
        api_key = system_globals.get("SystemGlobals_AutoLog_OpenAI_API_Key")
        if not api_key:
            print("❌ OpenAI API Key not found")
            return
        client = openai.OpenAI(api_key=api_key)
        print(f"✅ OpenAI client created")
    except Exception as e:
        print(f"❌ Error setting up OpenAI: {e}")
        return
    
    # Import the function
    sys.path.append(str(Path(__file__).resolve().parent / "jobs"))
    from stills_autolog_04_scrape_url import is_metadata_sufficient
    
    # Test cases
    test_cases = [
        {
            "text": "One of hundreds of thousands of free digital items from The New York Public Library.",
            "expected": False,
            "description": "Generic NYPL boilerplate"
        },
        {
            "text": "Family photographed in South Carolina, late 1890s",
            "expected": True,
            "description": "Simple but useful description"
        },
        {
            "text": "Civil rights demonstration outside courthouse, protesters holding signs",
            "expected": True,
            "description": "Historical event description"
        },
        {
            "text": "© Getty Images. Download this image. Rights managed.",
            "expected": False,
            "description": "Copyright and download boilerplate"
        },
        {
            "text": "Portrait of Abraham Lincoln, taken during his presidency, circa 1863",
            "expected": True,
            "description": "Historical portrait with context"
        },
        {
            "text": "Click here to view larger image. Share on social media.",
            "expected": False,
            "description": "Website navigation text"
        }
    ]
    
    print(f"\n🔍 TESTING {len(test_cases)} CASES:")
    
    results = []
    for i, case in enumerate(test_cases, 1):
        print(f"\n{i}️⃣ {case['description']}")
        print(f"   Text: \"{case['text']}\"")
        print(f"   Expected: {'✅ USEFUL' if case['expected'] else '❌ NOT USEFUL'}")
        
        try:
            result = is_metadata_sufficient(case['text'], client)
            correct = result == case['expected']
            
            print(f"   Result: {'✅ CORRECT' if correct else '❌ INCORRECT'}")
            results.append(correct)
            
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            results.append(False)
    
    # Summary
    correct_count = sum(results)
    total_count = len(results)
    accuracy = (correct_count / total_count) * 100 if total_count > 0 else 0
    
    print(f"\n📊 RESULTS:")
    print(f"   Correct: {correct_count}/{total_count}")
    print(f"   Accuracy: {accuracy:.1f}%")
    
    if accuracy >= 80:
        print(f"   ✅ GOOD - Metadata evaluation is working well!")
    else:
        print(f"   ⚠️ NEEDS IMPROVEMENT - Consider refining the prompt")

if __name__ == "__main__":
    test_metadata_evaluation() 