# Temporary Files Directory

This directory is designated for **ALL temporary test files** created during development and testing.

## What Goes Here
- Test scripts (`test_*.py`, `*_test.py`)
- Sample data files
- Debug output files
- Temporary development scripts
- Any files created during testing/debugging that aren't part of the main codebase

## Important Notes
- **Clean up after yourself**: Remove test files when you're done or mark them clearly for deletion
- Files in this directory are **gitignored** and will not be committed to the repository
- Do NOT place test files in other directories - they belong here

## Auto-Cleanup
This directory and its contents are ignored by git, so temporary files won't accidentally be committed to the repository. 