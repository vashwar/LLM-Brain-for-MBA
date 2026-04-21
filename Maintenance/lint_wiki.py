"""Wiki linter — structural health checks for the knowledge base.

Checks:
  1. Orphan pages     — concepts/cases with 0 inbound wikilinks
  2. Broken wikilinks — [[links]] pointing to non-existent pages
  3. Missing concepts  — terms mentioned frequently but lacking a dedicated page
  4. Stale content     — pages not updated since newer sources were ingested

Usage:
  python lint_wiki.py              # full report (console + markdown)
  python lint_wiki.py --orphans    # only orphan pages
  python lint_wiki.py --broken     # only broken wikilinks
  python lint_wiki.py --missing    # only missing concepts
  python lint_wiki.py --stale      # only stale content
  python lint_wiki.py --no-save    # console only, don't write report file
"""

import argparse
import re
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = PROJECT_ROOT / "MBAWiki"
MAINTENANCE_DIR = Path(__file__).resolve().parent
CONCEPT_PREFIX = "Concept-"
CASE_PREFIX = "Case-"
SUFFIX = ".md"
LOG_FILE = PROJECT_ROOT / "log.md"

# Minimum number of plain-text mentions to flag as a missing concept
MISSING_MENTION_THRESHOLD = 3

# Terms to ignore in missing-concepts check (course names, source artifacts, etc.)
IGNORE_TERMS = {
    # Course names and source file fragments
    "leading people", "overview chapter", "slides week", "intro finance",
    "financial accounting", "global economy", "united states",
    "marketing strategy", "business decision making", "business decision",
    "ethics toolkit", "class slides",
    # Course names and lecture titles that appear in metadata/source fields
    "introduction to finance", "economics for business decision making",
    "economics for business decision", "macroeconomics in the global economy",
    "data and decision", "data and decisions",
    "ethics and responsibility in business",
    "process analysis and process choice",
    "business models for sustainability",
    "responsiveness in services",
    "revenue management",
    # Common non-concept phrases
    "nobel prize", "steve jobs", "new york", "san francisco",
    "silicon valley", "wall street", "federal reserve",
    "world war", "united kingdom", "south korea", "north america",
    "real world", "long run", "short run", "key takeaway",
    "key takeaways", "class discussion", "case study",
    "lecture notes", "review session",
}

# Stale threshold: pages older than this many days before the latest ingest
STALE_DAYS = 5

# ── Helpers ─────────────────────────────────────────────────────────────────

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
PAREN_RE = re.compile(r"\(([^)]+)\)")


def build_alias_map(title_lookup, pages):
    """Build alias map matching the wikilink processor's logic."""
    alias_map = {}  # alias.lower() -> original title

    for title, info in pages.items():
        # Abbreviation aliases: "Net Present Value (NPV)" -> "NPV"
        matches = PAREN_RE.findall(title)
        for abbrev in matches:
            abbrev = abbrev.strip()
            if abbrev.lower() not in title_lookup:
                alias_map[abbrev.lower()] = title
        # Title without parenthetical: "Net Present Value (NPV)" -> "Net Present Value"
        stripped = PAREN_RE.sub("", title).strip()
        if stripped and stripped != title and stripped.lower() not in title_lookup:
            alias_map[stripped.lower()] = title

        # Slug alias: "consumption-smoothing" -> title
        slug = info["slug"]
        alias_map[slug.lower()] = title

    return alias_map


def resolve_link(link_text, title_lookup, alias_map):
    """Resolve a wikilink to a title, using exact match, aliases, then prefix match."""
    link_lower = link_text.lower()

    # Exact case-insensitive title match
    if link_lower in title_lookup:
        return title_lookup[link_lower]

    # Alias match
    if link_lower in alias_map:
        return alias_map[link_lower]

    # Prefix match — link text is the start of an existing title
    # e.g., "Equality vs. Equity" matches "Equality vs. Equity vs. Justice"
    link_norm = link_lower.replace("-", " ")
    best_match = None
    best_len = 0
    for title_lower, title in title_lookup.items():
        title_norm = title_lower.replace("-", " ")
        if title_norm.startswith(link_norm) and len(link_norm) >= len(title_norm) * 0.5:
            if len(title) > best_len:
                best_match = title
                best_len = len(title)

    return best_match


def read_title(filepath):
    """Extract the H1 title from the first line of a markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
        if first_line.startswith("# "):
            return first_line[2:].strip()
    except Exception:
        pass
    return None


def read_course(filepath):
    """Extract the course name from the metadata block."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i > 10:
                    break
                if line.strip().startswith("**Course:**"):
                    return line.split("**Course:**")[1].strip().rstrip("*")
    except Exception:
        pass
    return "Unknown"


def slug_from_filename(filename, prefix):
    """Concept-Some-Topic.md -> Some-Topic"""
    return filename[len(prefix):-len(SUFFIX)]


def read_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


# ── Scan ────────────────────────────────────────────────────────────────────

def scan_wiki():
    """Build maps of all pages, their wikilinks, and their metadata."""

    pages = {}           # title -> {path, slug, type, mtime, course}
    title_lookup = {}    # title.lower() -> title

    for prefix, ptype in [(CONCEPT_PREFIX, "concept"), (CASE_PREFIX, "case")]:
        for fp in sorted(WIKI_DIR.glob(f"{prefix}*{SUFFIX}")):
            title = read_title(fp)
            if not title:
                continue
            pages[title] = {
                "path": fp,
                "slug": slug_from_filename(fp.name, prefix),
                "type": ptype,
                "mtime": os.path.getmtime(fp),
                "course": read_course(fp),
            }
            title_lookup[title.lower()] = title

    # Build alias map for fuzzy resolution
    alias_map = build_alias_map(title_lookup, pages)

    # Extract wikilinks from every page
    outgoing = {}                    # title -> set of raw link targets
    inbound = defaultdict(set)       # title -> set of pages linking TO it
    broken = defaultdict(list)       # source title -> [broken link text]
    body_texts = {}                  # title -> full content

    for title, info in pages.items():
        content = read_file(info["path"])
        body_texts[title] = content

        links = set(WIKILINK_RE.findall(content))
        outgoing[title] = links

        for link_text in links:
            resolved_title = resolve_link(link_text.strip(), title_lookup, alias_map)
            if resolved_title:
                if resolved_title != title:
                    inbound[resolved_title].add(title)
            else:
                broken[title].append(link_text.strip())

    return pages, title_lookup, inbound, broken, body_texts


# ── Checks ──────────────────────────────────────────────────────────────────

def check_orphans(pages, inbound):
    """Find pages with 0 inbound wikilinks, grouped by type."""
    orphan_concepts = []
    orphan_cases = []
    for title, info in sorted(pages.items()):
        if title not in inbound or len(inbound[title]) == 0:
            entry = (title, info["course"], info["path"].name)
            if info["type"] == "case":
                orphan_cases.append(entry)
            else:
                orphan_concepts.append(entry)
    return orphan_concepts, orphan_cases


def check_broken(broken):
    """Collect broken wikilinks and group by target to find common patterns."""
    # target -> list of source pages
    by_target = defaultdict(list)
    for source_title, links in broken.items():
        for link in links:
            by_target[link].append(source_title)

    results = []
    for target, sources in sorted(by_target.items(), key=lambda x: -len(x[1])):
        results.append((target, sorted(sources)))
    return results


def check_missing(pages, title_lookup, body_texts):
    """Find terms mentioned frequently in body text but lacking a dedicated page.

    Filters out course names, source file artifacts, and short/generic phrases.
    """
    existing_lower = set(title_lookup.keys())

    # Auto-detect course names from pages and add to ignore set
    course_names = set()
    for info in pages.values():
        course = info.get("course", "")
        if course and course != "Unknown":
            course_names.add(course.lower())
            # Also add substrings (e.g., "Data and Decision" from "Data and Decision Making")
            for word in ["in the", "for", "to"]:
                if word in course.lower():
                    parts = course.lower().split(word)
                    for p in parts:
                        p = p.strip()
                        if len(p) > 8:
                            course_names.add(p)

    # Capitalized multi-word phrases (likely concept names)
    candidate_re = re.compile(r"\b([A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|of|and|the|in|for|vs\.|to|a|an))*(?:\s+[A-Z][a-z]+))\b")

    mention_counts = defaultdict(set)  # term -> set of pages mentioning it

    for title, content in body_texts.items():
        # Strip wikilinks, headings, metadata, and markdown formatting
        plain = WIKILINK_RE.sub("", content)
        plain = re.sub(r"^#+\s+.*$", "", plain, flags=re.MULTILINE)
        plain = re.sub(r"^\*\*[^*]+\*\*:.*$", "", plain, flags=re.MULTILINE)
        plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)  # strip md links

        for match in candidate_re.finditer(plain):
            term = match.group(1).strip()
            term_lower = term.lower()

            # Skip existing pages
            if term_lower in existing_lower:
                continue
            # Skip ignored terms and course names
            if term_lower in IGNORE_TERMS:
                continue
            if term_lower in course_names:
                continue
            # Skip if term is a substring of any course name or vice versa
            if any(term_lower in cn or cn in term_lower for cn in course_names):
                continue
            # Skip short terms (< 2 words or < 10 chars)
            if len(term) < 10 or " " not in term:
                continue
            # Skip terms that look like proper names (First Last, two words only)
            words = term.split()
            if len(words) == 2 and all(w[0].isupper() and w[1:].islower() for w in words):
                # Could be a person's name — skip unless it has concept-like words
                concept_words = {"theory", "effect", "model", "law", "rule", "bias",
                                 "curve", "analysis", "cost", "value", "rate", "index",
                                 "equilibrium", "pricing", "strategy", "framework"}
                if not any(w.lower() in concept_words for w in words):
                    continue

            mention_counts[term].add(title)

    # Filter and sort
    missing = []
    for term, mentioning_pages in sorted(mention_counts.items(),
                                          key=lambda x: -len(x[1])):
        if len(mentioning_pages) >= MISSING_MENTION_THRESHOLD:
            missing.append((term, len(mentioning_pages), list(mentioning_pages)[:3]))

    return missing[:30]


def check_stale(pages):
    """Find pages not modified in the last STALE_DAYS days, grouped by course."""
    now = datetime.now().timestamp()
    threshold = now - (STALE_DAYS * 86400)

    stale_by_course = defaultdict(list)
    for title, info in sorted(pages.items()):
        if info["mtime"] < threshold:
            dt = datetime.fromtimestamp(info["mtime"]).strftime("%Y-%m-%d")
            stale_by_course[info["course"]].append((title, info["type"], dt))

    return stale_by_course


# ── Report ──────────────────────────────────────────────────────────────────

def build_report(orphan_concepts, orphan_cases, broken_links, missing, stale_by_course, pages):
    """Build the report as a list of lines (used for both console and markdown)."""

    total_concepts = sum(1 for p in pages.values() if p["type"] == "concept")
    total_cases = sum(1 for p in pages.values() if p["type"] == "case")
    total_wikilinks = 0
    for title, info in pages.items():
        content = read_file(info["path"])
        total_wikilinks += len(WIKILINK_RE.findall(content))
    total_stale = sum(len(v) for v in stale_by_course.values())

    lines = []
    now_str = datetime.now().strftime("%B %d, %Y at %H:%M")

    lines.append(f"# Wiki Lint Report")
    lines.append(f"")
    lines.append(f"**Generated:** {now_str}")
    lines.append(f"**Scope:** {total_concepts} concepts, {total_cases} cases, ~{total_wikilinks} wikilinks")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # ── Health Score ────────────────────────────────────────────────────
    orphan_pct = (len(orphan_concepts) + len(orphan_cases)) / max(len(pages), 1) * 100
    broken_count = sum(len(sources) for _, sources in broken_links)
    health = 10
    health -= min(3, orphan_pct / 15)       # lose up to 3 for orphans
    health -= min(3, broken_count / 15)      # lose up to 3 for broken links
    health -= min(2, len(missing) / 10)      # lose up to 2 for missing concepts
    health -= min(2, total_stale / 200)      # lose up to 2 for stale
    health = max(0, round(health, 1))

    lines.append(f"## Health Score: {health}/10")
    lines.append(f"")
    lines.append(f"| Check | Count | Status |")
    lines.append(f"|-------|-------|--------|")
    lines.append(f"| Orphan concepts | {len(orphan_concepts)} | {'Good' if len(orphan_concepts) < 20 else 'Needs attention'} |")
    lines.append(f"| Orphan cases | {len(orphan_cases)} | {'Good' if len(orphan_cases) < 5 else 'Expected (cases rarely linked)'} |")
    lines.append(f"| Broken wikilinks | {broken_count} | {'Good' if broken_count < 5 else 'Fix these'} |")
    lines.append(f"| Missing concepts | {len(missing)} | {'Good' if len(missing) < 5 else 'Review candidates'} |")
    lines.append(f"| Stale pages | {total_stale} | {'Good' if total_stale < 50 else 'Informational'} |")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # ── Broken Wikilinks ───────────────────────────────────────────────
    lines.append(f"## Broken Wikilinks ({broken_count} total)")
    lines.append(f"")
    if broken_links:
        lines.append(f"Links that produce 404s. Grouped by target — fix the most-referenced first.")
        lines.append(f"")
        lines.append(f"| Missing Target | Referenced By | Fix |")
        lines.append(f"|----------------|-------------- |-----|")
        for target, sources in broken_links:
            source_list = ", ".join(sources[:3])
            if len(sources) > 3:
                source_list += f" (+{len(sources)-3} more)"
            lines.append(f"| `[[{target}]]` | {source_list} | ? |")
    else:
        lines.append(f"None found!")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # ── Orphan Pages ───────────────────────────────────────────────────
    lines.append(f"## Orphan Concepts ({len(orphan_concepts)} pages)")
    lines.append(f"")
    if orphan_concepts:
        lines.append(f"Concept pages that no other page links to. These are invisible to browsing.")
        lines.append(f"")

        # Group by course
        by_course = defaultdict(list)
        for title, course, fname in orphan_concepts:
            by_course[course].append((title, fname))

        for course in sorted(by_course.keys()):
            items = by_course[course]
            lines.append(f"### {course} ({len(items)} orphans)")
            lines.append(f"")
            for title, fname in items:
                lines.append(f"- {title}")
            lines.append(f"")
    else:
        lines.append(f"None found!")
    lines.append(f"")

    if orphan_cases:
        lines.append(f"## Orphan Cases ({len(orphan_cases)} pages)")
        lines.append(f"")
        lines.append(f"Cases are rarely wikilinked from concept pages. This is expected.")
        lines.append(f"")
        for title, course, fname in orphan_cases:
            lines.append(f"- {title}")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"")

    # ── Missing Concepts ───────────────────────────────────────────────
    lines.append(f"## Potential Missing Concepts ({len(missing)} candidates)")
    lines.append(f"")
    if missing:
        lines.append(f"Terms mentioned in {MISSING_MENTION_THRESHOLD}+ pages but lacking a dedicated page.")
        lines.append(f"")
        lines.append(f"| Term | Mentions | Example Pages |")
        lines.append(f"|------|----------|---------------|")
        for term, count, examples in missing:
            example_str = ", ".join(examples[:2])
            lines.append(f"| {term} | {count} | {example_str} |")
    else:
        lines.append(f"None found!")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # ── Stale Content ──────────────────────────────────────────────────
    lines.append(f"## Stale Content ({total_stale} pages, >{STALE_DAYS} days old)")
    lines.append(f"")
    if stale_by_course:
        lines.append(f"Pages not modified in the last {STALE_DAYS} days. This is informational —")
        lines.append(f"many pages are complete after initial processing and don't need updates.")
        lines.append(f"")
        for course in sorted(stale_by_course.keys()):
            items = stale_by_course[course]
            lines.append(f"### {course} ({len(items)} stale)")
            lines.append(f"")
            for title, ptype, dt in items[:10]:
                lines.append(f"- [{ptype}] {title} (last modified: {dt})")
            if len(items) > 10:
                lines.append(f"- ... and {len(items) - 10} more")
            lines.append(f"")
    else:
        lines.append(f"None found!")

    return "\n".join(lines)


# ── Console Output ──────────────────────────────────────────────────────────

def print_console(orphan_concepts, orphan_cases, broken_links, missing, stale_by_course, pages):
    """Print a concise console summary."""
    total_concepts = sum(1 for p in pages.values() if p["type"] == "concept")
    total_cases = sum(1 for p in pages.values() if p["type"] == "case")
    broken_count = sum(len(sources) for _, sources in broken_links)
    total_stale = sum(len(v) for v in stale_by_course.values())

    print()
    print("=" * 50)
    print("  Wiki Lint Report")
    print("=" * 50)
    print()

    print(f"  Orphan concepts:    {len(orphan_concepts)}")
    print(f"  Orphan cases:       {len(orphan_cases)}")
    print(f"  Broken wikilinks:   {broken_count}")
    print(f"  Missing concepts:   {len(missing)}")
    print(f"  Stale pages:        {total_stale}")
    print()

    if broken_links:
        print("TOP BROKEN LINKS:")
        for target, sources in broken_links[:10]:
            print(f"  [[{target}]]  <- {len(sources)} pages")
        print()

    if missing:
        print("TOP MISSING CONCEPTS:")
        for term, count, _ in missing[:10]:
            print(f"  \"{term}\"  <- {count} pages")
        print()

    print(f"TOTAL: {total_concepts} concepts, {total_cases} cases")
    print("-" * 50)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Lint the KnowledgeWiki for structural issues")
    parser.add_argument("--orphans", action="store_true", help="Only check orphan pages")
    parser.add_argument("--broken", action="store_true", help="Only check broken wikilinks")
    parser.add_argument("--missing", action="store_true", help="Only check missing concepts")
    parser.add_argument("--stale", action="store_true", help="Only check stale content")
    parser.add_argument("--no-save", action="store_true", help="Don't save markdown report")
    args = parser.parse_args()

    run_all = not (args.orphans or args.broken or args.missing or args.stale)

    print("Scanning wiki...")
    pages, title_lookup, inbound, broken, body_texts = scan_wiki()
    print(f"Found {len(pages)} pages.")

    orphan_concepts, orphan_cases = [], []
    if run_all or args.orphans:
        orphan_concepts, orphan_cases = check_orphans(pages, inbound)

    broken_links = check_broken(broken) if (run_all or args.broken) else []
    missing = check_missing(pages, title_lookup, body_texts) if (run_all or args.missing) else []
    stale_by_course = check_stale(pages) if (run_all or args.stale) else {}

    # Console output
    print_console(orphan_concepts, orphan_cases, broken_links, missing, stale_by_course, pages)

    # Save markdown report
    if not args.no_save:
        MAINTENANCE_DIR.mkdir(exist_ok=True)
        report = build_report(orphan_concepts, orphan_cases, broken_links, missing, stale_by_course, pages)
        timestamp = datetime.now().strftime("%Y-%m-%d")
        report_path = MAINTENANCE_DIR / f"lint-report-{timestamp}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
