# LLM Wiki Schema & System Instructions
*Inspired by Andrej Karpathy's "LLM Wiki" pattern — a persistent, compounding knowledge base maintained by LLMs.*

## The Three-Layer Architecture

Following Karpathy's vision, KnowledgeWiki operates in three layers:

1. **Raw Sources** (immutable)
   - Lecture PDFs, transcripts, case studies in `Transcript_class_lecture/`
   - These are the source of truth — the LLM reads but never modifies them

2. **The Wiki** (LLM-maintained)
   - `Concept-*.md` files — enduring concepts, frameworks, definitions
   - `Case-*.md` files — case studies with strategic dilemmas
   - Interconnected via `[[Wikilinks]]`, automatically cross-referenced
   - This is the compounding artifact — it gets richer with every source added

3. **The Schema** (this file)
   - Workflow instructions, page templates, and conventions
   - Tells the LLM how to maintain the wiki with consistency and discipline

---

## Core Principles

**Extract enduring concepts, not chronological summaries**
- Do not write "Lecture 5 covered X and Y and Z."
- Instead: "Here's what concept X is, why it matters, where it's taught, and how it connects to other concepts."

**The wiki is a persistent artifact, not a chat**
- Every ingestion compounds the knowledge base
- New sources update existing pages, not create duplicates
- Cross-references are maintained automatically
- The wiki gets better with every addition

**You (LLM) do the bookkeeping; the human curates and directs**
- Human's job: source materials, ask questions, guide analysis
- LLM's job: extract, synthesize, cross-reference, maintain consistency, flag contradictions

**Use wikilinks liberally**
- Every reference to another concept becomes `[[Concept Name]]`
- This creates the interconnected web that Karpathy envisioned

---

## Workflow 1: Concept Extraction (from lectures, transcripts)

**Trigger:** Process a new lecture PDF or transcript file

**Instructions:**
1. Read the raw material for conceptual pillars and frameworks (not chronological summaries)
2. For each distinct concept, create a new `Concept-{slug}.md` file OR update existing one
3. If a concept already exists, seamlessly merge new content — don't create duplicates
4. Use the template below

**Template:**
```markdown
# {Concept Name}

**Course:** {Course Name}
**Sources:** [[Lecture: Week X]], [[Transcript: Date]]
**Status:** Active

## Definition
{Clear, academic definition. Why does this concept matter?}

## Key Principles
- {Principle 1: explanation}
- {Principle 2: explanation}

## Formulas & Frameworks
{Any mathematical formulas, step-by-step processes, or analytical frameworks}

## Real-World Applications
- {Company/case example 1}
- {Company/case example 2}

## Related Concepts
- [[Concept A]] — how it connects
- [[Concept B]] — how it differs

## Edge Cases & Contradictions
{If different sources define this differently, note it here. Don't suppress contradictions — highlight them.}
```

**Merging Rule:** If concept already exists, integrate new applications and sources. Keep all historical definitions. Flag contradictions explicitly.

---

## Workflow 2: Case Study Processing

**Trigger:** Process a new case study PDF

**Instructions:**
1. Extract the core dilemma, stakeholders, financial constraints
2. Create `Case-{slug}.md` with template below
3. Mark as `#unresolved` until transcripts populate the class discussion

**Template:**
```markdown
# Case: {Case Name}

**Source:** {PDF filename}
**Related Concepts:** [[Concept A]], [[Concept B]]
**Status:** #unresolved

## Core Dilemma
{2-3 sentences: what's the strategic/leadership/operational problem?}

## Key Stakeholders & Incentives
- **{Stakeholder Name}** ({role}) — motivated by {incentive}
- **{Stakeholder Name}** ({role}) — motivated by {incentive}

## Financial Context
- Revenue: {amount}
- Margins: {percentage}
- Key constraints: {constraints}

## Strategic Questions
{What is the protagonist trying to decide?}

## Class Discussion & Takeaways
{Populated by transcript processing — leave blank initially}

## Related Concepts Demonstrated
- [[Concept A]] — {how the case illustrates it}
- [[Concept B]] — {how the case illustrates it}
```

---

## Workflow 3: Transcript Dual-Processing

**Trigger:** Process a lecture transcript

**Instructions:**
1. Extract new concepts (see Workflow 1)
2. Find matching case study pages; append to their "Class Discussion & Takeaways" section
3. Update any related concept pages with new applications
4. Single API call does both extraction AND case discussion updates

---

## Workflow 4: Image Tagging (Optional)

**Trigger:** User manually adds captions to `image_tags.json`

**Instructions:**
1. Map image captions to concepts via Gemini (1 API call)
2. Wiki viewer auto-inserts tagged images into matching concept pages
3. Images enhance conceptual understanding — they're not required, but valuable

---

## Universal Merge & Update Protocol

**Trigger:** When processing a source that touches an existing concept page

**Instructions:**
1. Read the EXISTING page
2. Read the NEW extracted content
3. Synthesize:
   - Keep all historical definitions
   - Add new applications and examples
   - Update "Related Concepts" if new connections emerged
   - If new source CONTRADICTS old claim, flag it explicitly under "Edge Cases & Contradictions"
4. Output the complete, merged page

**Key Rule:** Never delete. Only append, synthesize, and clarify. Contradictions are features, not bugs.

---

## Indexing & Navigation

**index.md** (content-oriented)
- Catalog of all concept and case pages
- Organized by category (Concepts, Cases, Courses)
- Updated after every ingestion
- LLM uses this to discover relevant pages before drilling into details

**log.md** (chronological, append-only)
- Record of all ingestions, updates, and linting passes
- Each entry: `## [YYYY-MM-DD] {action} | {source}`
- Helps track wiki evolution and understand what's been done
- Example: `## [2026-04-10] ingest | Microeconomics Week 1 Lecture`

---

## Linting & Health Checks (Periodic)

Run periodically to keep wiki healthy:
- **Orphan pages:** Concepts with no inbound wikilinks
- **Broken links:** Wikilinks that reference non-existent pages
- **Missing cross-references:** Related concepts not linked
- **Contradictions:** Different sources claiming different facts (keep them, but flag them)
- **Stale content:** Concepts that haven't been updated in weeks

---

## Why This Works

The tedious part of maintaining a knowledge base is **bookkeeping** — updating cross-references, keeping summaries current, maintaining consistency. Humans abandon wikis because this burden grows faster than value.

LLMs don't get bored. They handle all the maintenance. The human's job is curation and direction. The result is a wiki that compounds rather than decays.