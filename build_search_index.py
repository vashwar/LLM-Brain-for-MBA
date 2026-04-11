"""
build_search_index.py

Build a local semantic search index over MBAWiki/Concept-*.md and Case-*.md files.
Uses fastembed (ONNX-based, no PyTorch) with BAAI/bge-small-en-v1.5 (384-dim).

Outputs:
    MBAWiki/assets/search_index.npz     (float32 embeddings, shape N x 384)
    MBAWiki/assets/search_metadata.json (list of {slug, title, type, course, preview, mtime})

Usage:
    python build_search_index.py            # full rebuild (re-embed everything)
    python build_search_index.py --append   # incremental (re-embed only files whose mtime changed)

Programmatic:
    from build_search_index import build_index
    total, updated = build_index(append_mode=True)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np

# Paths
REPO_DIR = Path(__file__).parent
WIKI_DIR = REPO_DIR / "MBAWiki"
ASSETS_DIR = WIKI_DIR / "assets"
INDEX_PATH = ASSETS_DIR / "search_index.npz"
METADATA_PATH = ASSETS_DIR / "search_metadata.json"
LOG_FILE = REPO_DIR / "log.md"

CONCEPT_PREFIX = "Concept-"
CASE_PREFIX = "Case-"
SUFFIX = ".md"

# Embedding config
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384
BATCH_SIZE = 32
EMBED_TEXT_BODY_CHARS = 800
PREVIEW_CHARS = 200

# Regexes for markdown stripping
_RE_TITLE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_RE_COURSE = re.compile(r"^\*\*Course:\*\*\s*(.+)$", re.MULTILINE)
_RE_HEADER = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_RE_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_RE_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_RE_CODE_BLOCK = re.compile(r"```[\s\S]*?```")
_RE_INLINE_CODE = re.compile(r"`([^`]+)`")
_RE_IMAGE = re.compile(r"!\[[^\]]*\]\([^\)]*\)")
_RE_LINK = re.compile(r"\[([^\]]+)\]\([^\)]*\)")
_RE_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_WHITESPACE = re.compile(r"\s+")


def _strip_markdown(text: str) -> str:
    """Strip common markdown syntax to get cleaner embedding text."""
    text = _RE_CODE_BLOCK.sub(" ", text)
    text = _RE_IMAGE.sub(" ", text)
    text = _RE_LINK.sub(r"\1", text)
    text = _RE_WIKILINK.sub(r"\1", text)
    text = _RE_INLINE_CODE.sub(r"\1", text)
    text = _RE_BOLD.sub(r"\1", text)
    text = _RE_ITALIC.sub(r"\1", text)
    text = _RE_HEADER.sub("", text)
    text = _RE_HTML_TAG.sub(" ", text)
    text = _RE_WHITESPACE.sub(" ", text)
    return text.strip()


def _extract_title(content: str, fallback_slug: str) -> str:
    m = _RE_TITLE.search(content)
    if m:
        return m.group(1).strip()
    return fallback_slug.replace("-", " ").title()


def _extract_course(content: str) -> str:
    """Extract first course name from first ~10 lines. Returns 'Uncategorized' if not found."""
    head = "\n".join(content.splitlines()[:10])
    m = _RE_COURSE.search(head)
    if not m:
        return "Uncategorized"
    course_str = m.group(1).strip()
    parts = [c.strip() for c in course_str.split(",") if c.strip()]
    return parts[0] if parts else "Uncategorized"


def _slug_from_path(path: Path) -> tuple[str, str]:
    """Return (slug, type) where type is 'concept' or 'case'."""
    stem = path.stem
    if stem.startswith(CONCEPT_PREFIX):
        return stem[len(CONCEPT_PREFIX):], "concept"
    if stem.startswith(CASE_PREFIX):
        return stem[len(CASE_PREFIX):], "case"
    return stem, "concept"


def _build_embed_text(title: str, body: str) -> str:
    """Combine title and leading body text for embedding input."""
    stripped = _strip_markdown(body)
    return f"{title}\n{stripped[:EMBED_TEXT_BODY_CHARS]}"


def _build_preview(body: str) -> str:
    """Build a short plain-text preview for search result snippets."""
    stripped = _strip_markdown(body)
    if len(stripped) <= PREVIEW_CHARS:
        return stripped
    return stripped[:PREVIEW_CHARS].rstrip() + "…"


def _iter_wiki_files() -> Iterable[Path]:
    """Yield all Concept-*.md and Case-*.md files in MBAWiki/."""
    yield from sorted(WIKI_DIR.glob(f"{CONCEPT_PREFIX}*{SUFFIX}"))
    yield from sorted(WIKI_DIR.glob(f"{CASE_PREFIX}*{SUFFIX}"))


def _scan_files() -> list[dict]:
    """Scan all wiki files and return list of records (without embeddings).

    Each record: {slug, title, type, course, preview, mtime, path, embed_text}
    """
    records: list[dict] = []
    for path in _iter_wiki_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"   Warning: Could not read {path.name}: {e}")
            continue

        slug, ftype = _slug_from_path(path)
        title = _extract_title(content, slug)
        course = _extract_course(content)

        # Body is content after the first H1 line (if present)
        m = _RE_TITLE.search(content)
        body = content[m.end():] if m else content

        records.append({
            "slug": slug,
            "title": title,
            "type": ftype,
            "course": course,
            "preview": _build_preview(body),
            "mtime": path.stat().st_mtime,
            "path": str(path),
            "embed_text": _build_embed_text(title, body),
        })
    return records


def _load_existing() -> tuple[np.ndarray | None, list[dict] | None]:
    """Load existing index + metadata, or (None, None) if either is missing."""
    if not INDEX_PATH.exists() or not METADATA_PATH.exists():
        return None, None
    try:
        data = np.load(INDEX_PATH)
        embeddings = data["embeddings"]
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        if embeddings.shape[0] != len(metadata):
            print(f"   Warning: index/metadata row count mismatch ({embeddings.shape[0]} vs {len(metadata)}), rebuilding")
            return None, None
        return embeddings, metadata
    except Exception as e:
        print(f"   Warning: Could not load existing index ({e}), rebuilding")
        return None, None


def _embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a list of texts using fastembed. Returns float32 array of shape (N, EMBED_DIM)."""
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=MODEL_NAME)
    vectors: list[np.ndarray] = []
    for vec in model.embed(texts, batch_size=BATCH_SIZE):
        vectors.append(np.asarray(vec, dtype=np.float32))
    arr = np.stack(vectors, axis=0) if vectors else np.zeros((0, EMBED_DIM), dtype=np.float32)
    # Normalize (bge models are already L2-normalized, but be safe).
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (arr / norms).astype(np.float32)


def _log_build(total: int, updated: int, mode: str) -> None:
    """Append an entry to log.md matching process_single_file.log_ingestion format."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode_label = "full-rebuild" if mode == "full" else "incremental"
        entry = (
            f"## [{timestamp}] index | Search index {mode_label}: "
            f"{total} entries ({updated} re-embedded)\n"
        )
        if LOG_FILE.exists():
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(entry)
        else:
            header = "# Wiki Evolution Log\n\nAppend-only record of ingestions and updates.\n\n"
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(header)
                f.write(entry)
    except Exception as e:
        print(f"   Warning: Could not log index entry: {e}")


def build_index(append_mode: bool = False) -> tuple[int, int]:
    """Build or update the search index.

    Args:
        append_mode: If True, only re-embed files whose mtime differs from the cached value.
                     If False, re-embed everything.

    Returns:
        (total_entries, num_re_embedded)
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    records = _scan_files()
    if not records:
        print("   No wiki files found.")
        return 0, 0

    existing_embeddings, existing_metadata = (None, None)
    if append_mode:
        existing_embeddings, existing_metadata = _load_existing()

    if append_mode and existing_embeddings is not None and existing_metadata is not None:
        # Build a lookup from (slug, type) -> (row_index, cached_mtime)
        cache: dict[tuple[str, str], tuple[int, float]] = {
            (m["slug"], m["type"]): (i, m.get("mtime", 0.0))
            for i, m in enumerate(existing_metadata)
        }

        new_embeddings = np.zeros((len(records), EMBED_DIM), dtype=np.float32)
        new_metadata: list[dict] = []
        to_embed_indices: list[int] = []
        to_embed_texts: list[str] = []

        for i, rec in enumerate(records):
            key = (rec["slug"], rec["type"])
            cached = cache.get(key)
            if cached is not None and abs(cached[1] - rec["mtime"]) < 1e-6:
                # Reuse existing embedding
                new_embeddings[i] = existing_embeddings[cached[0]]
            else:
                to_embed_indices.append(i)
                to_embed_texts.append(rec["embed_text"])
            new_metadata.append({
                "slug": rec["slug"],
                "title": rec["title"],
                "type": rec["type"],
                "course": rec["course"],
                "preview": rec["preview"],
                "mtime": rec["mtime"],
            })

        if to_embed_texts:
            fresh = _embed_texts(to_embed_texts)
            for idx, vec in zip(to_embed_indices, fresh):
                new_embeddings[idx] = vec

        embeddings = new_embeddings
        metadata = new_metadata
        updated = len(to_embed_texts)
        mode = "incremental"
    else:
        # Full rebuild
        texts = [rec["embed_text"] for rec in records]
        embeddings = _embed_texts(texts)
        metadata = [
            {
                "slug": rec["slug"],
                "title": rec["title"],
                "type": rec["type"],
                "course": rec["course"],
                "preview": rec["preview"],
                "mtime": rec["mtime"],
            }
            for rec in records
        ]
        updated = len(records)
        mode = "full"

    # Write outputs
    np.savez(INDEX_PATH, embeddings=embeddings)
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    total = len(metadata)
    _log_build(total, updated, mode)
    return total, updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Build semantic search index for MBAWiki")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Incremental mode: only re-embed files whose mtime changed",
    )
    args = parser.parse_args()

    mode_label = "incremental" if args.append else "full rebuild"
    print(f"Building search index ({mode_label})...")
    print(f"   Wiki dir: {WIKI_DIR}")
    print(f"   Model:    {MODEL_NAME}")

    try:
        total, updated = build_index(append_mode=args.append)
    except ImportError as e:
        print(f"\nError: fastembed is not installed.")
        print(f"       Install with: pip install fastembed")
        print(f"       ({e})")
        return 1
    except Exception as e:
        print(f"\nError building index: {e}")
        return 1

    print(f"\n[OK] Indexed {total} entries ({updated} re-embedded)")
    print(f"   {INDEX_PATH}")
    print(f"   {METADATA_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
