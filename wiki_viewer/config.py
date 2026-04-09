import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent
WIKI_DIR = BASE_DIR / "MBAWiki"
CONCEPTS_DIR = WIKI_DIR
CHARTS_DIR = WIKI_DIR / "assets" / "charts"

# Flask config
DEBUG = True
HOST = "127.0.0.1"
PORT = 5000

# Concept file pattern
CONCEPT_FILE_PREFIX = "Concept-"
CASE_FILE_PREFIX = "Case-"
CONCEPT_FILE_SUFFIX = ".md"

# Verify paths exist
assert WIKI_DIR.exists(), f"Wiki directory not found: {WIKI_DIR}"
assert CONCEPTS_DIR.exists(), f"Concepts directory not found: {CONCEPTS_DIR}"
assert CHARTS_DIR.exists(), f"Charts directory not found: {CHARTS_DIR}"
