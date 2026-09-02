#!/usr/bin/env python3
"""Fetch course files from Google Drive without processing them.

The LLM-free half of the ingest pipeline. Downloads unprocessed lecture, case,
and transcript files for a course, cleans caption files into readable prose, and
lets you mark files done once their wiki pages exist.

Use this when the concept/case pages are authored by hand (or by Claude Code)
instead of by Gemini. For the fully automated Gemini pipeline, use
`process_standalone.py --course "CourseName"` instead.

All Drive, tracker, and path logic is reused from process_standalone.py — this
script adds no new pipeline behaviour and does not write to MBAWiki/.

Usage:
    python ingest/fetch_course_files.py --course "Negotiations"
    python ingest/fetch_course_files.py --course "Negotiations" --status
    python ingest/fetch_course_files.py --course "Negotiations" --all
    python ingest/fetch_course_files.py --course "Negotiations" \
        --mark lectures:"Week 2 Slides.pdf"
"""

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ingest.process_standalone import (  # noqa: E402
    LOCAL_DIR,
    download_file,
    is_file_processed,
    list_files_in_folder,
    load_courses,
    load_tracker,
    mark_file_processed,
    setup_google_drive,
    sort_files,
)

# (config key, tracker file_type, subdirectory under the course folder)
PHASES = [
    ("lectures_folder_id", "lectures", None),
    ("cases_folder_id", "cases", "cases"),
    ("transcripts_folder_id", "transcripts", "transcripts"),
]

CAPTION_SUFFIXES = (".txt", ".vtt", ".srt")


def phase_dir(course_name, subdir):
    base = LOCAL_DIR / course_name
    return base / subdir if subdir else base


def clean_captions(path):
    """Strip WebVTT/SRT timestamps and duplicate cues into flowing prose.

    Writes <name>.clean.txt beside the original and returns its path, or None if
    the file is not a caption file. Existing .clean.txt files are overwritten.
    """
    path = Path(path)
    if path.suffix.lower() not in CAPTION_SUFFIXES:
        return None

    raw = path.read_text(encoding="utf-8", errors="replace")
    kept = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or "-->" in s:
            continue
        if re.fullmatch(r"\d+", s):          # cue numbers
            continue
        if s.upper().startswith("WEBVTT"):
            continue
        if kept and kept[-1] == s:           # repeated rolling captions
            continue
        kept.append(s)

    text = re.sub(r"\s+", " ", " ".join(kept)).strip()
    out = path.with_suffix(".clean.txt")
    out.write_text(text, encoding="utf-8")
    return out


def unprocessed_for(service, course_name, config, tracker):
    """Return [(file_type, subdir, file_info)] for everything not yet marked done."""
    pending = []
    for key, file_type, subdir in PHASES:
        folder_id = config.get(key)
        if not folder_id:
            continue
        files = sort_files(list_files_in_folder(service, folder_id))
        for info in files:
            if not is_file_processed(tracker, course_name, file_type, info["name"]):
                pending.append((file_type, subdir, info))
    return pending


def cmd_status(service, course_name, config, tracker):
    done = tracker.get(course_name, {})
    print(f"\n  {course_name}")
    for key, file_type, _ in PHASES:
        folder_id = config.get(key)
        if not folder_id:
            print(f"    {file_type:12} (no folder configured)")
            continue
        files = sort_files(list_files_in_folder(service, folder_id))
        marked = done.get(file_type, {})
        pending = [f for f in files if f["name"] not in marked]
        print(f"    {file_type:12} {len(files) - len(pending)}/{len(files)} processed")
        for f in pending:
            print(f"       pending: {f['name']}")
    return 0


def cmd_fetch(service, course_name, config, tracker, fetch_all):
    pending = unprocessed_for(service, course_name, config, tracker)
    if not pending:
        print(f"\n  Nothing to fetch — all {course_name} files are marked processed.")
        return 0

    total = len(pending)
    if not fetch_all:
        pending = pending[:1]
        print(f"\n  Fetching 1 file (use --all for all {total}).")
    else:
        print(f"\n  Fetching {total} unprocessed file(s).")

    downloaded = []
    for file_type, subdir, info in pending:
        target = phase_dir(course_name, subdir)
        print(f"\n  [{file_type.upper()}] {info['name']}")
        local = download_file(service, info["id"], info["name"], target)
        if not local:
            print("     download failed — skipping")
            continue
        entry = {"type": file_type, "name": info["name"], "path": local}
        cleaned = clean_captions(local)
        if cleaned:
            entry["clean"] = str(cleaned)
            print(f"     cleaned captions -> {cleaned.name}")
        downloaded.append(entry)

    print(f"\n{'=' * 70}")
    print("  READY TO AUTHOR — read these, then write the wiki pages:")
    print(f"{'=' * 70}")
    for e in downloaded:
        print(f"\n  [{e['type']}] {e['path']}")
        if "clean" in e:
            print(f"           read this instead: {e['clean']}")
    print(f"\n  When a file's pages exist, mark it done:")
    for e in downloaded:
        print(f'    python ingest/fetch_course_files.py --course "{course_name}" '
              f'--mark {e["type"]}:"{e["name"]}"')
    print()
    return 0


def cmd_mark(course_name, spec):
    if ":" not in spec:
        print('  Error: --mark expects file_type:filename, e.g. lectures:"Week 2.pdf"')
        return 1
    file_type, filename = spec.split(":", 1)
    file_type, filename = file_type.strip(), filename.strip().strip('"')
    valid = {ft for _, ft, _ in PHASES}
    if file_type not in valid:
        print(f"  Error: file_type must be one of {sorted(valid)}")
        return 1

    tracker = load_tracker()
    if is_file_processed(tracker, course_name, file_type, filename):
        print(f"  Already marked: [{file_type}] {filename}")
        return 0
    mark_file_processed(tracker, course_name, file_type, filename)
    print(f"  Marked processed: [{file_type}] {filename}")
    print("  Remember to refresh derived artifacts:")
    print("    python ingest/build_search_index.py --append")
    print("    python ingest/build_graph.py")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Download course files from Drive without running the LLM pipeline.")
    parser.add_argument("--course", required=True, help="Course name as it appears in courses.json")
    parser.add_argument("--status", action="store_true", help="Show processed/pending counts and exit")
    parser.add_argument("--all", action="store_true", help="Fetch every unprocessed file, not just the next one")
    parser.add_argument("--mark", metavar="TYPE:NAME", help='Mark a file processed, e.g. lectures:"Week 2.pdf"')
    args = parser.parse_args()

    courses = load_courses()
    if args.course not in courses:
        print(f"  Course not found: {args.course}")
        print(f"  Available: {', '.join(courses.keys())}")
        return 1
    config = courses[args.course]

    # Marking touches only the local tracker — no Drive round-trip needed.
    if args.mark:
        return cmd_mark(args.course, args.mark)

    service = setup_google_drive()
    if not service:
        print("  Google Drive auth failed. Run this yourself if a browser consent screen is needed.")
        return 1

    tracker = load_tracker()
    if args.status:
        return cmd_status(service, args.course, config, tracker)
    return cmd_fetch(service, args.course, config, tracker, args.all)


if __name__ == "__main__":
    sys.exit(main())
