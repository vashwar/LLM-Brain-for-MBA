#!/usr/bin/env python3
"""
Build Knowledge Graph JSON from wiki markdown files.

Scans all Concept-*.md and Case-*.md in MBAWiki/, extracts titles, courses,
and [[Wikilinks]], then outputs a nodes+links JSON for D3 visualization.

Usage:
    python build_graph.py
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = PROJECT_ROOT / "MBAWiki"
CONCEPT_PREFIX = "Concept-"
CASE_PREFIX = "Case-"
SUFFIX = ".md"
OUTPUT_FILE = WIKI_DIR / "assets" / "knowledge_graph.json"


def extract_file_data(filepath, prefix):
    """Extract title, slug, course, and wikilinks from a markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"  Warning: Could not read {filepath}: {e}")
        return None

    lines = content.split("\n")

    # Title from first line
    title = None
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
    if not title:
        return None

    slug = filepath.stem[len(prefix):]

    # Determine type
    is_case = prefix == CASE_PREFIX
    node_type = "case" if is_case else "concept"

    # Course from first 5 lines
    courses = []
    for line in lines[:5]:
        if line.strip().startswith("**Course:**"):
            course_str = line.strip().replace("**Course:**", "").strip()
            courses = [c.strip() for c in course_str.split(",") if c.strip()]
            break
    if not courses:
        courses = ["Uncategorized"]

    # Extract all [[Wikilinks]]
    wikilinks = re.findall(r"\[\[([^\]]+)\]\]", content)

    return {
        "title": title,
        "slug": slug,
        "type": node_type,
        "courses": courses,
        "wikilinks": wikilinks,
    }


def build_graph():
    """Scan wiki files and build the knowledge graph."""
    if not WIKI_DIR.exists():
        print(f"Error: Wiki directory not found: {WIKI_DIR}")
        sys.exit(1)

    # Collect all file data
    all_data = []

    for filepath in sorted(WIKI_DIR.glob(f"{CONCEPT_PREFIX}*{SUFFIX}")):
        data = extract_file_data(filepath, CONCEPT_PREFIX)
        if data:
            all_data.append(data)

    for filepath in sorted(WIKI_DIR.glob(f"{CASE_PREFIX}*{SUFFIX}")):
        data = extract_file_data(filepath, CASE_PREFIX)
        if data:
            all_data.append(data)

    # Build title -> slug+type lookup for link validation
    title_lookup = {}
    for d in all_data:
        title_lookup[d["title"]] = {"slug": d["slug"], "type": d["type"]}

    # Build nodes
    nodes = []
    link_counts = {}  # slug -> count of valid connections

    for d in all_data:
        nodes.append({
            "id": d["slug"],
            "title": d["title"],
            "type": d["type"],
            "courses": d["courses"],
        })
        link_counts[d["slug"]] = 0

    # Build links (only where both source AND target exist)
    links = []
    broken_count = 0

    for d in all_data:
        source_slug = d["slug"]
        seen_targets = set()

        for wikilink_title in d["wikilinks"]:
            target = title_lookup.get(wikilink_title)
            if target and target["slug"] != source_slug:
                target_slug = target["slug"]
                # Deduplicate edges within same source
                if target_slug not in seen_targets:
                    seen_targets.add(target_slug)
                    links.append({
                        "source": source_slug,
                        "target": target_slug,
                    })
                    link_counts[source_slug] = link_counts.get(source_slug, 0) + 1
                    link_counts[target_slug] = link_counts.get(target_slug, 0) + 1
            elif not target:
                broken_count += 1

    # Add connection count to nodes
    for node in nodes:
        node["connections"] = link_counts.get(node["id"], 0)

    # Collect all unique courses for the color legend
    all_courses = sorted(set(c for d in all_data for c in d["courses"]))

    graph = {
        "nodes": nodes,
        "links": links,
        "courses": all_courses,
    }

    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)

    print(f"Built graph: {len(nodes)} nodes, {len(links)} edges ({broken_count} broken links filtered)")
    print(f"Courses: {', '.join(all_courses)}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    build_graph()
