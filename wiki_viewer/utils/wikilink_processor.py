import html
import re
import json
from pathlib import Path
import sys
from pathlib import Path as PathlibPath

# Add parent directory to path to import config
sys.path.insert(0, str(PathlibPath(__file__).parent.parent))

from config import CONCEPTS_DIR, CHARTS_DIR, CONCEPT_FILE_PREFIX, CASE_FILE_PREFIX, CONCEPT_FILE_SUFFIX


class WikilinkProcessor:
    """Handles conversion of wikilinks [[Link]] to HTML links and image insertion"""

    def __init__(self):
        self.concept_map = {}  # {"Display Name": "slug"}
        self.case_map = {}     # {"Display Name": "slug"}
        self.image_map = {}    # {"Concept Title": [{"filename": ..., "caption": ...}]}
        self.course_map = {}   # {"Course Name": {"concepts": [(title, slug)], "cases": [(title, slug)]}}
        self.concept_courses = {}  # {"Concept Title": ["Course1", "Course2"]}
        self.case_courses = {}     # {"Case Title": ["Course1", "Course2"]}
        self.alias_map = {}    # {"alias": ("type", "slug")} for fuzzy wikilink resolution
        self.build_concept_map()
        self.build_alias_map()
        self.load_image_tags()

    def build_concept_map(self):
        """
        Scan all Concept-*.md and Case-*.md files and build mapping from title to slug.

        Example:
            File: Concept-supply-curve.md
            First line: # Supply Curve
            Mapping: concept_map["Supply Curve"] = "supply-curve"

            File: Case-heidi-roizen.md
            First line: # Case: Heidi Roizen
            Mapping: case_map["Case: Heidi Roizen"] = "heidi-roizen"
        """
        # Scan Concept-*.md files
        concept_files = sorted(
            CONCEPTS_DIR.glob(f"{CONCEPT_FILE_PREFIX}*{CONCEPT_FILE_SUFFIX}")
        )

        for file_path in concept_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = [f.readline().strip() for _ in range(5)]

                if lines[0].startswith("# "):
                    title = lines[0][2:].strip()
                    slug = self._filename_to_slug(file_path.stem, CONCEPT_FILE_PREFIX)
                    self.concept_map[title] = slug
                    courses = self._extract_courses(lines)
                    self.concept_courses[title] = courses
                    for course in courses:
                        if course not in self.course_map:
                            self.course_map[course] = {"concepts": [], "cases": []}
                        self.course_map[course]["concepts"].append((title, slug))
            except Exception as e:
                print(f"Warning: Could not read {file_path}: {e}")

        # Scan Case-*.md files
        case_files = sorted(
            CONCEPTS_DIR.glob(f"{CASE_FILE_PREFIX}*{CONCEPT_FILE_SUFFIX}")
        )

        for file_path in case_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = [f.readline().strip() for _ in range(5)]

                if lines[0].startswith("# "):
                    title = lines[0][2:].strip()
                    slug = self._filename_to_slug(file_path.stem, CASE_FILE_PREFIX)
                    self.case_map[title] = slug
                    courses = self._extract_courses(lines)
                    self.case_courses[title] = courses
                    for course in courses:
                        if course not in self.course_map:
                            self.course_map[course] = {"concepts": [], "cases": []}
                        self.course_map[course]["cases"].append((title, slug))
            except Exception as e:
                print(f"Warning: Could not read {file_path}: {e}")

    def _filename_to_slug(self, filename, prefix=None):
        """
        Convert filename to slug.
        Example: "Concept-supply-curve" -> "supply-curve"
                 "Case-heidi-roizen" -> "heidi-roizen"
        """
        if prefix and filename.startswith(prefix):
            return filename[len(prefix):]
        if filename.startswith(CONCEPT_FILE_PREFIX):
            return filename[len(CONCEPT_FILE_PREFIX):]
        if filename.startswith(CASE_FILE_PREFIX):
            return filename[len(CASE_FILE_PREFIX):]
        return filename

    def _extract_courses(self, lines):
        """Extract course names from first 5 lines of a file.
        Looks for **Course:** field, supports comma-separated multi-course.
        Returns ["Uncategorized"] if no Course field found.
        """
        for line in lines:
            if line.startswith("**Course:**"):
                course_str = line.replace("**Course:**", "").strip()
                courses = [c.strip() for c in course_str.split(",") if c.strip()]
                if courses:
                    return courses
        return ["Uncategorized"]

    @staticmethod
    def get_course_slug(name):
        """Convert course name to URL slug."""
        return re.sub(r'[^a-z0-9\-]', '', name.lower().replace(" ", "-"))

    def get_courses_for_title(self, title):
        """Get list of course names for a concept or case title."""
        if title in self.concept_courses:
            return self.concept_courses[title]
        if title in self.case_courses:
            return self.case_courses[title]
        return []

    def get_sorted_courses(self):
        """Return course names sorted alphabetically, with Uncategorized last."""
        courses = sorted(self.course_map.keys())
        if "Uncategorized" in courses:
            courses.remove("Uncategorized")
            courses.append("Uncategorized")
        return courses

    def build_alias_map(self):
        """Build aliases so fuzzy wikilinks resolve correctly.

        Auto-generates three types of aliases:
        1. Abbreviations: "Net Present Value (NPV)" -> alias "NPV"
        2. Slug-to-title: slug "consumption-smoothing" -> "Consumption Smoothing"
        3. Case-insensitive: "phillips curve" matches "Phillips Curve"
        """
        # 1. Abbreviation aliases — extract text in parentheses from titles
        #    e.g., "CAPM (Capital Asset Pricing Model)" -> alias "CAPM"
        #    e.g., "Net Present Value (NPV)" -> alias "NPV"
        paren_re = re.compile(r"\(([^)]+)\)")
        for title, slug in self.concept_map.items():
            matches = paren_re.findall(title)
            for abbrev in matches:
                abbrev = abbrev.strip()
                if abbrev and abbrev not in self.concept_map and abbrev not in self.case_map:
                    self.alias_map[abbrev] = ("concept", slug)
            # Also add the title without the parenthetical
            stripped = paren_re.sub("", title).strip()
            if stripped and stripped != title and stripped not in self.concept_map:
                self.alias_map[stripped] = ("concept", slug)

        for title, slug in self.case_map.items():
            matches = paren_re.findall(title)
            for abbrev in matches:
                abbrev = abbrev.strip()
                if abbrev and abbrev not in self.concept_map and abbrev not in self.case_map:
                    self.alias_map[abbrev] = ("case", slug)

        # 2. Slug aliases — "consumption-smoothing" -> find matching title
        for title, slug in self.concept_map.items():
            self.alias_map[slug] = ("concept", slug)
        for title, slug in self.case_map.items():
            self.alias_map[slug] = ("case", slug)

    def _resolve_wikilink(self, link_text):
        """Try to resolve a wikilink to (type, slug, display_text) or None.

        Resolution order:
        1. Exact match in case_map
        2. Exact match in concept_map
        3. Case-insensitive match
        4. Alias map (abbreviations, slugs)
        5. Case-insensitive alias match
        """
        # 1. Exact case match
        slug = self.case_map.get(link_text)
        if slug:
            return ("case", slug, link_text)

        slug = self.concept_map.get(link_text)
        if slug:
            return ("concept", slug, link_text)

        # 2. Case-insensitive match against titles
        link_lower = link_text.lower()
        for title, slug in self.case_map.items():
            if title.lower() == link_lower:
                return ("case", slug, link_text)
        for title, slug in self.concept_map.items():
            if title.lower() == link_lower:
                return ("concept", slug, link_text)

        # 3. Exact alias match
        if link_text in self.alias_map:
            ptype, slug = self.alias_map[link_text]
            return (ptype, slug, link_text)

        # 4. Case-insensitive alias match (handles slug-style like "consumption-smoothing")
        for alias, (ptype, slug) in self.alias_map.items():
            if alias.lower() == link_lower:
                return (ptype, slug, link_text)

        # 5. Prefix match — link text is the start of an existing title
        #    e.g., "Equality vs. Equity" matches "Equality vs. Equity vs. Justice"
        #    Requires link text to be at least 50% of the title length
        link_norm = link_lower.replace("-", " ")
        best_match = None
        best_len = 0
        for title, slug in self.concept_map.items():
            title_norm = title.lower().replace("-", " ")
            if title_norm.startswith(link_norm) and len(link_norm) >= len(title_norm) * 0.5:
                if len(title) > best_len:
                    best_match = ("concept", slug, link_text)
                    best_len = len(title)
        for title, slug in self.case_map.items():
            title_norm = title.lower().replace("-", " ")
            if title_norm.startswith(link_norm) and len(link_norm) >= len(title_norm) * 0.5:
                if len(title) > best_len:
                    best_match = ("case", slug, link_text)
                    best_len = len(title)

        return best_match

    def process_wikilinks(self, html_content):
        """
        Replace wikilinks in HTML with proper <a> tags.

        Example:
            [[Supply Curve]] -> <a href="/concept/supply-curve">Supply Curve</a>
            [[Case: Heidi Roizen]] -> <a href="/case/heidi-roizen">Case: Heidi Roizen</a>
            [[Non-existent]] -> <span class="broken-wikilink">Non-existent</span>
        """
        pattern = r"\[\[([^\]]+)\]\]"

        def replace_wikilink(match):
            link_text = html.unescape(match.group(1))

            resolved = self._resolve_wikilink(link_text)
            if resolved:
                ptype, slug, display = resolved
                route = "case" if ptype == "case" else "concept"
                return f'<a href="/{route}/{slug}" class="wikilink">{display}</a>'

            return f'<span class="broken-wikilink" title="Link not found">{link_text}</span>'

        return re.sub(pattern, replace_wikilink, html_content)

    def fix_image_paths(self, html_content):
        """
        Fix image paths from relative to absolute.
        Example: src="assets/... -> src="/assets/...
        """
        return html_content.replace('src="assets/', 'src="/assets/')

    def load_image_tags(self):
        """Load image_tags.json and build concept → images mapping.
        Supports multiple captions per image (one image on multiple concept pages).
        """
        self.image_map = {}
        tags_file = CHARTS_DIR / 'image_tags.json'

        if not tags_file.exists():
            return

        try:
            with open(tags_file, 'r', encoding='utf-8') as f:
                tags = json.load(f)

            for filename, value in tags.items():
                # New format: list of {"concept": ..., "caption": ...}
                if isinstance(value, list):
                    for mapping in value:
                        if isinstance(mapping, dict) and 'concept' in mapping:
                            concept = mapping['concept']
                            if concept not in self.image_map:
                                self.image_map[concept] = []
                            self.image_map[concept].append({
                                'filename': filename,
                                'caption': mapping.get('caption', '')
                            })
        except Exception as e:
            print(f"Warning: Could not load image tags: {e}")

    def get_images_for_concept(self, title):
        """Get tagged images for a concept title."""
        return self.image_map.get(title, [])

    def insert_images_html(self, html_content, title):
        """Insert tagged images into the concept page HTML."""
        images = self.get_images_for_concept(title)
        if not images:
            return html_content

        images_html = '<div class="concept-charts">'
        images_html += '<h2>Charts & Diagrams</h2>'
        for img in images:
            images_html += f'<figure>'
            images_html += f'<img src="/assets/charts/{img["filename"]}" alt="{img["caption"]}">'
            if img["caption"]:
                images_html += f'<figcaption>{img["caption"]}</figcaption>'
            images_html += f'</figure>'
        images_html += '</div>'

        # Insert before Related Concepts section if it exists, otherwise append
        if '<h2>Related Concepts</h2>' in html_content:
            html_content = html_content.replace(
                '<h2>Related Concepts</h2>',
                images_html + '<h2>Related Concepts</h2>'
            )
        else:
            html_content += images_html

        return html_content

    def process_content(self, markdown_html, title=None):
        """
        Run all processing steps on HTML content.
        Returns processed HTML with wikilinks, fixed image paths, and tagged images.
        """
        html = self.process_wikilinks(markdown_html)
        html = self.fix_image_paths(html)
        if title:
            html = self.insert_images_html(html, title)
        return html

    def get_all_concepts(self):
        """Return list of all concept titles, sorted alphabetically"""
        return sorted(self.concept_map.keys())

    def get_all_cases(self):
        """Return list of all case titles, sorted alphabetically"""
        return sorted(self.case_map.keys())

    def get_concept_slug(self, title):
        """Get slug for a given concept title, or None if not found"""
        return self.concept_map.get(title)

    def get_case_slug(self, title):
        """Get slug for a given case title, or None if not found"""
        return self.case_map.get(title)


# Create global instance for reuse
processor = WikilinkProcessor()
