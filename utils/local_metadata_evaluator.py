#!/usr/bin/env python3
"""
Local metadata quality evaluator using spaCy and rule-based heuristics.
Fast, free alternative to OpenAI-based evaluation.
"""

import re
import spacy
from typing import Dict, List, Tuple
from pathlib import Path

# Load spaCy model (install with: python -m spacy download en_core_web_sm)
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("spaCy model not found. Install with: python -m spacy download en_core_web_sm")
    nlp = None

class LocalMetadataEvaluator:
    def __init__(self):
        self.historical_keywords = {
            # Time periods
            'century', 'circa', 'c.', 'ca.', 'american civil war', 'world war', 'wwi', 'wwii',
            'reconstruction', 'antebellum', 'colonial', 'revolutionary war', 'great depression',
            'gilded age', 'progressive era', 'jazz age', '1800s', '1900s', 'nineteenth', 'twentieth',
            
            # Military/Political
            'general', 'president', 'colonel', 'captain', 'union', 'confederate', 'federal',
            'regiment', 'battalion', 'army', 'navy', 'military', 'battle', 'campaign', 'war',
            'politician', 'senator', 'congressman', 'governor', 'mayor',
            
            # Photography/Archives
            'photograph', 'daguerreotype', 'tintype', 'carte de visite', 'cabinet card',
            'albumen', 'gelatin silver', 'glass plate', 'negative', 'print', 'portrait',
            'studio', 'photographer', 'archive', 'collection', 'manuscript', 'library',
            
            # Geographic/Social
            'north', 'south', 'east', 'west', 'city', 'town', 'county', 'state', 'territory',
            'frontier', 'settlement', 'plantation', 'farm', 'railroad', 'factory', 'mill',
            'immigrant', 'migration', 'slavery', 'abolition', 'suffrage', 'temperance',
            
            # People/Family
            'family', 'husband', 'wife', 'children', 'son', 'daughter', 'father', 'mother',
            'brother', 'sister', 'uncle', 'aunt', 'cousin', 'grandfather', 'grandmother'
        }
        
        self.boilerplate_indicators = {
            'stock photo', 'getty images', 'download', 'license', 'royalty free', 'editorial use',
            'cookies', 'privacy policy', 'terms of service', 'log in', 'sign up', 'cart',
            'shopping', 'purchase', 'buy now', 'add to cart', 'checkout', 'payment',
            'search results', 'related images', 'similar photos', 'more like this',
            'advertisement', 'sponsored', 'promotion', 'sale', 'discount', 'offer'
        }
        
        self.archival_quality_indicators = {
            'archival', 'historical', 'manuscript', 'document', 'record', 'collection',
            'donated', 'acquired', 'preservation', 'digitized', 'original', 'vintage',
            'authentic', 'provenance', 'attribution', 'creator', 'photographer', 'artist'
        }

    def evaluate_metadata(self, text: str, has_url: bool = False) -> Dict[str, any]:
        """
        Evaluate metadata quality using local analysis.
        Returns dict with 'sufficient' (bool), 'reason' (str), 'confidence' (str), 'score' (float)
        
        NOTE: This method is deprecated. Use evaluate_metadata_local() function instead.
        """
        # Delegate to the new function for consistency
        return evaluate_metadata_local(text, has_url)

def test_evaluator():
    """Test the evaluator with sample texts using the new 40-point scale."""
    test_cases = [
        "Portrait of General Ulysses S. Grant, circa 1865, taken during the American Civil War by photographer Mathew Brady",
        "Stock photo of a man in uniform, royalty free, download now",
        "Family photograph from the 1920s showing three generations",
        "Getty Images watermark visible",
        "Historical photograph from the Library of Congress collection showing President Abraham Lincoln with his cabinet members in 1864",
        "Short text"
    ]
    
    for i, text in enumerate(test_cases, 1):
        print(f"Test {i}: {text[:50]}...")
        
        result = evaluate_metadata_local(text)
        print(f"  {'✅ SUFFICIENT' if result['sufficient'] else '❌ INSUFFICIENT'}")
        print(f"    Score: {result['score']:.0f}/40, Reason: {result['reason']}")
        print()

# Global instance
_evaluator = LocalMetadataEvaluator()

def evaluate_metadata_local(text: str, has_url: bool = False) -> Dict[str, any]:
    """
    Evaluate metadata quality using local analysis.
    Uses a realistic 40-point scale where 15+ is considered good quality.
    Returns dict with 'sufficient' (bool), 'reason' (str), 'confidence' (str), 'score' (float)
    """
    if not text or not text.strip():
        return {
            'sufficient': False,
            'reason': 'No metadata text provided',
            'confidence': 'high',
            'score': 0.0
        }

    text_clean = text.strip()
    
    # Quick length check - more generous
    if len(text_clean) < 15:
        return {
            'sufficient': False,
            'reason': 'Text too short (less than 15 characters)',
            'confidence': 'high',
            'score': 3.0
        }

    evaluator = LocalMetadataEvaluator()
    score = 0.0
    reasons = []
    
    # 1. Basic text quality (12 points max) - More generous
    length_score = min(len(text_clean) / 80, 1.0) * 12  # 0-12 points, easier to get full points
    score += length_score
    
    # 2. Check for boilerplate content (penalty up to -8 points) - Less harsh penalty
    text_lower = text_clean.lower()
    boilerplate_count = sum(1 for phrase in evaluator.boilerplate_indicators if phrase in text_lower)
    boilerplate_penalty = min(boilerplate_count * 2, 8)  # Max 8 point penalty (reduced)
    score -= boilerplate_penalty
    
    if boilerplate_count > 0:
        reasons.append(f"Contains {boilerplate_count} boilerplate phrases (-{boilerplate_penalty} pts)")
    
    # 3. Historical keywords (15 points max) - More generous
    historical_matches = sum(1 for keyword in evaluator.historical_keywords if keyword in text_lower)
    historical_score = min(historical_matches / 2, 1.0) * 15  # 0-15 points, only need 2 matches for full
    score += historical_score
    
    if historical_matches > 0:
        reasons.append(f"Contains {historical_matches} historical keywords (+{historical_score:.0f} pts)")
    
    # 4. Archival quality indicators (10 points max) - More generous
    archival_indicators = ['photographer', 'creator', 'archive', 'collection', 'museum', 'library', 'footage', 'film', 'video', 'documentary']
    archival_matches = sum(1 for indicator in archival_indicators if indicator in text_lower)
    archival_score = min(archival_matches / 1, 1.0) * 10  # 0-10 points, only need 1 match for full
    score += archival_score
    
    if archival_matches > 0:
        reasons.append(f"Contains {archival_matches} archival quality indicators (+{archival_score:.0f} pts)")
    
    # 5. Named entity detection (10 points max) - More generous
    # Simple patterns for names, places, organizations
    name_pattern = r'\b[A-Z][a-z]+ [A-Z][a-z]+\b'  # "John Smith"
    place_pattern = r'\b[A-Z][a-z]+(?:, [A-Z][a-z]+)*\b'  # "New York"
    org_pattern = r'\b[A-Z][A-Z\s&]{2,}\b'  # "FBI", "NEW YORK TIMES"
    
    name_matches = len(re.findall(name_pattern, text_clean))
    place_matches = len(re.findall(place_pattern, text_clean))
    org_matches = len(re.findall(org_pattern, text_clean))
    
    total_entities = name_matches + place_matches + org_matches
    entity_score = min(total_entities / 2, 1.0) * 10  # 0-10 points, only need 2 entities for full
    score += entity_score
    
    if total_entities > 0:
        reasons.append(f"Contains {total_entities} named entities (+{entity_score:.0f} pts)")
    
    # 6. Date patterns (bonus up to 6 points) - More generous
    date_patterns = [
        r'\b(18|19|20)\d{2}\b',  # Years
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\b',
        r'\bcirca\b', r'\bc\.\s*\d{4}\b', r'\bca\.\s*\d{4}\b'
    ]
    
    date_matches = sum(1 for pattern in date_patterns if re.search(pattern, text_lower))
    if date_matches > 0:
        date_bonus = min(date_matches * 3, 6)  # Up to 6 bonus points
        score += date_bonus
        reasons.append(f"Contains {date_matches} date patterns (+{date_bonus} pts)")
    
    # 7. Technical metadata bonus (5 points) - New category for footage
    technical_terms = ['fps', 'resolution', 'codec', 'bitrate', 'duration', 'format', 'timecode']
    technical_matches = sum(1 for term in technical_terms if term in text_lower)
    if technical_matches > 0:
        technical_bonus = min(technical_matches, 5)  # Up to 5 bonus points
        score += technical_bonus
        reasons.append(f"Contains {technical_matches} technical terms (+{technical_bonus} pts)")
    
    # Cap score at 50 (new realistic maximum with more generous scoring)
    score = min(score, 50.0)
    
    # Much more generous threshold: 10/50 is good quality (20% = passing grade)
    threshold = 10.0
    sufficient = score >= threshold
    
    # Determine confidence based on 50-point scale
    if score >= 30:      # 60% = A grade
        confidence = 'high'
    elif score >= 20:    # 40% = B grade  
        confidence = 'medium'
    else:                # Below 40% = C or lower
        confidence = 'low'
    
    # Generate reason with 50-point scoring (much more generous)
    if score >= 40:
        grade = "A+"
    elif score >= 30:
        grade = "A"
    elif score >= 25:
        grade = "B+"
    elif score >= 20:
        grade = "B"
    elif score >= 15:
        grade = "C+"
    elif score >= 10:
        grade = "C (PASSING)"
    elif score >= 5:
        grade = "D"
    else:
        grade = "F"
    
    if sufficient:
        reason = f"Good quality metadata ({score:.0f}/50 - Grade: {grade}). " + "; ".join(reasons)
    else:
        reason = f"Insufficient metadata quality ({score:.0f}/50 - Grade: {grade}, need 10+ to pass). " + "; ".join(reasons)
    
    return {
        'sufficient': sufficient,
        'reason': reason,
        'confidence': confidence,
        'score': score
    }

if __name__ == "__main__":
    test_evaluator() 