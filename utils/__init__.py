"""
Utility modules for the FileMaker Backend system.

This package contains utility modules that can be imported individually
to avoid dependency issues.
"""

# Make individual modules available for import
# but don't import them automatically to avoid dependency errors

__all__ = [
    'evaluate_metadata_local',
    'LocalMetadataEvaluator', 
    'global_openai_client',
    'GlobalOpenAIClient'
]

def get_metadata_evaluator():
    """Get the metadata evaluator, handling import errors gracefully."""
    try:
        from .local_metadata_evaluator import evaluate_metadata_local, LocalMetadataEvaluator
        return evaluate_metadata_local, LocalMetadataEvaluator
    except ImportError as e:
        print(f"Warning: Could not import metadata evaluator: {e}")
        return None, None

def get_openai_client():
    """Get the OpenAI client."""
    from .openai_client import global_openai_client, GlobalOpenAIClient
    return global_openai_client, GlobalOpenAIClient 