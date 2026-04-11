# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: KnowledgeWiki (MBA Wiki)

An LLM-powered wiki that extracts economics concepts from MBA lecture materials (PDFs and transcripts) and presents them in a locally-hosted Wikipedia-style web interface.

### Architecture

```
Google Drive (lectures, cases, transcripts folders)
  → download_and_process.py (downloads file, calls processor)
    → process_single_file.py (extracts text, 1-2 Gemini API calls)
      → Lectures:     MBAWiki/Concept-*.md (concept files)
      → Cases:        MBAWiki/Case-*.md (case study files)
      → Transcripts:  Concept-*.md + updates Case-*.md discussions
        → build_search_index.py (local embeddings, auto-refreshes after ingest)
          → MBAWiki/assets/search_index.npz + search_metadata.json
            → wiki_viewer/app.py (Flask web server, renders wiki + /search)
              → http://127.0.0.1:5000/
```

### Key Files

- **download_and_process.py** - Google Drive integration. Downloads files, calls processor. Supports single file or batch `--all` mode (lectures → cases → transcripts). Timeout: 300s for PDFs/DOCX, 120s for TXT. Triggers a full search index rebuild at the end of `--all`.
- **process_single_file.py** - Core processor. Three modes via `--type`: `lecture` (default), `case`, `transcript`. Handles `.pdf`, `.docx`, and `.txt` inputs (legacy `.doc` is unsupported — convert first). Auto-creates new files, auto-merges duplicates via Gemini rewrite. Accepts `--no-images` flag. After ingest, runs an incremental search index update (mtime-based).
- **build_search_index.py** - Builds a local semantic search index (`BAAI/bge-small-en-v1.5` via fastembed, ONNX). Outputs `search_index.npz` + `search_metadata.json` in `MBAWiki/assets/`. Supports `--append` for incremental updates. Logs to `log.md` as `## [ts] index | Search index ...`.
- **tag_images.py** - Image tagging workflow. Maps image captions to concepts via 1 Gemini API call. Wiki viewer auto-inserts tagged images into matching concept pages.
- **init_image_tags.py** - Helper to populate `image_tags.json` with all PNG filenames from charts folder.
- **wiki_viewer/app.py** - Flask web server with Wikipedia-style UI. Serves concepts at `/concept/<slug>`, cases at `/case/<slug>`, and semantic search at `/search?q=...&course=...&type=...`. Loads the search index at startup (fast); embedding model is lazy-loaded on first query (~3s cold start).
- **wiki_viewer/utils/search.py** - `SearchIndex` class. Loads `.npz` + JSON sidecar, runs cosine similarity search with course/type filters and a +0.15 title-substring boost. Relevance threshold 0.2.
- **wiki_viewer/utils/wikilink_processor.py** - Converts [[Wikilinks]] to HTML links. Scans both `Concept-*.md` and `Case-*.md`. Routes wikilinks to correct URL prefix.
- **wiki_viewer/utils/markdown_parser.py** - Markdown to HTML conversion with TOC.

### Processing Rules

- **LLM Model:** `gemini-3-flash-preview` (Gemini 3 Flash)
- **API Optimization:** Max 2 API calls per file (1 extraction + 1 merge if duplicates found).
- **Three file types:** `lecture` (Concept-*.md), `case` (Case-*.md), `transcript` (both)
- **Multi-concept extraction:** Each lecture/transcript yields 3-10 concepts
- **Full content:** Send entire file text to Gemini, no truncation
- **Images:** Extract from PDFs and save to `MBAWiki/assets/charts/` (10KB min size filter). NOT auto-inserted into wiki. User manually tags images via `image_tags.json`, then `tag_images.py --map` maps them to concepts (1 API call).
- **Auto-create:** New concepts → `Concept-{slug}.md`, new cases → `Case-{slug}.md`
- **Auto-merge:** If concept matches existing one, Gemini rewrites the full page seamlessly. No "Additional Content from..." blocks.
- **Case studies:** Specialized format with Core Dilemma, Stakeholders, Financial Context, Class Discussion sections. Tagged `#unresolved` until transcript populates discussion.
- **Transcripts:** Dual duty — extract concepts AND fill case discussion sections. Single API call returns both. Case updates are file I/O (no extra API call).
- **Wikilinks:** Only link to concepts/cases that actually exist in `MBAWiki/`
- **No Vision API:** Do not use Gemini Vision - too expensive
- **Clean rebuild:** Delete `Concept-*.md` and `Case-*.md` files before `--all` to regenerate

### Commands

```bash
# List available courses and files
python download_and_process.py
python download_and_process.py --course "CourseName"

# Process a single file
python download_and_process.py --course "CourseName" "Week 1"

# Process ALL files (lectures → cases → transcripts)
python download_and_process.py --course "CourseName" --all

# Process ALL files with image extraction
python download_and_process.py --course "CourseName" --all --images

# Process only cases or transcripts
python download_and_process.py --course "CourseName" --cases-only
python download_and_process.py --course "CourseName" --transcripts-only

# Process local file with type
python process_single_file.py "file.pdf" --course "CourseName" --type case
python process_single_file.py "file.txt" --course "CourseName" --type transcript

# Image tagging workflow
python init_image_tags.py              # Create JSON with all PNG filenames
python tag_images.py --list            # See untagged images
# (manually edit image_tags.json to add captions)
python tag_images.py --map             # Map captions to concepts (1 API call)
python tag_images.py --status          # Verify mappings

# Run wiki viewer
python wiki_viewer/app.py
# → http://127.0.0.1:5000/
# → http://127.0.0.1:5000/search?q=your+question  (semantic search)

# Search index (auto-refreshed by single-file + batch ingestion)
pip install fastembed                                  # one-time dep
python build_search_index.py                           # full rebuild
python build_search_index.py --append                  # incremental (mtime-based)
```

### Image Tagging Format

`MBAWiki/assets/charts/image_tags.json` - same image can map to multiple concepts:
```json
{
  "Slides_Page15_Plot0.png": ["supply vs demand intersection", "downward sloping demand"],
  "Slides_Page22_Plot0.png": ["elastic vs inelastic comparison"]
}
```
After `--map`, becomes:
```json
{
  "Slides_Page15_Plot0.png": [
    {"concept": "Supply Curve", "caption": "supply vs demand intersection"},
    {"concept": "Demand Curve", "caption": "downward sloping demand"}
  ]
}
```

### Folder Structure

```
MBAWiki/                    # Wiki content
  Concept-*.md              # Concept markdown files
  Case-*.md                 # Case study markdown files
  assets/charts/            # Extracted PDF images
    image_tags.json          # Image-to-concept mappings
  assets/search_index.npz       # Semantic search embeddings (N x 384 float32)
  assets/search_metadata.json   # Per-row {slug, title, type, course, preview, mtime}
  archive/                  # Old/archived concepts
wiki_viewer/                # Flask web application
  app.py, config.py
  templates/                # HTML templates (incl. search.html)
  static/css/               # Wikipedia-style CSS
  utils/                    # markdown_parser, wikilink_processor, search (SearchIndex)
Transcript_class_lecture/   # Downloaded lecture files (local cache)
  CourseName/               # Lecture PDFs, DOCXs, and TXTs
  CourseName/cases/         # Case study files
  CourseName/transcripts/   # Transcript files
credentials/                # Google Drive OAuth tokens
Vision/                     # Vision project notes
```

## gstack

- For all web browsing, always use the `/browse` skill from gstack. Never use `mcp__claude-in-chrome__*` tools.

### Available gstack skills

- `/office-hours` - Office hours
- `/plan-ceo-review` - Plan CEO review
- `/plan-eng-review` - Plan engineering review
- `/plan-design-review` - Plan design review
- `/design-consultation` - Design consultation
- `/review` - Code review
- `/ship` - Ship
- `/land-and-deploy` - Land and deploy
- `/canary` - Canary
- `/benchmark` - Benchmark
- `/browse` - Web browsing
- `/qa` - QA
- `/qa-only` - QA only
- `/design-review` - Design review
- `/setup-browser-cookies` - Setup browser cookies
- `/setup-deploy` - Setup deploy
- `/retro` - Retro
- `/investigate` - Investigate
- `/document-release` - Document release
- `/codex` - Codex
- `/cso` - CSO
- `/autoplan` - Auto plan
- `/careful` - Careful mode
- `/freeze` - Freeze
- `/guard` - Guard
- `/unfreeze` - Unfreeze
- `/gstack-upgrade` - Upgrade gstack

