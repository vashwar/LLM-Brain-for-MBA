# MBA Wiki Viewer

A Wikipedia-style web viewer for MBA economics concepts extracted from lecture materials.

## Features

✨ **Rich Content Display**
- Converts markdown to beautiful HTML with Wikipedia-inspired styling
- Automatic table of contents sidebar for easy navigation
- Embedded charts and diagrams from lecture materials
- Code blocks, blockquotes, and formatted text

🔗 **Smart Wikilinks**
- Converts `[[Concept Name]]` links to HTML navigation
- Highlights broken links in red with tooltips
- Cross-reference related concepts seamlessly

📚 **Full Concept Library**
- 20+ microeconomic concepts from MBA lectures
- Each concept includes:
  - Definition and key points
  - Formulas and equations
  - Real-world examples and applications
  - Illustrative charts and diagrams
  - Key quotes from lecture materials
  - Practice questions
  - Related concepts (as wikilinks)

🎨 **Wikipedia-Style Design**
- Clean, readable typography
- Responsive layout (mobile, tablet, desktop)
- Familiar Wikipedia color scheme and styling
- Sticky table of contents sidebar

## Installation

1. **Install dependencies:**
   ```bash
   pip install -r ../requirements.txt
   ```

2. **Verify the MBAWiki directory exists:**
   ```bash
   ls ../MBAWiki/
   ```

## Running the Application

Start the Flask development server:

```bash
python app.py
```

The application will:
- Load 20 concepts from `../MBAWiki/Concept-*.md` files
- Start a local web server at `http://127.0.0.1:5000`
- Enable debug mode with auto-reload

**Output:**
```
Starting MBA Wiki Viewer...
Loaded 20 concepts
Open browser to: http://127.0.0.1:5000/
 * Running on http://127.0.0.1:5000
```

## URL Structure

- **Homepage:** `http://localhost:5000/`
  - Displays alphabetical list of all concepts
  - Quick start with search bar

- **Concept Page:** `http://localhost:5000/concept/<slug>`
  - Example: `/concept/supply-curve`
  - Example: `/concept/demand-curve`
  - Example: `/concept/market-equilibrium`

- **Chart Images:** `http://localhost:5000/assets/charts/<filename>`
  - Served from `../MBAWiki/assets/charts/`

## Project Structure

```
wiki_viewer/
├── app.py                          # Flask application & routes
├── config.py                       # Configuration & paths
├── utils/
│   ├── markdown_parser.py          # Markdown → HTML conversion
│   └── wikilink_processor.py       # Wikilink & link conversion
├── templates/
│   ├── base.html                   # Base layout with header/footer
│   ├── index.html                  # Homepage with concept list
│   ├── concept.html                # Individual concept page
│   ├── 404.html                    # Not found page
│   └── 500.html                    # Server error page
└── static/
    ├── css/
    │   └── wikipedia.css           # Wikipedia-inspired styling
    └── js/
        └── search.js               # Search UI enhancements
```

## Key Components

### 1. Flask Routes (app.py)

- **`GET /`** — Homepage with concept list
- **`GET /concept/<slug>`** — Individual concept page
- **`GET /assets/charts/<filename>`** — Serve chart images
- **`404/500`** — Error handling

### 2. Markdown Parser (utils/markdown_parser.py)

Converts markdown to HTML with extensions:
- Table of contents auto-generation
- Table support
- Code blocks with syntax highlighting
- Proper heading hierarchy

### 3. Wikilink Processor (utils/wikilink_processor.py)

Handles the critical task of converting wikilinks to proper HTML links:

**How it works:**
1. **Build mapping at startup:** Scans all `Concept-*.md` files and extracts titles from H1 headers
2. **Map titles to slugs:** Creates dictionary like `{"Supply Curve": "supply-curve"}`
3. **Process wikilinks:** Converts `[[Supply Curve]]` → `<a href="/concept/supply-curve">`
4. **Handle broken links:** Unmapped links show as red text with "Link not found" tooltip

**Example:**
```
Input:  - [[Demand Curve]] from the [[Market Equilibrium]] and [[Supply and Demand]]
Output: - <a href="/concept/demand-curve">Demand Curve</a> from the
        <a href="/concept/market-equilibrium">Market Equilibrium</a> and
        <span class="broken-wikilink">Supply and Demand</span>
```

### 4. Wikipedia Styling (static/css/wikipedia.css)

Design features:
- Max-width 900px for content (readable line length)
- Left sidebar for table of contents (sticky)
- Blue links (#0645ad) with Wikipedia-standard colors
- Serif fonts (Georgia) for body text
- Responsive layout with mobile breakpoint

## Development

### Enable Debug Mode

Edit `config.py`:
```python
DEBUG = True  # Already enabled by default
```

### Hot Reload

Flask is configured with debug=True, so changes to templates and Python files will auto-reload the server.

### Adding a New Concept

1. Create markdown file in `../MBAWiki/`
   ```
   Concept-my-concept-name.md
   ```

2. Start with H1 heading (required for title extraction)
   ```markdown
   # My Concept Name

   **Source:** Lecture notes or slides

   ## Definition
   ...
   ```

3. Add wikilinks to related concepts
   ```markdown
   [[Related Concept]]
   ```

4. Refresh browser — new concept appears automatically!

## Verification Checklist

After running the app, verify these features work:

- [ ] Homepage loads with 20 concepts listed
- [ ] Clicking a concept opens its page
- [ ] Table of contents sidebar scrolls to sections
- [ ] Charts/images load correctly (not broken images)
- [ ] Wikilinks are blue and clickable
- [ ] Clicking a wikilink navigates to that concept
- [ ] Broken wikilinks appear in red with tooltip
- [ ] Metadata (tags, status) displays at top
- [ ] Search bar is present (placeholder for Phase 4)
- [ ] Responsive design works on mobile (use browser dev tools)
- [ ] Back button returns to homepage

## Future Enhancements (Not Implemented)

See the main plan for potential features:
- Full-text search across all concepts
- Tag-based filtering
- Graph visualization of concept relationships
- Integration with LLM for Q&A
- Static HTML export for deployment
- Edit capability
- Version history tracking

## Troubleshooting

### Charts don't load
- Check: `ls ../MBAWiki/assets/charts/`
- Verify file names exactly match markdown references
- Note: File names with spaces are URL-encoded in browser

### Wikilinks not converting
- Verify concept file exists: `ls ../MBAWiki/Concept-*.md`
- Check title is H1 (first line starts with `# `)
- Run app and check console for errors

### Port already in use
- Change `PORT` in `config.py`
- Or kill process: `lsof -i :5000` then `kill -9 <pid>`

### 404 errors
- Verify concept slug matches filename
- Example: File `Concept-supply-curve.md` → URL `/concept/supply-curve`

## Browser Compatibility

Tested on:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## License

Part of the MBA Wiki project. See parent directory for license info.
