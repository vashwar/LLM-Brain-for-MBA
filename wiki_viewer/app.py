from flask import Flask, render_template, abort, send_from_directory
from pathlib import Path
import json
import sys

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

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["DEBUG"] = DEBUG


@app.route("/")
def index():
    """Homepage: display grid of course cards"""
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
    return render_template(
        "index.html",
        courses=courses,
        total_concepts=total_concepts,
        total_cases=total_cases,
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
