from flask import Flask, render_template, abort, send_from_directory, request
from pathlib import Path
import json
import sys
import datetime
import re

# Setup path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    DEBUG,
    HOST,
    PORT,
    WIKI_DIR,
    CONCEPTS_DIR,
    CHARTS_DIR,
    CONCEPT_FILE_PREFIX,
    CASE_FILE_PREFIX,
    CONCEPT_FILE_SUFFIX,
)
from utils.markdown_parser import parse_markdown_to_html, extract_title_from_markdown, extract_metadata
from utils.wikilink_processor import processor
from utils.search import SearchIndex

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["DEBUG"] = DEBUG

# Initialize semantic search index (loads embeddings + metadata, not the model)
search_index = SearchIndex(
    WIKI_DIR / "assets" / "search_index.npz",
    WIKI_DIR / "assets" / "search_metadata.json",
)
search_index.load()


def _strip_md(text):
    """Minimal markdown stripper for preview text."""
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", text)  # wikilinks
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)                   # bold
    text = re.sub(r"\*([^*]+)\*", r"\1", text)                       # italic
    text = re.sub(r"`([^`]+)`", r"\1", text)                         # code
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)             # md links
    text = text.replace("**", "").replace("*", "")
    return text.strip()


def _extract_first_paragraph(content):
    """Return the first prose paragraph after the H1 title.

    Prefers text under '## Definition' if present, otherwise takes the first
    non-empty block after the title that isn't metadata or a heading.
    """
    lines = content.splitlines()

    def paragraph_after(start_idx):
        buf = []
        for ln in lines[start_idx:]:
            stripped = ln.strip()
            if not stripped:
                if buf:
                    break
                continue
            if stripped.startswith("#"):
                if buf:
                    break
                continue
            if stripped.startswith("**") and stripped.endswith("**") and ":" in stripped:
                # metadata line like **Course:** ..., **Source:** ...
                if buf:
                    break
                continue
            if stripped.startswith("- ") or stripped.startswith("* "):
                if buf:
                    break
                continue
            buf.append(stripped)
        return " ".join(buf).strip()

    # Look for ## Definition first
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith("## definition"):
            para = paragraph_after(i + 1)
            if para:
                return para
            break

    # Fallback: first paragraph after the H1 title
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            para = paragraph_after(i + 1)
            if para:
                return para
            break

    return ""


def _get_concept_of_the_day():
    """Deterministically pick a concept for today.

    Uses date.toordinal() % count so the selection is stable for the whole day
    and rotates every midnight local time. Returns a dict with title, slug,
    course, and preview — or None if no concepts exist.
    """
    concept_titles = sorted(processor.concept_map.keys())
    if not concept_titles:
        return None

    today_ordinal = datetime.date.today().toordinal()
    idx = today_ordinal % len(concept_titles)
    title = concept_titles[idx]
    slug = processor.concept_map[title]

    filename = f"{CONCEPT_FILE_PREFIX}{slug}{CONCEPT_FILE_SUFFIX}"
    filepath = CONCEPTS_DIR / filename
    preview = ""
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            raw = _extract_first_paragraph(content)
            preview = _strip_md(raw)
            if len(preview) > 360:
                preview = preview[:357].rsplit(" ", 1)[0] + "..."
        except Exception as e:
            print(f"Warning: could not read {filepath} for concept-of-the-day: {e}")

    courses = processor.get_courses_for_title(title)
    course_name = courses[0] if courses else "Uncategorized"

    return {
        "title": title,
        "slug": slug,
        "course": course_name,
        "course_slug": processor.get_course_slug(course_name),
        "preview": preview,
    }


def _get_did_you_know(n=4, exclude_title=None):
    """Pick N random concepts for the 'Did you know' panel.

    Deterministic per day (shifted from the concept-of-the-day so they differ).
    """
    concept_titles = sorted(processor.concept_map.keys())
    if not concept_titles:
        return []

    today_ordinal = datetime.date.today().toordinal()
    total = len(concept_titles)
    picks = []
    seen = set()
    if exclude_title:
        seen.add(exclude_title)

    step = max(1, total // max(n, 1) + 1)
    i = (today_ordinal * 7) % total  # shift from concept-of-the-day
    attempts = 0
    while len(picks) < n and attempts < total * 2:
        title = concept_titles[i % total]
        if title not in seen:
            slug = processor.concept_map[title]
            picks.append({"title": title, "slug": slug})
            seen.add(title)
        i += step
        attempts += 1

    return picks


@app.route("/")
def index():
    """Homepage: Wikipedia main-page style with Concept of the Day."""
    courses = []
    for name in processor.get_sorted_courses():
        data = processor.course_map[name]
        courses.append({
            "name": name,
            "slug": processor.get_course_slug(name),
            "concept_count": len(data["concepts"]),
            "case_count": len(data["cases"]),
        })
    total_concepts = len(processor.concept_map)
    total_cases = len(processor.case_map)

    concept_of_the_day = _get_concept_of_the_day()
    did_you_know = _get_did_you_know(
        n=4,
        exclude_title=concept_of_the_day["title"] if concept_of_the_day else None,
    )
    today_str = datetime.date.today().strftime("%B %d, %Y")

    return render_template(
        "index.html",
        courses=courses,
        total_concepts=total_concepts,
        total_cases=total_cases,
        concept_of_the_day=concept_of_the_day,
        did_you_know=did_you_know,
        today_str=today_str,
    )


@app.route("/course/<slug>")
def course(slug):
    """Display a single course page with its concepts and cases"""
    # Find course by slug
    course_name = None
    for name in processor.course_map:
        if processor.get_course_slug(name) == slug:
            course_name = name
            break

    if course_name is None:
        abort(404)

    data = processor.course_map[course_name]
    concepts = sorted(data["concepts"], key=lambda x: x[0])
    cases = sorted(data["cases"], key=lambda x: x[0])

    return render_template(
        "course.html",
        course_name=course_name,
        course_slug=slug,
        concepts=concepts,
        cases=cases,
    )


@app.route("/cases")
def all_cases():
    """Display all case studies across all courses"""
    # Get all cases organized by course
    cases_by_course = []
    for course_name in sorted(processor.course_map.keys()):
        data = processor.course_map[course_name]
        if data["cases"]:
            cases_by_course.append({
                "name": course_name,
                "slug": processor.get_course_slug(course_name),
                "cases": sorted(data["cases"], key=lambda x: x[0]),
            })

    total_cases = len(processor.case_map)

    return render_template(
        "cases.html",
        cases_by_course=cases_by_course,
        total_cases=total_cases,
    )


@app.route("/concept/<slug>")
def concept(slug):
    """
    Display a single concept page.
    Loads the markdown file, converts to HTML, processes wikilinks.
    """
    # Build filename from slug
    filename = f"{CONCEPT_FILE_PREFIX}{slug}{CONCEPT_FILE_SUFFIX}"
    filepath = CONCEPTS_DIR / filename

    # Check if file exists
    if not filepath.exists():
        abort(404)

    # Read markdown content
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        abort(500)

    # Parse markdown to HTML
    html, toc = parse_markdown_to_html(content)

    # Extract metadata
    metadata = extract_metadata(content)
    title = extract_title_from_markdown(content) or slug.replace("-", " ").title()

    # Add course links to metadata
    course_names = processor.get_courses_for_title(title)
    metadata["course_links"] = [
        {"name": c, "slug": processor.get_course_slug(c)} for c in course_names
    ]

    # Process wikilinks, image paths, and tagged images
    html = processor.process_content(html, title=title)

    return render_template(
        "concept.html",
        title=title,
        slug=slug,
        content=html,
        toc=toc,
        metadata=metadata,
    )


@app.route("/case/<slug>")
def case(slug):
    """
    Display a single case study page.
    Loads the Case-*.md file, converts to HTML, processes wikilinks.
    """
    filename = f"{CASE_FILE_PREFIX}{slug}{CONCEPT_FILE_SUFFIX}"
    filepath = CONCEPTS_DIR / filename

    if not filepath.exists():
        abort(404)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        abort(500)

    html, toc = parse_markdown_to_html(content)
    metadata = extract_metadata(content)
    title = extract_title_from_markdown(content) or slug.replace("-", " ").title()

    # Add course links to metadata
    course_names = processor.get_courses_for_title(title)
    metadata["course_links"] = [
        {"name": c, "slug": processor.get_course_slug(c)} for c in course_names
    ]

    html = processor.process_content(html, title=title)

    return render_template(
        "concept.html",
        title=title,
        slug=slug,
        content=html,
        toc=toc,
        metadata=metadata,
    )


@app.route("/graph")
def graph():
    """Display the interactive knowledge graph visualization."""
    graph_file = CHARTS_DIR.parent / "knowledge_graph.json"
    graph_data = {"nodes": [], "links": [], "courses": []}
    if graph_file.exists():
        try:
            with open(graph_file, "r", encoding="utf-8") as f:
                graph_data = json.load(f)
        except Exception as e:
            print(f"Error reading knowledge_graph.json: {e}")
    return render_template("graph.html", graph_data=graph_data)


@app.route("/search")
def search():
    """Semantic search across concepts and case studies."""
    query = request.args.get("q", "").strip()
    course_filter = request.args.get("course", "").strip()
    type_filter = request.args.get("type", "").strip()

    # Normalize "all" / empty to None for the SearchIndex API
    course_arg = course_filter or None
    type_arg = type_filter if type_filter in ("concept", "case") else None

    results = []
    if query and search_index.available:
        results = search_index.search(
            query,
            k=20,
            course=course_arg,
            type_filter=type_arg,
        )

    concepts = [r for r in results if r["type"] == "concept"]
    cases = [r for r in results if r["type"] == "case"]

    return render_template(
        "search.html",
        query=query,
        concepts=concepts,
        cases=cases,
        total=len(results),
        courses=processor.get_sorted_courses(),
        course_filter=course_filter,
        type_filter=type_filter,
        index_available=search_index.available,
    )


@app.route("/assets/charts/<filename>")
def serve_chart(filename):
    """Serve chart images from the assets/charts directory"""
    # Security: prevent directory traversal
    if ".." in filename or "/" in filename:
        abort(403)

    return send_from_directory(CHARTS_DIR, filename)


@app.errorhandler(404)
def not_found(e):
    """Custom 404 page"""
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    """Custom 500 page"""
    return render_template("500.html"), 500


if __name__ == "__main__":
    print(f"Starting MBA Wiki Viewer...")
    print(f"Loaded {len(processor.concept_map)} concepts, {len(processor.case_map)} cases across {len(processor.course_map)} courses")
    print(f"Open browser to: http://{HOST}:{PORT}/")
    app.run(host=HOST, port=PORT, debug=DEBUG)
