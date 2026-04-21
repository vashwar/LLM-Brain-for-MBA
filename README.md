# KnowledgeWiki

**Turn your lectures into a Wikipedia-style knowledge base — for free.**

KnowledgeWiki is an open-source tool that takes your lecture slides, PDFs, case studies, and class transcripts, extracts every concept using Google's Gemini AI, and serves them as an interconnected, searchable wiki with an interactive knowledge graph.

Built for MBA students, but works for **any academic discipline** — law, medicine, engineering, computer science, history, or anything with lecture material. If you have PDFs and transcripts, KnowledgeWiki can build a knowledge base from them.

## Inspiration

This project is inspired by [Andrej Karpathy's idea](https://x.com/karpathy) of using LLMs to build personal knowledge systems. Instead of passively reading lecture notes, KnowledgeWiki actively extracts, links, and organizes concepts — turning a semester of material into an interconnected reference you can search, browse, and explore.

## Why It's Free

The entire pipeline runs on **Gemini's free tier**. The code is specifically optimized for this:

- **Single model, no waste**: Uses `gemini-3.1-flash-lite-preview` (highest free-tier rate limit)
- **Max 2 API calls per file**: 1 for extraction + 1 for merging duplicates. No wasted calls
- **Automatic rate limiting**: 20-second delays between files in batch mode to stay within free quotas
- **Batch merging**: All duplicate concepts from a single file are merged in 1 API call, not individually
- **Auto-retry on error**: Waits and retries from unprocessed files on any failure
- **No Vision API**: Image tagging uses text-only Gemini calls (Vision API is expensive)
- **Transcript dual-processing**: A single API call extracts both new concepts AND case discussion updates

You need: a free [Google Gemini API key](https://aistudio.google.com/apikey) and (optionally) a Google Drive API setup for auto-downloading materials.

## What You Get

- **Wikipedia-style wiki** with semantic search, navigation, and table of contents for every concept
- **Auto-linked concepts**: `[[Wikilinks]]` between related concepts — click to navigate
- **Interactive knowledge graph**: D3.js force-directed visualization of all concepts and their connections
- **Semantic search**: Local embeddings via `BAAI/bge-small-en-v1.5` (ONNX, no PyTorch required)
- **LaTeX math rendering**: Equations render properly via KaTeX
- **Course organization**: Concepts grouped by course with cross-course linking
- **Case study tracking**: Dedicated case pages with discussion sections populated from transcripts
- **Health dashboard**: Wiki linter checks for orphan pages, broken links, missing concepts, and stale content

---

## Project Structure

The project is organized into **3 stages**:

```
KnowledgeWiki/
├── ingest/                         # Stage 1: Data Processing
│   ├── process_standalone.py       #   Batch processor (Google Drive + Gemini)
│   ├── build_search_index.py       #   Semantic search index builder
│   ├── build_graph.py              #   Knowledge graph JSON builder
│   ├── tag_images.py               #   Image-to-concept mapper
│   └── init_image_tags.py          #   Image tags JSON initializer
│
├── wiki_viewer/                    # Stage 2: Query / Viewing
│   ├── app.py                      #   Flask web server
│   ├── config.py                   #   Configuration (reads WIKI_DIR from .env)
│   ├── templates/                  #   HTML templates (Wikipedia-style)
│   ├── static/css/                 #   Stylesheets
│   └── utils/                      #   Markdown parser, wikilink processor, search
│
├── Maintenance/                    # Stage 3: Linting & Health Checks
│   ├── lint_wiki.py                #   Wiki linter (orphans, broken links, stale)
│   └── lint-report-*.md            #   Generated lint reports
│
├── MBAWiki/                        # Generated wiki content (gitignored)
│   ├── Concept-*.md                #   Concept pages
│   ├── Case-*.md                   #   Case study pages
│   └── assets/                     #   Charts, search index, knowledge graph
│
├── courses.json                    # Course configuration
├── course_groups.json              # Cross-course grouping
├── .env                            # API keys + WIKI_DIR setting
└── log.md                          # Append-only ingestion log
```

---

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/KnowledgeWiki.git
cd KnowledgeWiki
pip install -r requirements.txt
```

### 2. Get a Gemini API Key (Free)

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create a free API key
3. Create a `.env` file in the project root:

```
Gemini_Api_Key="your-api-key-here"
WIKI_DIR=MBAWiki
```

### 3. Set Up Your Courses

Edit `courses.json` to define your courses. If you're using Google Drive to store materials, add the folder IDs. If you're processing local files, the folder IDs can be `null`:

```json
{
  "Microeconomics": {
    "lectures_folder_id": "your-google-drive-folder-id",
    "cases_folder_id": null,
    "transcripts_folder_id": null,
    "seed_concepts": [
      "Supply and Demand",
      "Price Elasticity",
      "Opportunity Cost"
    ]
  }
}
```

### 4. Process Your Materials

```bash
python ingest/process_standalone.py --course "Microeconomics"
```

This downloads from Google Drive and processes all files (seed concepts -> lectures -> cases -> transcripts) automatically. It retries on errors with a configurable wait.

### 5. Build the Knowledge Graph

```bash
python ingest/build_graph.py
```

### 6. View Your Wiki

```bash
python wiki_viewer/app.py
```
Open http://127.0.0.1:5000/ in your browser.

---

## Scripts Reference

### Ingest Stage (`ingest/`)

#### `ingest/process_standalone.py` — Batch Processor

Downloads files from Google Drive and processes them in the correct order (seed -> lectures -> cases -> transcripts). Retries on errors with configurable wait time.

```bash
# Process all files for a course
python ingest/process_standalone.py --course "Microeconomics"

# Process with image extraction from PDFs
python ingest/process_standalone.py --course "Microeconomics" --images

# Custom retry wait time (default: 30 min)
python ingest/process_standalone.py --course "Microeconomics" --wait 15
```

| Flag | Description |
|------|-------------|
| `--course "Name"` | Which course to process (required) |
| `--images` | Extract charts/figures from PDFs during processing |
| `--wait N` | Minutes to wait before retrying on error (default: 30) |

**Processing modes** (automatic based on folder):

| Folder | Output | API Calls |
|--------|--------|-----------|
| lectures | 20-25 `Concept-*.md` files per lecture | 1-2 |
| cases | 1 `Case-*.md` file per case | 1 |
| transcripts | Concepts + case discussion updates | 1 |

**Auto-merge**: If a concept already exists, Gemini rewrites the page seamlessly — merging new content into the existing page.

**Tracking**: Already-processed files are recorded in `processed_files.json` and skipped on future runs. Delete entries to reprocess.

---

#### `ingest/build_search_index.py` — Semantic Search Index

Builds a local semantic search index using `BAAI/bge-small-en-v1.5` via fastembed (ONNX, no PyTorch).

```bash
pip install fastembed                         # one-time dependency
python ingest/build_search_index.py           # full rebuild
python ingest/build_search_index.py --append  # incremental (only re-embeds changed files)
```

The search index is also auto-refreshed after each batch ingestion.

---

#### `ingest/build_graph.py` — Knowledge Graph

Scans all wiki pages, extracts `[[Wikilinks]]`, and builds an interactive graph for the `/graph` page.

```bash
python ingest/build_graph.py
```

Output: `MBAWiki/assets/knowledge_graph.json`

---

#### Image Tagging (Optional)

Image tagging lets you associate extracted PDF charts/figures with specific concepts. The wiki viewer will auto-insert tagged images into matching concept pages.

```bash
# Step 1: Extract images during processing (use --images flag)
python ingest/process_standalone.py --course "Microeconomics" --images

# Step 2: Initialize the tags file
python ingest/init_image_tags.py

# Step 3: Manually add captions to MBAWiki/assets/charts/image_tags.json
# { "Slides_Page15_Plot0.png": ["supply vs demand intersection"] }

# Step 4: Auto-map captions to concepts (1 Gemini API call)
python ingest/tag_images.py --map

# Step 5: Verify mappings
python ingest/tag_images.py --status
```

---

### Query Stage (`wiki_viewer/`)

#### `wiki_viewer/app.py` — Flask Wiki Server

```bash
python wiki_viewer/app.py
# Open http://127.0.0.1:5000/
```

| Route | Description |
|-------|-------------|
| `/` | Homepage — course grid, concept of the day, did you know |
| `/course/<slug>` | All concepts and cases for a course |
| `/concept/<slug>` | Individual concept page with TOC, equations, related links |
| `/case/<slug>` | Case study page with discussion section |
| `/cases` | All case studies across all courses |
| `/graph` | Interactive knowledge graph (D3.js force-directed) |
| `/search?q=...` | Semantic search with course and type filters |
| `/health` | Health dashboard — runs wiki linter, saves markdown report |

The `WIKI_DIR` environment variable in `.env` controls where wiki content is read from (default: `MBAWiki`).

---

### Maintenance Stage (`Maintenance/`)

#### `Maintenance/lint_wiki.py` — Wiki Linter

Checks for structural issues and generates reports.

```bash
python Maintenance/lint_wiki.py              # full report (console + markdown)
python Maintenance/lint_wiki.py --orphans    # only orphan pages
python Maintenance/lint_wiki.py --broken     # only broken wikilinks
python Maintenance/lint_wiki.py --missing    # only missing concepts
python Maintenance/lint_wiki.py --stale      # only stale content
python Maintenance/lint_wiki.py --no-save    # console only, skip markdown report
```

Reports are saved to `Maintenance/lint-report-YYYY-MM-DD.md`. The `/health` route in the wiki viewer also runs the linter and saves a report.

---

## Configuration

### `courses.json` — Course Definitions

```json
{
  "Microeconomics": {
    "lectures_folder_id": "google-drive-folder-id-or-null",
    "cases_folder_id": "google-drive-folder-id-or-null",
    "transcripts_folder_id": "google-drive-folder-id-or-null",
    "seed_concepts": ["Supply and Demand", "Price Elasticity"]
  }
}
```

### `course_groups.json` — Cross-Course Linking

```json
{
  "Economics & Strategy": ["Microeconomics", "Financial Accounting"],
  "People & Organizations": ["Leading People"]
}
```

Duplicate detection is tiered:
- **Same course**: Fuzzy matching (catches "Supply Curve" vs "The Supply Curve")
- **Same group**: Exact matching only
- **Other courses**: Exact matching only

### `.env` — Environment Variables

```
Gemini_Api_Key="your-gemini-api-key"
GEMINI_MODEL="gemini-3.1-flash-lite-preview"
WIKI_DIR=MBAWiki
```

### Google Drive Setup (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable the Google Drive API
3. Create OAuth 2.0 credentials (Desktop application)
4. Download as `credentials/credentials.json`
5. On first run, a browser window opens for authentication — the token is saved to `credentials/token.json`

If you don't use Google Drive, just place your files locally in `Transcript_class_lecture/<CourseName>/`.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Gemini_Api_Key not found` | Check your `.env` file has `Gemini_Api_Key="..."` |
| Files skipped as "already processed" | Delete entries from `processed_files.json` to reprocess |
| Rate limit errors (429) | The system auto-retries after a wait period. Adjust with `--wait` |
| Equations not rendering | KaTeX is loaded via CDN — check your internet connection |
| Broken wikilinks | Run `python ingest/build_graph.py` or check `/health` for details |
| Images not showing on concept pages | Run `python ingest/tag_images.py --status` to verify mappings |
| Google Drive auth fails | Delete `credentials/token.json` and re-authenticate |
| Search not working | Run `python ingest/build_search_index.py` to rebuild the index |

---

## Cost Summary

| Component | Cost |
|-----------|------|
| Gemini API | Free (free tier) |
| Google Drive API | Free |
| Python + Flask | Free / open source |
| fastembed (search) | Free / open source |
| KaTeX (math rendering) | Free CDN |
| D3.js (knowledge graph) | Free CDN |
| **Total** | **$0** |

---

## License

MIT
