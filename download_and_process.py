#!/usr/bin/env python3
"""
Download and Process Files from Google Drive - Multi-Course Support

Usage:
    python download_and_process.py                                              (list courses)
    python download_and_process.py --course "Microeconomics"                    (list files in course)
    python download_and_process.py --course "Microeconomics" "Week 1"           (process single file)
    python download_and_process.py --course "Microeconomics" --all              (process all: lectures + cases + transcripts)
    python download_and_process.py --course "Microeconomics" --all --images     (with image extraction)
    python download_and_process.py --course "Microeconomics" --cases-only       (process only case reviews)
    python download_and_process.py --course "Microeconomics" --transcripts-only (process only transcripts)

--all processes lectures first, then cases, then transcripts.
Skips already-processed files (tracked in processed_files.json).
15-30s delay between files for free Gemini tier rate limits.
"""

import os
import sys
import subprocess
import re
import json
import time
import random
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

COURSES_FILE = Path('courses.json')
TRACKER_FILE = Path('processed_files.json')
LOCAL_DIR = Path('Transcript_class_lecture')
LOG_FILE = Path('log.md')


def load_courses():
    """Load course configuration from courses.json."""
    if not COURSES_FILE.exists():
        print("No courses.json found. Create one with course folder IDs.")
        print('Example:\n{')
        print('  "Microeconomics": {')
        print('    "lectures_folder_id": "YOUR_FOLDER_ID",')
        print('    "cases_folder_id": null,')
        print('    "transcripts_folder_id": null')
        print('  }')
        print('}')
        sys.exit(1)

    with open(COURSES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_tracker():
    """Load processed files tracker."""
    if not TRACKER_FILE.exists():
        return {}
    with open(TRACKER_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_tracker(tracker):
    """Save processed files tracker."""
    with open(TRACKER_FILE, 'w', encoding='utf-8') as f:
        json.dump(tracker, f, indent=2)


def is_file_processed(tracker, course_name, file_type, filename):
    """Check if a file has already been processed."""
    return (course_name in tracker
            and file_type in tracker[course_name]
            and filename in tracker[course_name][file_type])


def mark_file_processed(tracker, course_name, file_type, filename):
    """Mark a file as processed in the tracker."""
    if course_name not in tracker:
        tracker[course_name] = {}
    if file_type not in tracker[course_name]:
        tracker[course_name][file_type] = {}
    tracker[course_name][file_type][filename] = datetime.now(timezone.utc).isoformat()
    save_tracker(tracker)


def log_batch_operation(course_name, operation, file_type, file_count):
    """Log a batch operation to log.md.

    Args:
        course_name: e.g., "Microeconomics"
        operation: e.g., "ingest", "complete"
        file_type: e.g., "lectures", "cases", "transcripts"
        file_count: number of files processed
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format: ## [2026-04-10 17:30:00] {operation} | {course}: {file_type} ({count} files)
        entry = f"## [{timestamp}] {operation} | {course_name}: {file_type.capitalize()} ({file_count} files)\n"

        # Append to log.md
        if LOG_FILE.exists():
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(entry)
        else:
            # If log doesn't exist yet, create it with header
            header = "# Wiki Evolution Log\n\nAppend-only record of ingestions and updates.\n\n"
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                f.write(header)
                f.write(entry)
    except Exception as e:
        # Don't fail processing if logging fails
        print(f"   Warning: Could not log batch operation: {e}")


def setup_google_drive():
    """Authenticate with Google Drive."""
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    import os

    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    creds = None

    # Check if token.json exists and load it
    if os.path.exists('credentials/token.json'):
        try:
            creds = Credentials.from_authorized_user_file('credentials/token.json', SCOPES)
        except Exception as e:
            print(f"Warning: Could not load existing token: {e}")
            creds = None

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired token
            try:
                print("Refreshing expired token...")
                creds.refresh(Request())
            except Exception as e:
                print(f"Could not refresh token: {e}")
                print("Starting new authentication flow...")
                creds = None

        if not creds:
            # Run OAuth flow to get new credentials
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials/credentials.json', SCOPES)
                print("\nOpening browser for Google Drive authentication...")
                print("Please authorize access to your Google Drive.\n")
                creds = flow.run_local_server(port=0)
            except Exception as e:
                print(f"Error during authentication: {e}")
                return None

        # Save the credentials for future runs
        try:
            with open('credentials/token.json', 'w') as token:
                token.write(creds.to_json())
            print("✓ Authentication successful! Token saved to credentials/token.json\n")
        except Exception as e:
            print(f"Warning: Could not save token: {e}")

    # Build and return the service
    try:
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"Error: {e}")
        return None


def list_files_in_folder(service, folder_id):
    """List all files in a Google Drive folder."""
    try:
        query = f"'{folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, mimeType, modifiedTime)',
            pageSize=100,
            orderBy='modifiedTime desc'
        ).execute()

        return results.get('files', [])
    except Exception as e:
        print(f"Error: {e}")
        return []


def find_file(service, folder_id, filename):
    """Find a file by name (exact or partial match)."""
    files = list_files_in_folder(service, folder_id)

    # Exact match
    for file in files:
        if file['name'] == filename:
            return file

    # Case-insensitive partial match
    filename_lower = filename.lower()
    for file in files:
        if filename_lower in file['name'].lower():
            return file

    return None


def download_file(service, file_id, filename, course_dir):
    """Download a file from Google Drive to the course subdirectory."""
    try:
        course_dir.mkdir(parents=True, exist_ok=True)

        output_file = course_dir / filename

        # Skip if already downloaded
        if output_file.exists():
            file_size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"   Already downloaded: {filename} ({file_size_mb:.1f} MB)")
            return str(output_file)

        request = service.files().get_media(fileId=file_id)

        print(f"   Downloading: {filename}")

        with open(output_file, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()

        file_size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"   Downloaded: {file_size_mb:.1f} MB")
        return str(output_file)

    except Exception as e:
        print(f"   Download failed: {e}")
        return None


def process_file(filepath, course_name, extract_images=False, file_type="lectures"):
    """Run the process_single_file.py script with course info."""
    try:
        lower = filepath.lower()
        is_long = lower.endswith('.pdf') or lower.endswith('.docx')
        timeout_seconds = 300 if is_long else 120

        cmd = [sys.executable, 'process_single_file.py', filepath, '--course', course_name]
        if file_type == "cases":
            cmd.extend(['--type', 'case'])
        elif file_type == "transcripts":
            cmd.extend(['--type', 'transcript'])
        if not extract_images:
            cmd.append('--no-images')

        result = subprocess.run(
            cmd,
            check=True,
            timeout=timeout_seconds
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"   Processing timed out (>{timeout_seconds}s)")
        return False
    except subprocess.CalledProcessError as e:
        print(f"   Processing failed: {e}")
        return False
    except Exception as e:
        print(f"   Error: {e}")
        return False


def rate_limit_delay():
    """Wait 15-30s between files to respect free Gemini tier rate limits."""
    delay = random.uniform(15, 30)
    print(f"\n   Waiting {delay:.0f}s before next file (rate limit)...")
    time.sleep(delay)


def get_week_number(filename):
    """Extract week number from filename for sorting. Returns 999 if no week found."""
    match = re.search(r'[Ww]eek\s*(\d+)', filename)
    if match:
        return int(match.group(1))
    # Try date-based files (e.g. 8_24_2024)
    match = re.search(r'(\d{1,2})_(\d{1,2})_(\d{4})', filename)
    if match:
        month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return month * 100 + day  # Sort by date
    return 999


def sort_files_for_processing(files):
    """Sort files: PDFs first (by week), then DOCX, then TXTs (by week/date)."""
    pdfs = [f for f in files if f['name'].lower().endswith('.pdf')]
    docxs = [f for f in files if f['name'].lower().endswith('.docx')]
    txts = [f for f in files if f['name'].lower().endswith('.txt')]

    pdfs.sort(key=lambda f: get_week_number(f['name']))
    docxs.sort(key=lambda f: get_week_number(f['name']))
    txts.sort(key=lambda f: get_week_number(f['name']))

    return pdfs + docxs + txts


def process_all(service, course_name, folder_id, course_dir, file_type="lectures", extract_images=False):
    """Download and process all files for a course. Skips already-processed files."""
    files = list_files_in_folder(service, folder_id)

    if not files:
        print(f"No {file_type} files found")
        return

    sorted_files = sort_files_for_processing(files)
    tracker = load_tracker()

    # Filter out already-processed files
    to_process = []
    skipped = []
    for f in sorted_files:
        if is_file_processed(tracker, course_name, file_type, f['name']):
            skipped.append(f['name'])
        else:
            to_process.append(f)

    if skipped:
        print(f"\n   Skipping {len(skipped)} already-processed files:")
        for name in skipped:
            print(f"      {name}")

    if not to_process:
        print(f"\n   All files already processed! Delete entries from processed_files.json to reprocess.")
        return

    pdfs = [f for f in to_process if f['name'].lower().endswith('.pdf')]
    docxs = [f for f in to_process if f['name'].lower().endswith('.docx')]
    txts = [f for f in to_process if f['name'].lower().endswith('.txt')]

    print(f"\n   Processing: {len(pdfs)} PDFs, {len(docxs)} DOCXs, {len(txts)} TXTs ({len(skipped)} skipped)")
    print(f"   Image extraction: {'ON' if extract_images else 'OFF'}")
    print(f"{'='*60}")

    succeeded = 0
    failed = 0
    failed_files = []

    for i, file_info in enumerate(to_process, 1):
        # Rate limit delay between files (not before first)
        if i > 1:
            rate_limit_delay()

        ext = Path(file_info['name']).suffix.upper()
        print(f"\n{'='*60}")
        print(f"[{i}/{len(to_process)}] {ext} | {file_info['name']}")
        print(f"{'='*60}")

        # Download
        local_path = download_file(service, file_info['id'], file_info['name'], course_dir)
        if not local_path:
            failed += 1
            failed_files.append(file_info['name'])
            continue

        # Process (skip image extraction for TXT files regardless of flag)
        is_pdf = file_info['name'].lower().endswith('.pdf')
        use_images = extract_images and is_pdf

        success = process_file(local_path, course_name, extract_images=use_images, file_type=file_type)

        if success:
            succeeded += 1
            mark_file_processed(tracker, course_name, file_type, file_info['name'])
        else:
            failed += 1
            failed_files.append(file_info['name'])

    # Final summary
    print(f"\n{'='*60}")
    print(f"BATCH COMPLETE")
    print(f"{'='*60}")
    print(f"   Succeeded: {succeeded}/{len(to_process)}")
    print(f"   Failed:    {failed}/{len(to_process)}")
    print(f"   Skipped:   {len(skipped)} (already processed)")

    if failed_files:
        print(f"\n   Failed files:")
        for f in failed_files:
            print(f"   - {f}")

    print(f"\n   Next steps:")
    print(f"   1. Review concepts in MBAWiki/")
    print(f"   2. python wiki_viewer/app.py")
    print(f"   3. http://127.0.0.1:5000/")


def process_single(service, course_name, folder_id, course_dir, filename):
    """Download and process a single file."""
    print(f"\n   Searching: {filename}")

    file_info = find_file(service, folder_id, filename)

    if not file_info:
        print(f"   File not found: {filename}")
        print(f"\n   Available files:")
        files = list_files_in_folder(service, folder_id)
        for file in files:
            print(f"   - {file['name']}")
        sys.exit(1)

    print(f"   Found: {file_info['name']}")

    # Download
    local_path = download_file(service, file_info['id'], file_info['name'], course_dir)
    if not local_path:
        sys.exit(1)

    # Process
    print("\n" + "=" * 60)
    success = process_file(local_path, course_name)

    if success:
        # Mark as processed
        tracker = load_tracker()
        mark_file_processed(tracker, course_name, "lectures", file_info['name'])

        print("\n" + "=" * 60)
        print("Complete!")
        print(f"\nYour concepts were created in MBAWiki/")
        print(f"Restart the wiki to see them:")
        print(f"   python wiki_viewer/app.py")
        print(f"   http://127.0.0.1:5000/")
    else:
        print("\nProcessing failed")
        sys.exit(1)


def parse_args():
    """Parse command line arguments."""
    args = sys.argv[1:]
    parsed = {
        'course': None,
        'all': '--all' in args,
        'cases_only': '--cases-only' in args,
        'transcripts_only': '--transcripts-only' in args,
        'images': '--images' in args,
        'filename': None,
    }

    # Extract --course value
    if '--course' in args:
        idx = args.index('--course')
        if idx + 1 < len(args):
            parsed['course'] = args[idx + 1]

    # Find filename (positional arg that's not a flag or flag value)
    skip_next = False
    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == '--course':
            skip_next = True
            continue
        if arg.startswith('--'):
            continue
        parsed['filename'] = arg

    return parsed


def main():
    """Main function."""
    courses = load_courses()
    parsed = parse_args()

    print("Google Drive Transcript Processor")
    print("=" * 60)

    # No --course: list available courses
    if not parsed['course']:
        print(f"\nAvailable courses:\n")
        for name, config in courses.items():
            has_cases = "yes" if config.get('cases_folder_id') else "no"
            has_transcripts = "yes" if config.get('transcripts_folder_id') else "no"
            print(f"   {name}")
            print(f"      Lectures folder: {config['lectures_folder_id']}")
            print(f"      Cases folder: {has_cases}")
            print(f"      Transcripts folder: {has_transcripts}")
            print()

        print(f"Usage:")
        print(f'   python download_and_process.py --course "CourseName"              # list files')
        print(f'   python download_and_process.py --course "CourseName" --all        # process all')
        print(f'   python download_and_process.py --course "CourseName" "Week 1"     # single file')
        sys.exit(0)

    course_name = parsed['course']

    # Validate course exists
    if course_name not in courses:
        print(f"\nCourse not found: {course_name}")
        print(f"Available courses: {', '.join(courses.keys())}")
        print(f"\nAdd it to courses.json with the Google Drive folder ID.")
        sys.exit(1)

    course_config = courses[course_name]
    lectures_folder_id = course_config['lectures_folder_id']
    cases_folder_id = course_config.get('cases_folder_id')
    transcripts_folder_id = course_config.get('transcripts_folder_id')
    course_dir = LOCAL_DIR / course_name

    # Setup Google Drive
    service = setup_google_drive()
    if not service:
        sys.exit(1)

    print(f"Course: {course_name}")

    # No filename and no --all: list files
    if not parsed['all'] and not parsed['filename'] and not parsed['cases_only'] and not parsed['transcripts_only']:
        tracker = load_tracker()

        print(f"\nLectures:\n")
        files = list_files_in_folder(service, lectures_folder_id)
        if not files:
            print("   No files found")
        else:
            for i, file in enumerate(files, 1):
                status = ""
                if is_file_processed(tracker, course_name, "lectures", file['name']):
                    status = " [processed]"
                print(f"   {i:2d}. {file['name']}{status}")

        if cases_folder_id:
            print(f"\nCase Reviews:\n")
            case_files = list_files_in_folder(service, cases_folder_id)
            if not case_files:
                print("   No files found")
            else:
                for i, file in enumerate(case_files, 1):
                    status = ""
                    if is_file_processed(tracker, course_name, "cases", file['name']):
                        status = " [processed]"
                    print(f"   {i:2d}. {file['name']}{status}")

        if transcripts_folder_id:
            print(f"\nTranscripts:\n")
            transcript_files = list_files_in_folder(service, transcripts_folder_id)
            if not transcript_files:
                print("   No files found")
            else:
                for i, file in enumerate(transcript_files, 1):
                    status = ""
                    if is_file_processed(tracker, course_name, "transcripts", file['name']):
                        status = " [processed]"
                    print(f"   {i:2d}. {file['name']}{status}")

        print(f'\nUsage:')
        print(f'   python download_and_process.py --course "{course_name}" --all')
        print(f'   python download_and_process.py --course "{course_name}" "filename"')
        sys.exit(0)

    # --cases-only mode: process only case reviews
    if parsed['cases_only']:
        if cases_folder_id:
            print(f"\n--- Case Reviews ---")
            process_all(service, course_name, cases_folder_id, course_dir / "cases",
                        file_type="cases", extract_images=False)
        else:
            print(f"\n   No cases folder configured for {course_name}")
            print(f"   Add 'cases_folder_id' to courses.json for this course.")

    # --transcripts-only mode: process only transcripts
    elif parsed['transcripts_only']:
        if transcripts_folder_id:
            print(f"\n--- Transcripts ---")
            process_all(service, course_name, transcripts_folder_id, course_dir / "transcripts",
                        file_type="transcripts", extract_images=False)
        else:
            print(f"\n   No transcripts folder configured for {course_name}")
            print(f"   Add 'transcripts_folder_id' to courses.json for this course.")

    # --all mode: seed concepts, then lectures, then cases, then transcripts
    elif parsed['all']:
        # Seed foundational concepts first (no API calls)
        print(f"\n--- Seed Concepts ---")
        seed_cmd = [sys.executable, 'process_single_file.py', '--seed', '--course', course_name]
        try:
            subprocess.run(seed_cmd, check=True, timeout=30)
        except Exception as e:
            print(f"   Seed step failed (non-fatal): {e}")

        print(f"\n--- Lectures ---")
        lecture_files = list_files_in_folder(service, lectures_folder_id)
        process_all(service, course_name, lectures_folder_id, course_dir,
                    file_type="lectures", extract_images=parsed['images'])
        log_batch_operation(course_name, "ingest", "lectures", len(lecture_files))

        if cases_folder_id:
            print(f"\n--- Case Reviews ---")
            case_files = list_files_in_folder(service, cases_folder_id)
            process_all(service, course_name, cases_folder_id, course_dir / "cases",
                        file_type="cases", extract_images=False)
            log_batch_operation(course_name, "ingest", "cases", len(case_files))
        else:
            print(f"\n   No cases folder configured for {course_name}")

        if transcripts_folder_id:
            print(f"\n--- Transcripts ---")
            transcript_files = list_files_in_folder(service, transcripts_folder_id)
            process_all(service, course_name, transcripts_folder_id, course_dir / "transcripts",
                        file_type="transcripts", extract_images=False)
            log_batch_operation(course_name, "ingest", "transcripts", len(transcript_files))
        else:
            print(f"\n   No transcripts folder configured for {course_name}")

        # Log completion
        print(f"\n{'='*60}")
        print(f"✓ Logged to: log.md")
        print(f"{'='*60}")

        # Rebuild search index after batch ingestion
        try:
            from build_search_index import build_index
            total, updated = build_index(append_mode=False)  # full rebuild
            print(f"✓ Search index rebuilt: {total} entries")
        except ImportError:
            print(f"⚠ Search index skipped: fastembed not installed (run: pip install fastembed)")
        except Exception as e:
            print(f"⚠ Search index rebuild failed (non-fatal): {e}")
    else:
        # Single file mode
        process_single(service, course_name, lectures_folder_id, course_dir, parsed['filename'])


if __name__ == "__main__":
    main()
