# Wiki Viewer (Query Stage)

Flask web application that serves the KnowledgeWiki as a Wikipedia-style local website.

## Features

- **Wikipedia-style UI** — clean typography, TOC sidebar, responsive layout
- **Smart Wikilinks** — `[[Concept Name]]` auto-links to existing pages; broken links shown in red
- **Semantic Search** — local embeddings via BAAI/bge-small-en-v1.5 (ONNX, no PyTorch)
- **Knowledge Graph** — interactive D3.js force-directed visualization
- **Health Dashboard** — runs wiki linter checks, generates markdown reports
- **LaTeX Rendering** — equations via KaTeX CDN
- **Course Organization** — concepts grouped by course with cross-course linking
- **Case Studies** — dedicated pages with discussion sections from transcripts
- **Concept of the Day** — deterministic daily rotation on the homepage
- **Tagged Images** — auto-inserted into concept pages from `image_tags.json`

## Running

```bash
python wiki_viewer/app.py
# Open http://127.0.0.1:5000/
```

## Configuration

The viewer reads `WIKI_DIR` from `.env` (defaults to `MBAWiki` relative to the project root). Edit `wiki_viewer/config.py` for Flask settings (host, port, debug mode).

## Routes

| Route | Description |
|-------|-------------|
| `/` | Homepage — course grid, concept of the day, did you know |
| `/course/<slug>` | All concepts and cases for a course |
| `/concept/<slug>` | Individual concept page with TOC, equations, related links |
| `/case/<slug>` | Case study page with discussion section |
| `/cases` | All case studies across all courses |
| `/graph` | Interactive knowledge graph (D3.js force-directed) |
| `/search?q=...&course=...&type=...` | Semantic search with filters |
| `/health` | Health dashboard — orphans, broken links, stale content |
| `/assets/charts/<filename>` | Serve chart images |

## Project Structure

```
wiki_viewer/
├── app.py                          # Flask application & routes
├── config.py                       # Configuration (WIKI_DIR from .env)
├── utils/
│   ├── markdown_parser.py          # Markdown -> HTML conversion with TOC
│   ├── wikilink_processor.py       # [[Wikilink]] -> HTML link conversion
│   └── search.py                   # SearchIndex class (cosine similarity)
├── templates/
│   ├── base.html                   # Base layout with header/footer
│   ├── index.html                  # Homepage with course grid
│   ├── concept.html                # Concept/case page
│   ├── course.html                 # Course page
│   ├── cases.html                  # All cases page
│   ├── search.html                 # Search results
│   ├── graph.html                  # Knowledge graph visualization
│   ├── health.html                 # Health dashboard
│   ├── 404.html                    # Not found page
│   └── 500.html                    # Server error page
└── static/
    └── css/
        └── wikipedia.css           # Wikipedia-inspired styling
```

## Key Components

### Wikilink Processor (`utils/wikilink_processor.py`)

At startup, scans all `Concept-*.md` and `Case-*.md` files to build a title-to-slug mapping. Converts `[[Supply Curve]]` to `<a href="/concept/supply-curve">Supply Curve</a>`. Supports aliases (abbreviations in parentheses) and fuzzy matching. Broken links render as red text with tooltips.

### Search Index (`utils/search.py`)

Loads pre-built embeddings from `MBAWiki/assets/search_index.npz` + `search_metadata.json`. The embedding model (`BAAI/bge-small-en-v1.5`) is lazy-loaded on first search query (~3s cold start). Supports course and type filters, with a +0.15 title-substring boost.

### Health Dashboard (`/health`)

Imports `Maintenance/lint_wiki.py` to run structural checks:
- Orphan pages (0 inbound links)
- Broken wikilinks (404 targets)
- Missing concepts (frequently mentioned but no dedicated page)
- Stale content (not updated recently)

Also saves a markdown report to `Maintenance/lint-report-YYYY-MM-DD.md` on each visit.

## License

Part of the KnowledgeWiki project. See parent directory for license info.
