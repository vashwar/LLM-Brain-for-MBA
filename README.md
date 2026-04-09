# KnowledgeWiki

**Turn your lectures into a Wikipedia-style knowledge base — for free.**

KnowledgeWiki is an open-source tool that takes your lecture slides, PDFs, case studies, and class transcripts, extracts every concept using Google's Gemini AI, and serves them as an interconnected, searchable wiki with an interactive knowledge graph.

Built for MBA students, but works for **any academic discipline** — law, medicine, engineering, computer science, history, or anything with lecture material. If you have PDFs and transcripts, KnowledgeWiki can build a knowledge base from them.

## Inspiration

This project is inspired by [Andrej Karpathy's idea](https://x.com/karpathy) of using LLMs to build personal knowledge systems. Instead of passively reading lecture notes, KnowledgeWiki actively extracts, links, and organizes concepts — turning a semester of material into an interconnected reference you can search, browse, and explore.

## Why It's Free

The entire pipeline runs on **Gemini's free tier**. The code is specifically optimized for this:

- **Model fallback chain**: Uses `gemini-3.1-flash-lite-preview` (highest free-tier rate limit), falling back to `gemini-3-flash-preview` and `gemini-2.5-flash` if rate-limited
- **Max 2 API calls per file**: 1 for extraction + 1 for merging duplicates. No wasted calls
- **Automatic rate limiting**: 15-30 second delays between files in batch mode to stay within free quotas
- **Batch merging**: All duplicate concepts from a single file are merged in 1 API call, not individually
- **Smart retries**: On 429 (rate limit) errors, automatically falls back to a different model instead of waiting
- **No Vision API**: Image tagging uses text-only Gemini calls (Vision API is expensive)
- **Transcript dual-processing**: A single API call extracts both new concepts AND case discussion updates

You need: a free [Google Gemini API key](https://aistudio.google.com/apikey) and (optionally) a Google Drive API setup for auto-downloading materials.

## What You Get

- **Wikipedia-style wiki** with search, navigation, and table of contents for every concept
- **Auto-linked concepts**: `[[Wikilinks]]` between related concepts — click to navigate
- **Interactive knowledge graph**: D3.js force-directed visualization of all concepts and their connections
- **LaTeX math rendering**: Equations render properly via KaTeX
- **Course organization**: Concepts grouped by course with cross-course linking
- **Case study tracking**: Dedicated case pages with discussion sections populated from transcripts

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
Gemini_Api_key="your-api-key-here"
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

### 4. Process Your First Lecture

**From a local file:**
```bash
python process_single_file.py "path/to/lecture.pdf" --course "Microeconomics"
```

**From Google Drive (downloads + processes all files):**
```bash
python download_and_process.py --course "Microeconomics" --all
```

### 5. View Your Wiki

```bash
python wiki_viewer/app.py
```
Open http://127.0.0.1:5000/ in your browser.

---

## Full Pipeline

Here's the complete workflow from raw lecture materials to a running wiki:

```
Step 1: Seed foundational concepts (optional, no API calls)
Step 2: Process lectures → generates Concept-*.md files
Step 3: Process case studies → generates Case-*.md files
Step 4: Process transcripts → enriches concepts + fills case discussions
Step 5: Tag images (optional, 1 API call)
Step 6: Build knowledge graph
Step 7: Start wiki server
```

Running `--all` handles steps 1-4 automatically in the correct order:

```bash
python download_and_process.py --course "Microeconomics" --all
python build_graph.py
python wiki_viewer/app.py
```

---

## Scripts Reference

### `download_and_process.py` — Download & Orchestrate

Downloads files from Google Drive and processes them in the correct order (seed → lectures → cases → transcripts).

```bash
# List available courses
python download_and_process.py

# List files in a specific course
python download_and_process.py --course "Microeconomics"

# Process a single file by name
python download_and_process.py --course "Microeconomics" "Week 1"

# Process ALL files (lectures → cases → transcripts)
python download_and_process.py --course "Microeconomics" --all

# Process ALL files with image extraction
python download_and_process.py --course "Microeconomics" --all --images

# Process only cases or only transcripts
python download_and_process.py --course "Microeconomics" --cases-only
python download_and_process.py --course "Microeconomics" --transcripts-only
```

| Flag | Description |
|------|-------------|
| `--course "Name"` | Which course to process (required) |
| `--all` | Process all files: seed concepts, then lectures, then cases, then transcripts |
| `--images` | Extract charts/figures from PDFs during processing |
| `--cases-only` | Only process files from the cases folder |
| `--transcripts-only` | Only process files from the transcripts folder |

**Tracking**: Already-processed files are recorded in `processed_files.json` and skipped on future runs. Delete entries from this file to reprocess.

---

### `process_single_file.py` — Core Extraction Engine

The heart of the system. Takes a single file (PDF or TXT), sends it to Gemini, and creates/updates wiki pages.

```bash
# Process a lecture PDF
python process_single_file.py "lecture.pdf" --course "Microeconomics"

# Process a case study
python process_single_file.py "case.pdf" --course "Leading People" --type case

# Process a transcript (extracts concepts AND fills case discussions)
python process_single_file.py "transcript.txt" --course "Leading People" --type transcript

# Create seed concept stubs (no API calls)
python process_single_file.py --seed --course "Microeconomics"

# Skip image extraction from PDF
python process_single_file.py "lecture.pdf" --course "Microeconomics" --no-images
```

| Flag | Description |
|------|-------------|
| `--course "Name"` | Which course this file belongs to (required) |
| `--type lecture\|case\|transcript` | Processing mode (default: `lecture`) |
| `--seed` | Create stub files from `seed_concepts` in courses.json |
| `--no-images` | Skip extracting images from PDFs |

**Three processing modes:**

| Mode | Input | Output | API Calls |
|------|-------|--------|-----------|
| `lecture` | Lecture PDF/TXT | 20-25 `Concept-*.md` files | 1-2 |
| `case` | Case study PDF | 1 `Case-*.md` file | 1-2 |
| `transcript` | Class transcript TXT | Concepts + case discussion updates | 1 |
| `--seed` | courses.json config | Stub `Concept-*.md` files | 0 |

**Auto-merge**: If a concept already exists, Gemini rewrites the page seamlessly — merging new content from a different lecture into the existing page. No "Additional Content from..." blocks.

---

### `build_graph.py` — Knowledge Graph Generator

Scans all wiki pages, extracts `[[Wikilinks]]`, and builds an interactive graph.

```bash
python build_graph.py
```

- Output: `MBAWiki/assets/knowledge_graph.json`
- Validates all links (only includes edges where both source and target exist)
- Run this after processing to update the graph visualization at `/graph`

---

### `wiki_viewer/app.py` — Flask Wiki Server

Serves the wiki as a local website.

```bash
python wiki_viewer/app.py
# Open http://127.0.0.1:5000/
```

**Pages:**
| Route | Description |
|-------|-------------|
| `/` | Homepage — course grid with concept/case counts |
| `/course/<slug>` | All concepts and cases for a course |
| `/concept/<slug>` | Individual concept page with TOC, equations, related links |
| `/case/<slug>` | Case study page with discussion section |
| `/graph` | Interactive knowledge graph (D3.js force-directed) |

---

### Image Tagging (Optional)

Image tagging lets you associate extracted PDF charts/figures with specific concepts. The wiki viewer will auto-insert tagged images into the matching concept pages.

**This is entirely optional.** The wiki works perfectly without it.

```bash
# Step 1: Extract images during processing
python download_and_process.py --course "Microeconomics" --all --images

# Step 2: Initialize the tags file
python init_image_tags.py

# Step 3: Manually add captions to MBAWiki/assets/charts/image_tags.json
# Example:
# {
#   "Slides_Page15_Plot0.png": ["supply vs demand intersection"],
#   "Slides_Page22_Plot0.png": ["elastic vs inelastic comparison"]
# }

# Step 4: Auto-map captions to concepts (1 Gemini API call)
python tag_images.py --map

# Step 5: Verify mappings
python tag_images.py --status
```

| Script | Command | Description |
|--------|---------|-------------|
| `init_image_tags.py` | `python init_image_tags.py` | Scans charts folder, creates `image_tags.json` with empty entries |
| `tag_images.py` | `--list` | Show all images and their caption status |
| `tag_images.py` | `--map` | Map captions to concepts via Gemini (1 API call) |
| `tag_images.py` | `--status` | Show current image-to-concept mappings |

---

## Configuration

### `courses.json` — Course Definitions

Define your courses and where their materials are stored:

```json
{
  "Microeconomics": {
    "lectures_folder_id": "google-drive-folder-id-or-null",
    "cases_folder_id": "google-drive-folder-id-or-null",
    "transcripts_folder_id": "google-drive-folder-id-or-null",
    "seed_concepts": [
      "Supply and Demand",
      "Price Elasticity",
      "Opportunity Cost"
    ]
  }
}
```

- `lectures_folder_id`: Google Drive folder containing lecture PDFs (set to `null` for local files)
- `cases_folder_id`: Google Drive folder for case studies (optional)
- `transcripts_folder_id`: Google Drive folder for transcripts (optional)
- `seed_concepts`: Foundational concepts to create as stubs before processing (optional, max ~10)

### `course_groups.json` — Cross-Course Linking

Group related courses so concepts can link across course boundaries:

```json
{
  "Economics & Strategy": ["Microeconomics", "Financial Accounting"],
  "People & Organizations": ["Leading People"]
}
```

A course can belong to multiple groups. When processing, duplicate detection is tiered:
- **Same course**: Fuzzy matching (catches "Supply Curve" vs "The Supply Curve")
- **Same group**: Exact matching only (prevents false positives across courses)
- **Other courses**: Exact matching only

### `.env` — API Keys

```
Gemini_Api_key="your-gemini-api-key"
```

### Google Drive Setup (Optional)

If you want to auto-download materials from Google Drive:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable the Google Drive API
3. Create OAuth 2.0 credentials (Desktop application)
4. Download as `credentials/credentials.json`
5. On first run, a browser window opens for authentication — the token is saved to `credentials/token.json`

If you don't use Google Drive, just place your files locally and use `process_single_file.py` directly.

---

## Adapting for Your Own Use

KnowledgeWiki was built for MBA courses, but works with any academic material:

1. **Edit `courses.json`** — add your courses (e.g., "Organic Chemistry", "Constitutional Law", "Machine Learning")
2. **Edit `course_groups.json`** — group related courses (e.g., "Sciences": ["Chemistry", "Biology", "Physics"])
3. **Add seed concepts** — define foundational concepts for each course in `courses.json`
4. **Process your materials** — point it at your lecture PDFs and transcripts

The LLM prompt in `process_single_file.py` extracts concepts with definitions, key points, formulas, and examples — this structure works across disciplines. The wiki viewer, knowledge graph, and cross-linking all work automatically regardless of subject matter.

---

## Folder Structure

```
KnowledgeWiki/
├── courses.json                  # Course configuration
├── course_groups.json            # Cross-course grouping
├── processed_files.json          # Tracks processed files (auto-generated)
├── .env                          # API keys
├── requirements.txt              # Python dependencies
│
├── download_and_process.py       # Google Drive download + orchestration
├── process_single_file.py        # Core LLM extraction engine
├── build_graph.py                # Knowledge graph generator
├── tag_images.py                 # Image-to-concept mapping
├── init_image_tags.py            # Initialize image tags
│
├── MBAWiki/                      # Generated wiki content
│   ├── Concept-*.md              # Concept pages (auto-generated)
│   ├── Case-*.md                 # Case study pages (auto-generated)
│   └── assets/
│       ├── charts/               # Extracted PDF images
│       │   └── image_tags.json   # Image captions & mappings
│       └── knowledge_graph.json  # Graph data for D3 visualization
│
├── wiki_viewer/                  # Flask web application
│   ├── app.py                    # Web server entry point
│   ├── templates/                # HTML templates (Wikipedia-style)
│   ├── static/css/               # Stylesheets
│   └── utils/                    # Markdown parser, wikilink processor
│
├── Transcript_class_lecture/     # Downloaded files cache
│   └── <CourseName>/            # Organized by course
│
└── credentials/                  # Google Drive OAuth tokens
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Gemini_Api_Key not found` | Check your `.env` file has `Gemini_Api_key="..."` |
| Files skipped as "already processed" | Delete entries from `processed_files.json` to reprocess |
| Rate limit errors (429) | The system auto-retries with fallback models. If persistent, wait a few minutes |
| Equations not rendering | KaTeX is loaded via CDN — check your internet connection |
| Broken wikilinks | Run `python build_graph.py` — it filters invalid links. Ensure referenced concepts exist |
| Images not showing on concept pages | Run `python tag_images.py --status` to verify mappings |
| Google Drive auth fails | Delete `credentials/token.json` and re-authenticate |

---

## Cost Summary

| Component | Cost |
|-----------|------|
| Gemini API | Free (free tier) |
| Google Drive API | Free |
| Python + Flask | Free / open source |
| KaTeX (math rendering) | Free CDN |
| D3.js (knowledge graph) | Free CDN |
| **Total** | **$0** |

---

## License

MIT
