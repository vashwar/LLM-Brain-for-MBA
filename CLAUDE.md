# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: KnowledgeWiki (MBA Wiki)

An LLM-powered wiki that extracts economics concepts from MBA lecture materials (PDFs and transcripts) and presents them in a locally-hosted Wikipedia-style web interface.

### Architecture

```
Google Drive (lectures, cases, transcripts folders)
  → ingest/process_standalone.py (downloads + processes files, 1-2 Gemini API calls)
    → Lectures:     MBAWiki/Concept-*.md (concept files)
    → Cases:        MBAWiki/Case-*.md (case study files)
    → Transcripts:  Concept-*.md + updates Case-*.md discussions
      → ingest/build_search_index.py (local embeddings, auto-refreshes after ingest)
        → MBAWiki/assets/search_index.npz + search_metadata.json
          → wiki_viewer/app.py (Flask web server, renders wiki + /search + /health)
            → http://127.0.0.1:5000/
  → Maintenance/lint_wiki.py (structural health checks, markdown reports)
```

### Key Files

**Ingest (ingest/):**
- **ingest/process_standalone.py** - Standalone batch processor. Downloads from Google Drive + processes files (1-2 Gemini API calls each). Handles lectures, cases, and transcripts. Retries on error with configurable wait. Replaces the legacy `download_and_process.py` + `process_single_file.py` pipeline.
- **ingest/build_search_index.py** - Builds a local semantic search index (`BAAI/bge-small-en-v1.5` via fastembed, ONNX). Outputs `search_index.npz` + `search_metadata.json` in `MBAWiki/assets/`. Supports `--append` for incremental updates. Logs to `log.md`.
- **ingest/build_graph.py** - Builds `knowledge_graph.json` from wiki markdown files (nodes + links for D3 visualization).
- **ingest/tag_images.py** - Image tagging workflow. Maps image captions to concepts via 1 Gemini API call. Wiki viewer auto-inserts tagged images into matching concept pages.
- **ingest/init_image_tags.py** - Helper to populate `image_tags.json` with all PNG filenames from charts folder.

**Query (wiki_viewer/):**
- **wiki_viewer/app.py** - Flask web server with Wikipedia-style UI. Serves concepts at `/concept/<slug>`, cases at `/case/<slug>`, semantic search at `/search?q=...&course=...&type=...`, and health dashboard at `/health`. Loads the search index at startup (fast); embedding model is lazy-loaded on first query (~3s cold start).
- **wiki_viewer/config.py** - Configuration. Reads `WIKI_DIR` from `.env` (defaults to `MBAWiki` relative to project root).
- **wiki_viewer/utils/search.py** - `SearchIndex` class. Loads `.npz` + JSON sidecar, runs cosine similarity search with course/type filters and a +0.15 title-substring boost. Relevance threshold 0.2.
- **wiki_viewer/utils/wikilink_processor.py** - Converts [[Wikilinks]] to HTML links. Scans both `Concept-*.md` and `Case-*.md`. Routes wikilinks to correct URL prefix.
- **wiki_viewer/utils/markdown_parser.py** - Markdown to HTML conversion with TOC.

**Maintenance (Maintenance/):**
- **Maintenance/lint_wiki.py** - Wiki linter: orphan pages, broken wikilinks, missing concepts, stale content. Generates markdown reports in `Maintenance/lint-report-*.md`. Also called by `/health` route.

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
# ── Ingest ─────────────────────────────────────────────────
# Batch process all files for a course (downloads from Google Drive)
python ingest/process_standalone.py --course "CourseName"
python ingest/process_standalone.py --course "CourseName" --images
python ingest/process_standalone.py --course "CourseName" --wait 15

# Search index (auto-refreshed by batch ingestion)
pip install fastembed                                       # one-time dep
python ingest/build_search_index.py                         # full rebuild
python ingest/build_search_index.py --append                # incremental (mtime-based)

# Knowledge graph
python ingest/build_graph.py

# Image tagging workflow
python ingest/init_image_tags.py              # Create JSON with all PNG filenames
python ingest/tag_images.py --list            # See untagged images
# (manually edit image_tags.json to add captions)
python ingest/tag_images.py --map             # Map captions to concepts (1 API call)
python ingest/tag_images.py --status          # Verify mappings

# ── Query ──────────────────────────────────────────────────
# Run wiki viewer
python wiki_viewer/app.py
# → http://127.0.0.1:5000/
# → http://127.0.0.1:5000/search?q=your+question  (semantic search)
# → http://127.0.0.1:5000/health                   (health dashboard)

# ── Maintenance ────────────────────────────────────────────
python Maintenance/lint_wiki.py              # full report (console + markdown)
python Maintenance/lint_wiki.py --orphans    # only orphan pages
python Maintenance/lint_wiki.py --broken     # only broken wikilinks
python Maintenance/lint_wiki.py --no-save    # console only, don't write report

# ── Legacy (gitignored, kept for reference) ────────────────
# process_single_file.py, download_and_process.py, process_all_lite.py
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

### Environment Variables (.env)

- `WIKI_DIR` — Path to wiki content directory (default: `MBAWiki`, relative to project root)
- `Gemini_Api_Key` — Gemini API key for LLM calls
- `GEMINI_MODEL` — Gemini model name for ingestion

### Folder Structure

```
KnowledgeWiki/
├── ingest/                         # Data processing scripts
│   ├── process_standalone.py       # Batch processor (Google Drive + Gemini)
│   ├── build_search_index.py       # Semantic search index builder
│   ├── build_graph.py              # Knowledge graph JSON builder
│   ├── tag_images.py               # Image-to-concept mapper
│   └── init_image_tags.py          # Image tags JSON initializer
├── wiki_viewer/                    # Flask web application (Query stage)
│   ├── app.py                      # Web server (concepts, cases, search, health)
│   ├── config.py                   # Configuration (reads WIKI_DIR from .env)
│   ├── templates/                  # HTML templates
│   ├── static/css/                 # Wikipedia-style CSS
│   └── utils/                      # markdown_parser, wikilink_processor, search
├── Maintenance/                    # Linting and health checks
│   ├── lint_wiki.py                # Wiki linter (orphans, broken links, stale)
│   └── lint-report-*.md            # Generated lint reports
├── MBAWiki/                        # Wiki content (gitignored)
│   ├── Concept-*.md                # Concept markdown files
│   ├── Case-*.md                   # Case study markdown files
│   ├── assets/charts/              # Extracted PDF images + image_tags.json
│   ├── assets/search_index.npz     # Semantic search embeddings (N x 384 float32)
│   ├── assets/search_metadata.json # Per-row {slug, title, type, course, preview, mtime}
│   └── archive/                    # Old/archived concepts
├── Transcript_class_lecture/       # Downloaded lecture files (local cache, gitignored)
├── credentials/                    # Google Drive OAuth tokens (gitignored)
├── .env                            # Environment variables (gitignored)
├── courses.json                    # Course configuration (shared)
├── course_groups.json              # Course groupings
└── log.md                          # Append-only ingestion log
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

