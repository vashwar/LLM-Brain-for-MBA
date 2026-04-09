import re
import markdown
from pathlib import Path


def _convert_latex_delimiters_html(html):
    """Convert $...$ LaTeX math to \\(...\\) delimiters in rendered HTML.
    Only converts when content between $ signs contains LaTeX commands
    (backslashes), avoiding false positives on dollar amounts like $20,000.
    Run AFTER markdown-to-HTML conversion to avoid markdown escaping.
    """
    def replace_match(m):
        inner = m.group(1)
        return '\\(' + inner + '\\)'

    # Match $...$ where content contains a backslash (LaTeX command)
    html = re.sub(
        r'\$([^$]*?\\[^$]*?)\$',
        replace_match,
        html
    )
    return html


def parse_markdown_to_html(content):
    """
    Convert markdown content to HTML using Python-Markdown library.
    Enables extensions for better formatting support.
    """
    md = markdown.Markdown(
        extensions=[
            "markdown.extensions.toc",
            "markdown.extensions.tables",
            "markdown.extensions.fenced_code",
            "markdown.extensions.codehilite",
        ]
    )

    html = md.convert(content)
    toc = md.toc

    # Convert LaTeX $...$ to \(...\) after markdown processing
    # so markdown doesn't escape the backslash delimiters
    html = _convert_latex_delimiters_html(html)

    return html, toc


def extract_title_from_markdown(content):
    """
    Extract the first H1 heading from markdown as the page title.
    Returns None if no H1 heading found.
    """
    lines = content.split("\n")
    for line in lines:
        if line.startswith("# "):
            return line[2:].strip()
    return None


def extract_metadata(content):
    """
    Extract metadata from bottom of markdown file.
    Looks for tags and status lines.
    """
    lines = content.split("\n")
    metadata = {}

    for line in lines:
        if line.startswith("**Tags:**"):
            # Extract tags from line like: **Tags:** #concept #lecture #microecon
            tags_str = line.replace("**Tags:**", "").strip()
            metadata["tags"] = [tag.strip() for tag in tags_str.split() if tag.startswith("#")]
        elif line.startswith("**Status:**"):
            status_str = line.replace("**Status:**", "").strip()
            metadata["status"] = status_str
        elif line.startswith("**Course:**"):
            course_str = line.replace("**Course:**", "").strip()
            metadata["courses"] = [c.strip() for c in course_str.split(",") if c.strip()]

    return metadata
