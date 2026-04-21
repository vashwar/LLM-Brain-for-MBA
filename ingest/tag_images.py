#!/usr/bin/env python3
"""
Tag Images to Concepts

Each image can have multiple captions, mapping it to multiple concept pages.

Workflow:
  1. Run with --list to see all untagged images
  2. Edit MBAWiki/assets/charts/image_tags.json to add captions
  3. Run with --map to auto-map captions to concepts (1 Gemini API call)

Format (before mapping):
  { "image.png": ["caption for concept A", "caption for concept B"] }

Format (after mapping):
  { "image.png": [
      {"concept": "Concept A", "caption": "caption for concept A"},
      {"concept": "Concept B", "caption": "caption for concept B"}
  ]}

Usage:
    python tag_images.py --list          # Show untagged images
    python tag_images.py --map           # Map captions to concepts via Gemini
    python tag_images.py --status        # Show current mappings
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / '.env')

WIKI_DIR = PROJECT_ROOT / 'MBAWiki'
CHARTS_DIR = WIKI_DIR / 'assets' / 'charts'
TAGS_FILE = CHARTS_DIR / 'image_tags.json'
GEMINI_MODEL = "gemini-3-flash-preview"


def load_tags():
    """Load image_tags.json."""
    if not TAGS_FILE.exists():
        return {}
    with open(TAGS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_tags(tags):
    """Save image_tags.json."""
    with open(TAGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tags, f, indent=2, ensure_ascii=False)
    print(f"   ✅ Saved to {TAGS_FILE}")


def get_all_images():
    """Get all PNG images in charts folder."""
    if not CHARTS_DIR.exists():
        return []
    return sorted([f.name for f in CHARTS_DIR.glob('*.png')])


def get_existing_concepts():
    """Load all concept titles from wiki."""
    concepts = []
    for file in sorted(WIKI_DIR.glob('Concept-*.md')):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line.startswith('# '):
                    concepts.append(first_line[2:].strip())
        except Exception:
            pass
    return concepts


def is_unmapped(value):
    """Check if a tag value still needs mapping (is a list of strings)."""
    if isinstance(value, list) and len(value) > 0:
        return isinstance(value[0], str)
    if isinstance(value, str):
        return True
    return False


def list_untagged():
    """Show all images and their tag status."""
    images = get_all_images()
    tags = load_tags()

    if not images:
        print("No images found in MBAWiki/assets/charts/")
        return

    print(f"\n📊 Images in MBAWiki/assets/charts/ ({len(images)} total)")
    print(f"{'='*60}")

    untagged = 0
    captioned = 0
    mapped = 0

    for img in images:
        if img not in tags:
            print(f"  ❌ {img}  (no caption)")
            untagged += 1
        elif is_unmapped(tags[img]):
            # Has captions but not mapped yet
            captions = tags[img] if isinstance(tags[img], list) else [tags[img]]
            print(f"  📝 {img}  → {len(captions)} caption(s)")
            for c in captions:
                print(f"       \"{c}\"")
            captioned += 1
        elif isinstance(tags[img], list):
            # Mapped (list of dicts)
            print(f"  ✅ {img}  → {len(tags[img])} mapping(s)")
            for m in tags[img]:
                print(f"       → {m['concept']}  \"{m['caption']}\"")
            mapped += 1

    print(f"\n  Summary: {mapped} mapped | {captioned} captioned (need --map) | {untagged} untagged")

    if untagged > 0:
        print(f"\n  💡 To tag images, edit: {TAGS_FILE}")
        print(f"     Format (multiple captions per image):")
        print(f'     "{images[0]}": ["caption 1", "caption 2"]')
        print(f"     Or single caption:")
        print(f'     "{images[0]}": ["caption 1"]')


def map_captions_to_concepts():
    """Use 1 Gemini API call to map all captions to concepts."""
    tags = load_tags()
    concepts = get_existing_concepts()

    if not concepts:
        print("❌ No concepts found in MBAWiki/")
        return

    # Find images that have captions but no concept mapping yet
    to_map = {}
    for img, value in tags.items():
        if is_unmapped(value):
            captions = value if isinstance(value, list) else [value]
            to_map[img] = captions

    if not to_map:
        print("No captions to map. Add captions to image_tags.json first.")
        print(f"  💡 Run: python tag_images.py --list")
        return

    total_captions = sum(len(v) for v in to_map.values())
    print(f"\n🤖 Mapping {total_captions} captions across {len(to_map)} images to {len(concepts)} concepts (1 API call)...")

    # Build prompt
    captions_json = json.dumps(to_map, indent=2)
    concepts_list = "\n".join(f"- {c}" for c in concepts)

    prompt = f"""Map each image caption to the most relevant concept from the list.
Each image has one or more captions. Map EACH caption to a concept independently.

IMAGE CAPTIONS (each image has a list of captions):
{captions_json}

AVAILABLE CONCEPTS:
{concepts_list}

RESPOND ONLY WITH JSON (no markdown):
{{
  "mappings": {{
    "image.png": [
      {{"caption": "the original caption text", "concept": "Exact Concept Title"}},
      {{"caption": "another caption", "concept": "Different Concept Title"}}
    ]
  }}
}}

RULES:
- Use the EXACT concept title from the list
- Map each caption independently - same image can map to different concepts
- If a caption doesn't match any concept well, set concept to null
- Preserve the original caption text exactly
"""

    try:
        api_key = os.getenv('Gemini_Api_Key')
        if not api_key:
            print("❌ Gemini_Api_Key not found in .env")
            return

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)

        response_text = response.text
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        result = json.loads(response_text[start_idx:end_idx])
        mappings = result.get('mappings', {})

        # Update tags with concept mappings
        for img, caption_mappings in mappings.items():
            if img in tags:
                valid = [m for m in caption_mappings if m.get('concept')]
                if valid:
                    tags[img] = valid
                    for m in valid:
                        print(f"  ✅ {img} → {m['concept']}  \"{m['caption']}\"")
                else:
                    print(f"  ⚠️  {img} → no matching concepts")

        save_tags(tags)
        print(f"\n✅ Done! Run 'python wiki_viewer/app.py' to see images in concepts.")

    except Exception as e:
        print(f"❌ Error: {e}")


def show_status():
    """Show current mapping status."""
    tags = load_tags()

    mapped_images = {}
    for img, value in tags.items():
        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
            for mapping in value:
                concept = mapping.get('concept', '')
                if concept:
                    if concept not in mapped_images:
                        mapped_images[concept] = []
                    mapped_images[concept].append({
                        'filename': img,
                        'caption': mapping.get('caption', '')
                    })

    if not mapped_images:
        print("No images mapped to concepts yet.")
        print("  💡 Run: python tag_images.py --list")
        return

    print(f"\n📊 Image Mappings")
    print(f"{'='*60}")
    for concept in sorted(mapped_images.keys()):
        print(f"\n  📖 {concept}")
        for img in mapped_images[concept]:
            print(f"     📈 {img['filename']}")
            if img['caption']:
                print(f"        \"{img['caption']}\"")

    total = sum(len(v) for v in mapped_images.values())
    print(f"\n  Total: {total} image-concept mappings across {len(mapped_images)} concepts")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python tag_images.py --list     # Show untagged images")
        print("  python tag_images.py --map      # Map captions to concepts (1 API call)")
        print("  python tag_images.py --status   # Show current mappings")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == '--list':
        list_untagged()
    elif cmd == '--map':
        map_captions_to_concepts()
    elif cmd == '--status':
        show_status()
    else:
        print(f"Unknown command: {cmd}")
        print("Use --list, --map, or --status")
