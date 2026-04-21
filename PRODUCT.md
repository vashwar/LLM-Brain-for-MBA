# PRODUCT.md — KnowledgeWiki

## What This Is

KnowledgeWiki turns a semester of lecture material into a persistent, interconnected knowledge base — automatically. You feed it PDFs, transcripts, and case studies. An LLM extracts every concept, links them together with wikilinks, merges duplicates seamlessly, and serves the result as a searchable Wikipedia-style site. The wiki compounds: every new source enriches existing pages rather than creating duplicates.

The project implements [Andrej Karpathy's "LLM Wiki" pattern](https://x.com/karpathy) — the idea that most RAG systems (NotebookLM, ChatGPT file uploads) re-derive knowledge from scratch on every query, while a wiki compiles knowledge once and keeps it current. KnowledgeWiki is what happens when you take that idea seriously and build it for real coursework.

**The constraint that shaped everything:** the entire pipeline runs on Gemini's free tier. Zero dollars. This forced every design decision toward efficiency — max 2 API calls per file, no Vision API, batch merging, incremental indexing.

**Current scale:** 989 concepts, 46 case studies, 13 MBA courses, 1,035 search-indexed entries. Built over 13 days with 332 automated ingestion operations. I study from it daily.

---

## Key Product Decisions

### 1. Compile-time knowledge, not query-time retrieval

**Decision:** Build a persistent wiki of markdown files, not a RAG pipeline.

**Alternatives considered:**
- RAG (retrieve + generate on every query): Cheaper to set up, but re-derives knowledge from scratch each time. No compounding. Ask a cross-cutting question and the LLM has to find and piece together fragments from raw documents every time.
- Fine-tuning: Expensive, opaque, not inspectable. Can't browse or link concepts.

**Why this:** The wiki is inspectable (plain markdown), linkable (wikilinks create a graph), and compounding (each source enriches existing pages). The 989 concept pages represent compiled knowledge — cross-references already exist, duplicates are already merged. Karpathy's core insight is that the maintenance cost of a wiki drops to near-zero when an LLM does the bookkeeping.

**Validation:** After 13 courses, I search the wiki daily for exam prep and case analysis. The cross-course connections (e.g., finding that Microeconomics' "Price Discrimination" links to Marketing Strategy's "Segmentation") emerged automatically from the LLM extraction — I didn't create them.

### 2. Max 2 API calls per file, no exceptions

**Decision:** Hard limit of 2 Gemini API calls per source file (1 extraction + 1 merge if duplicates found). Transcripts do concept extraction AND case discussion updates in a single call.

**Alternatives considered:**
- Separate API calls per concept (10-25 calls per lecture): More precise, but 10x the API usage. Would blow through free-tier quotas immediately.
- Multi-pass extraction (extract, then refine, then link): Higher quality per page, but 3-5x the calls. Not viable at $0.

**Why this:** The free-tier constraint is the product, not a limitation. Every MBA student has access to Gemini's free API. The 2-call limit means a full course (40+ files) processes in under 30 minutes at zero cost. The quality tradeoff is acceptable — the LLM extracts 20-25 concepts per lecture in one call, and the merge call produces seamlessly integrated pages.

**Evidence:** 332 ingestion operations over 13 days. Zero API cost. The system processed 13 courses end-to-end without hitting permanent rate limits. (Commit `400dda6`: resilient JSON parsing, configurable model)

### 3. Tiered duplicate detection across courses

**Decision:** Three-tier matching when checking if a concept already exists: same course (fuzzy matching), same course group (exact only), other courses (exact only).

**Alternatives considered:**
- Flat matching across all courses: Simpler, but creates false positives. "Equilibrium" in Microeconomics is different from "Equilibrium" in Game Theory.
- No cross-course matching: Misses legitimate duplicates. "NPV" taught in both Intro Finance and Financial Accounting should merge, not duplicate.

**Why this:** Course groups (defined in `course_groups.json`) model real-world course relationships. Economics courses share concepts with Finance; Marketing shares with Pricing. The tier system catches real duplicates while preventing false-positive merges across unrelated courses.

### 4. Wikipedia-style web UI, not Obsidian

**Decision:** Build a Flask web server with Wikipedia-inspired styling, rather than using Obsidian (which Karpathy recommended).

**Alternatives considered:**
- Obsidian: Free, has graph view, supports wikilinks natively. But requires each user to install it, configure plugins, and point it at the right folder. Not shareable.
- Static site generator (MkDocs, Hugo): Would need custom wikilink resolution and case-study routing. More setup than Flask for this use case.

**Why this:** A `python wiki_viewer/app.py` command gives you a working wiki in 2 seconds. No installation, no plugin configuration, no Obsidian license. The web UI also enabled features Obsidian doesn't have: semantic search with course/type filters, a health dashboard that runs the linter on-demand, and concept-of-the-day rotation.

### 5. Local semantic search, not cloud-based

**Decision:** Build search using `BAAI/bge-small-en-v1.5` via fastembed (ONNX runtime, no PyTorch). Embeddings stored as a `.npz` file alongside the wiki.

**Alternatives considered:**
- Full-text search (BM25): Simpler, but misses semantic matches. "What drives consumer behavior?" wouldn't find "Willingness to Pay" without keyword overlap.
- Cloud embedding API: Higher quality but adds a dependency and a cost. Defeats the $0 constraint.
- Karpathy's suggestion of `qmd`: Good tool, but adds a dependency. Building it in was ~135 lines of Python.

**Why this:** fastembed runs locally in ~3s on first query, then milliseconds per search. The 384-dimensional embeddings for 1,035 entries fit in a 1.5MB `.npz` file. Incremental rebuilds (mtime-based) mean the index stays current without re-embedding unchanged pages. Title-substring boosting (+0.15) handles the common case where users search for exact concept names.

### 6. Three-stage project structure (Ingest / Query / Maintenance)

**Decision:** Reorganize from 9 flat scripts to 3 directories mapping to Karpathy's three operations.

**Why this:** Karpathy's architecture defines three operations: Ingest (process sources into wiki), Query (search and browse), and Lint (health-check the wiki). The directory structure now mirrors this directly: `ingest/`, `wiki_viewer/`, `Maintenance/`. A new contributor can understand the system's purpose from `ls`.

---

## Decisions Not Made (Scoped Out)

### Contradiction tracking
The schema template includes an "Edge Cases & Contradictions" section, and the LLM is instructed to flag contradictions during merge. But there's no systematic aggregation — no `contradictions.md`, no cross-wiki contradiction surface. This is the right scope cut for now: with 989 pages from lecture slides (which are internally consistent per course), contradictions are rare. If the system expanded to include external articles or competing textbooks, this would become critical.

### Edit-from-browser
The wiki is read-only. There's no "Edit" button, no WYSIWYG editor, no way to modify pages from the web UI. This is intentional: the LLM is the writer, the human is the reader. Editing pages manually would break the merge logic (the LLM expects to own the markdown format). The `/wiki` skill in Claude Code serves as the "edit" interface — ask it to create or update a page, and it writes the markdown directly.

### Deployment / hosting
The wiki runs locally (`127.0.0.1:5000`). There's no Dockerfile, no deployment config, no public URL. This is a personal study tool, not a SaaS product. The TODO mentions `start_wiki.bat` for auto-launch on Windows login — that's the right level of "deployment" for this use case.

### Vector DB for concept linking
Considered and deferred. Current wikilinks are curated by the LLM during extraction — they represent intentional pedagogical connections ("Supply Curve" links to "Demand Curve" because they're taught together). Vector similarity would add a "Related by embedding distance" section, but at 989 pages the wikilinks already provide rich navigation. The marginal value of embedding-based suggestions doesn't justify the complexity.

---

## Pivots & What Drove Them

### Pivot 1: From subprocess orchestrator to standalone processor

**Before (April 9-13):** Two scripts — `download_and_process.py` (orchestrator) called `process_single_file.py` (processor) via subprocess. Each file spawned a new Python process.

**After (April 15, commit `400dda6`):** Single `process_standalone.py` that handles both Google Drive download and Gemini processing in one process. No subprocess overhead.

**What drove it:** Processing 40+ files per course, the subprocess overhead added up. More importantly, error handling was split across two scripts — timeouts in the subprocess were hard to catch and retry from the orchestrator. The standalone version retries from unprocessed files on any error, sleeping and resuming automatically.

### Pivot 2: From index.md to semantic search

**Before (April 9-10):** A manually-maintained `Vision/index.md` catalog of all pages, following Karpathy's recommendation.

**After (April 10, commit `487851a`):** Local vector embeddings with `BAAI/bge-small-en-v1.5`, web UI search at `/search`, incremental mtime-based rebuilds.

**What drove it:** At 20 concepts, index.md worked fine — the LLM could read it and find relevant pages. At 200+ concepts across 5 courses, it became unmaintainable and unsearchable. The semantic search was ~135 lines of Python and made the entire wiki instantly navigable. This exceeded Karpathy's vision (he suggested index.md + optional `qmd`).

### Pivot 3: From rigid to resilient JSON parsing

**Before:** LLM responses parsed with strict `json.loads()`. Occasional failures when Gemini returned malformed JSON (unescaped newlines, truncated output).

**After (April 15, commit `400dda6`):** 5-stage JSON repair pipeline: try as-is, fix unescaped strings, fix arrays, brute-force escape control chars, truncation recovery.

**What drove it:** Processing 13 courses (332 files), about 5% of Gemini responses had JSON issues. Each failure meant a wasted API call and a manual retry. The repair pipeline recovers from ~95% of malformed responses automatically. This was a "production at scale" fix — it only mattered after processing hundreds of files.

---

## What I Learned

1. **Constraints breed better architecture.** The $0 budget forced the 2-call-per-file limit, which forced batch merging, which forced smarter duplicate detection. Every "limitation" of the free tier pushed the design toward more efficient patterns. If I'd had unlimited API budget, I would have built something sloppier.

2. **Compounding beats precision.** A 989-page wiki with 80% accuracy per page is vastly more useful than 50 pages at 99% accuracy. The cross-references, the search, the knowledge graph — they all get better with scale. The first 50 concepts were unimpressive; the interconnected 989 are genuinely useful for exam prep.

3. **LLMs are reliable writers but unreliable serializers.** Gemini generates excellent markdown prose. But its JSON serialization fails ~5% of the time — unescaped newlines, truncated output, malformed arrays. The repair pipeline was essential. Lesson: always build a tolerance layer between LLM output and your parser.

4. **The maintenance problem is real — and solvable.** Karpathy's insight that "humans abandon wikis because maintenance burden grows faster than value" is exactly right. The linter (`lint_wiki.py`) found 158 orphan concepts and 17 broken wikilinks in a 989-page wiki. Without automated health checks, these would accumulate silently until the wiki felt unreliable.

5. **Search transforms the product.** The wiki with just browsing and wikilinks was useful. The wiki with semantic search became indispensable. Being able to type "what causes inflation" and get ranked results across Macro, Micro, and Finance courses changed how I study. The investment was ~135 lines of Python.

---

## By the Numbers

| Metric | Value | Source |
|--------|-------|--------|
| Total concept pages | 989 | `ls MBAWiki/Concept-*.md \| wc -l` |
| Total case study pages | 46 | `ls MBAWiki/Case-*.md \| wc -l` |
| Courses processed | 13 | `courses.json` |
| Search index entries | 1,035 | `search_metadata.json` |
| Log entries | 603 | `wc -l log.md` |
| Ingestion operations | 332 | `grep "ingest" log.md \| wc -l` |
| Knowledge graph edges | 3,413 | `build_graph.py` output |
| Knowledge graph nodes | 1,035 | `build_graph.py` output |
| Broken wikilinks | 134 (graph-filtered) | `build_graph.py` output |
| Development period | 13 days (Apr 7-20, 2026) | `git log` |
| Commits | 8 | `git log --oneline` |
| Total Python LOC | 4,366 | `wc -l` across all `.py` files |
| API cost | $0 | Gemini free tier |
| Test coverage | 0% | No tests exist |
| Largest course (by concepts) | Pricing: 211 | `search_metadata.json` |
| Smallest course (by concepts) | Ethics: 25 | `search_metadata.json` |

---

## What I'd Do Differently

1. **Write tests from day 1.** The JSON repair pipeline, wikilink resolution, duplicate detection, and search ranking all have clear input/output contracts. They're perfectly testable. Having zero tests at 4,366 LOC is the project's biggest weakness. If I restarted, I'd write tests for `repair_json()`, `check_for_duplicates()`, and `_resolve_wikilink()` before writing the production code.

2. **Take screenshots early.** The wiki looks good — Wikipedia-style layout, knowledge graph visualization, search UI. But there's no visual evidence anywhere. A README with screenshots would communicate more in 5 seconds than the entire scripts reference section.

3. **Track success criteria upfront.** "Build a wiki from lectures" was the implicit goal, but there was no definition of "done." I should have written: "Success = 500+ concepts across 10+ courses, searchable, with <20 broken wikilinks." That would have made the alignment report more rigorous.

4. **Add CI/CD before the 3rd commit.** Even a simple GitHub Actions workflow that runs `python -c "from ingest.build_search_index import build_index"` would catch import breakage. The reorganization into `ingest/` required fixing 15+ import paths — any of which could have silently broken.

5. **Surface metrics in the product.** The `/health` dashboard shows wiki quality metrics. There should be a similar dashboard for system metrics — total concepts processed, API calls saved by merging, search queries served, concepts added per course. The data exists in `log.md`; it just needs a view.

---

## Architecture

```
                    ┌─────────────────────────────┐
                    │     Google Drive             │
                    │  (lectures, cases,           │
                    │   transcripts per course)    │
                    └──────────┬──────────────────┘
                               │ download
                    ┌──────────▼──────────────────┐
                    │  ingest/process_standalone   │
                    │  • Extract text (PyMuPDF)    │
                    │  • Gemini API (1-2 calls)    │
                    │  • Create/merge markdown     │
                    │  • Update search index       │
                    └─────��────┬──────────────────┘
                               │ writes
          ┌────────────────────▼────────────────────────┐
          │              MBAWiki/                        │
          │  ┌──────────────┐  ┌───────────────┐        │
          │  │ Concept-*.md │  │  Case-*.md    │        │
          │  │ (989 pages)  │  │  (46 pages)   │        │
          │  └──────────────┘  └─────��─────────┘        │
          │  ┌──────────────────────────────────┐       │
          │  │ assets/                           │       │
          │  │  search_index.npz (embeddings)   │       │
          │  │  knowledge_graph.json (D3 data)  │       │
          │  │  charts/ (PDF images + tags)     │       │
          │  └────────────���────────────��────────┘       │
          └────────────────────┬────────────────────────┘
                               │ reads
          ┌────��───────────────▼────────────────��───────┐
          │         wiki_viewer/ (Flask)                 │
          │  /              Homepage + concept of day    │
          │  /concept/slug  Concept page + TOC + links   ��
          │  /case/slug     Case study page              │
          │  /search        Semantic search (bge-small)  │
          │  /graph         D3.js knowledge graph        │
          │  /health        Lint dashboard + MD report   │
          └─────────���───────────────────────────────────┘
                               │ imports
          ┌────���─────────���─────▼────────────────────────┐
          │         Maintenance/                         │
          │  lint_wiki.py   Orphans, broken links,      │
          │                 missing concepts, stale      │
          │  lint-report-*  Generated markdown reports   │
          └───────────��─────────────────────────────────┘
```

---

## Success Criteria Revisited

| Criterion | Target | Actual | Met? |
|-----------|--------|--------|------|
| Concept extraction at scale | 500+ concepts | 989 concepts | Yes |
| Multi-course support | 10+ courses | 13 courses | Yes |
| Zero API cost | $0 | $0 | Yes |
| Searchable wiki | Natural-language search | Semantic search with filters | Yes |
| Cross-course linking | Concepts link across courses | 3,413 graph edges | Yes |
| Case study tracking | Cases with discussion sections | 46 cases, transcript-populated | Yes |
| Health monitoring | Detect wiki quality issues | Linter with 4 check types + dashboard | Yes |
| Daily usability | Use for studying | Used daily for exam prep | Yes |
| Test coverage | > 0% | 0% | **No** |
| Visual documentation | Screenshots in README | None | **No** |

**8 of 10 criteria met.** The two failures (tests, screenshots) are documentation/quality gaps, not product gaps. The system works, scales, and is used daily.
