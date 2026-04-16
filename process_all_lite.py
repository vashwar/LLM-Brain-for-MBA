#!/usr/bin/env python3
"""
Resilient Batch Processor - Gemini 3.1 Flash Lite Only

Uses ONLY gemini-3.1-flash-lite-preview with no fallback.
On any error, waits 30 minutes and retries from unprocessed files.
Loops until every file is processed.

Usage:
    python process_all_lite.py --course "Microeconomics"
    python process_all_lite.py --course "Microeconomics" --images
    python process_all_lite.py --course "Microeconomics" --wait 15   (custom wait: 15 mins)
"""

import os
import sys
import subprocess
import json
import time
import re
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
COURSES_FILE = Path('courses.json')
TRACKER_FILE = Path('processed_files.json')
LOCAL_DIR = Path('Transcript_class_lecture')
LOG_FILE = Path('log.md')
DEFAULT_WAIT_MINUTES = 30


def load_courses():
    with open(COURSES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_tracker():
    if not TRACKER_FILE.exists():
        return {}
    with open(TRACKER_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_tracker(tracker):
    with open(TRACKER_FILE, 'w', encoding='utf-8') as f:
        json.dump(tracker, f, indent=2)


def is_file_processed(tracker, course_name, file_type, filename):
    return (course_name in tracker
            and file_type in tracker[course_name]
            and filename in tracker[course_name][file_type])


def mark_file_processed(tracker, course_name, file_type, filename):
    if course_name not in tracker:
        tracker[course_name] = {}
    if file_type not in tracker[course_name]:
        tracker[course_name][file_type] = {}
    tracker[course_name][file_type][filename] = datetime.now(timezone.utc).isoformat()
    save_tracker(tracker)


def setup_google_drive():
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    creds = None

    if os.path.exists('credentials/token.json'):
        try:
            creds = Credentials.from_authorized_user_file('credentials/token.json', SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials/credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                print(f"Auth error: {e}")
                return None

        try:
            with open('credentials/token.json', 'w') as token:
                token.write(creds.to_json())
        except Exception:
            pass

    return build('drive', 'v3', credentials=creds)


def list_files_in_folder(service, folder_id):
    try:
        query = f"'{folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query, spaces='drive',
            fields='files(id, name, mimeType, modifiedTime)',
            pageSize=100, orderBy='modifiedTime desc'
        ).execute()
        return results.get('files', [])
    except Exception as e:
        print(f"Error listing files: {e}")
        return []


def get_week_number(filename):
    match = re.search(r'[Ww]eek\s*(\d+)', filename)
    if match:
        return int(match.group(1))
    match = re.search(r'(\d{1,2})_(\d{1,2})_(\d{4})', filename)
    if match:
        return int(match.group(1)) * 100 + int(match.group(2))
    return 999


def sort_files(files):
    pdfs = sorted([f for f in files if f['name'].lower().endswith('.pdf')],
                  key=lambda f: get_week_number(f['name']))
    docxs = sorted([f for f in files if f['name'].lower().endswith('.docx')],
                   key=lambda f: get_week_number(f['name']))
    txts = sorted([f for f in files if f['name'].lower().endswith('.txt')],
                  key=lambda f: get_week_number(f['name']))
    return pdfs + docxs + txts


def download_file(service, file_id, filename, course_dir):
    course_dir.mkdir(parents=True, exist_ok=True)
    output_file = course_dir / filename

    if output_file.exists():
        print(f"   Already downloaded: {filename}")
        return str(output_file)

    try:
        request = service.files().get_media(fileId=file_id)
        print(f"   Downloading: {filename}")
        with open(output_file, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        print(f"   Downloaded: {output_file.stat().st_size / (1024*1024):.1f} MB")
        return str(output_file)
    except Exception as e:
        print(f"   Download failed: {e}")
        return None


def process_file(filepath, course_name, file_type="lectures", extract_images=False):
    """Run process_single_file.py with GEMINI_MODEL_OVERRIDE set to force single model."""
    is_long = filepath.lower().endswith(('.pdf', '.docx'))
    timeout_seconds = 300 if is_long else 120

    cmd = [sys.executable, 'process_single_file.py', filepath, '--course', course_name]
    if file_type == "cases":
        cmd.extend(['--type', 'case'])
    elif file_type == "transcripts":
        cmd.extend(['--type', 'transcript'])
    if not extract_images:
        cmd.append('--no-images')

    # Force single model - no fallback
    env = os.environ.copy()
    env['GEMINI_MODEL_OVERRIDE'] = MODEL

    try:
        result = subprocess.run(cmd, check=True, timeout=timeout_seconds, env=env)
        return True
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception) as e:
        print(f"   Failed: {e}")
        return False


def get_unprocessed(service, course_name, folder_id, file_type, tracker):
    """Get list of unprocessed files for a folder."""
    if not folder_id:
        return []
    files = list_files_in_folder(service, folder_id)
    sorted_files = sort_files(files)
    return [f for f in sorted_files
            if not is_file_processed(tracker, course_name, file_type, f['name'])]


def run_batch(service, course_name, course_config, extract_images, wait_minutes):
    """Process all unprocessed files. Returns True if all done, False if error occurred."""
    lectures_folder_id = course_config['lectures_folder_id']
    cases_folder_id = course_config.get('cases_folder_id')
    transcripts_folder_id = course_config.get('transcripts_folder_id')
    course_dir = LOCAL_DIR / course_name

    # Seed concepts first (no API calls)
    seed_cmd = [sys.executable, 'process_single_file.py', '--seed', '--course', course_name]
    try:
        subprocess.run(seed_cmd, check=True, timeout=30)
    except Exception:
        pass

    # Build the work queue: (folder_id, file_type, course_subdir)
    phases = [
        (lectures_folder_id, "lectures", course_dir),
        (cases_folder_id, "cases", course_dir / "cases"),
        (transcripts_folder_id, "transcripts", course_dir / "transcripts"),
    ]

    total_processed = 0
    total_remaining = 0

    for folder_id, file_type, subdir in phases:
        if not folder_id:
            continue

        tracker = load_tracker()
        unprocessed = get_unprocessed(service, course_name, folder_id, file_type, tracker)

        if not unprocessed:
            print(f"\n   [{file_type.upper()}] All done")
            continue

        print(f"\n{'='*60}")
        print(f"   [{file_type.upper()}] {len(unprocessed)} files to process")
        print(f"{'='*60}")

        for i, file_info in enumerate(unprocessed, 1):
            # Rate limit delay between files
            if total_processed > 0:
                delay = 20
                print(f"\n   Waiting {delay}s (rate limit)...")
                time.sleep(delay)

            print(f"\n   [{file_type.upper()} {i}/{len(unprocessed)}] {file_info['name']}")

            local_path = download_file(service, file_info['id'], file_info['name'], subdir)
            if not local_path:
                print(f"\n   Download failed. Will retry in {wait_minutes} minutes.")
                return False

            is_pdf = file_info['name'].lower().endswith('.pdf')
            use_images = extract_images and is_pdf

            success = process_file(local_path, course_name,
                                   file_type=file_type, extract_images=use_images)

            if success:
                tracker = load_tracker()
                mark_file_processed(tracker, course_name, file_type, file_info['name'])
                total_processed += 1
                print(f"   Processed so far: {total_processed}")
            else:
                # Count remaining
                remaining_this_phase = len(unprocessed) - i
                remaining_later = 0
                for fid, ft, _ in phases[phases.index((folder_id, file_type, subdir))+1:]:
                    if fid:
                        remaining_later += len(get_unprocessed(
                            service, course_name, fid, ft, load_tracker()))
                total_remaining = remaining_this_phase + remaining_later

                print(f"\n{'='*60}")
                print(f"   ERROR on: {file_info['name']}")
                print(f"   Model: {MODEL} (no fallback)")
                print(f"   Processed so far: {total_processed}")
                print(f"   Remaining: {total_remaining}")
                print(f"   Will retry in {wait_minutes} minutes...")
                print(f"{'='*60}")
                return False

    return True


def main():
    courses = load_courses()

    # Parse args
    args = sys.argv[1:]
    course_name = None
    extract_images = '--images' in args
    wait_minutes = DEFAULT_WAIT_MINUTES

    if '--course' in args:
        idx = args.index('--course')
        if idx + 1 < len(args):
            course_name = args[idx + 1]

    if '--wait' in args:
        idx = args.index('--wait')
        if idx + 1 < len(args):
            wait_minutes = int(args[idx + 1])

    if not course_name:
        print("Usage: python process_all_lite.py --course \"CourseName\"")
        print("       python process_all_lite.py --course \"CourseName\" --images")
        print("       python process_all_lite.py --course \"CourseName\" --wait 15")
        print(f"\nAvailable courses: {', '.join(courses.keys())}")
        sys.exit(1)

    if course_name not in courses:
        print(f"Course not found: {course_name}")
        print(f"Available: {', '.join(courses.keys())}")
        sys.exit(1)

    course_config = courses[course_name]

    print(f"{'='*60}")
    print(f"  RESILIENT BATCH PROCESSOR")
    print(f"  Course: {course_name}")
    print(f"  Model:  {MODEL} (no fallback)")
    print(f"  Retry:  {wait_minutes} min wait on error")
    print(f"  Images: {'ON' if extract_images else 'OFF'}")
    print(f"{'='*60}")

    service = setup_google_drive()
    if not service:
        sys.exit(1)

    attempt = 0
    while True:
        attempt += 1
        print(f"\n{'='*60}")
        print(f"  ATTEMPT #{attempt} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        all_done = run_batch(service, course_name, course_config, extract_images, wait_minutes)

        if all_done:
            print(f"\n{'='*60}")
            print(f"  ALL FILES PROCESSED")
            print(f"  Attempts: {attempt}")
            print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")

            # Rebuild search index
            try:
                from build_search_index import build_index
                total, updated = build_index(append_mode=False)
                print(f"  Search index rebuilt: {total} entries")
            except ImportError:
                print(f"  Search index skipped (fastembed not installed)")
            except Exception as e:
                print(f"  Search index failed (non-fatal): {e}")

            print(f"\n  Next steps:")
            print(f"  1. python wiki_viewer/app.py")
            print(f"  2. http://127.0.0.1:5000/")
            break
        else:
            resume_time = datetime.now()
            resume_hour = (resume_time.hour + (resume_time.minute + wait_minutes) // 60) % 24
            resume_min = (resume_time.minute + wait_minutes) % 60
            print(f"\n  Sleeping {wait_minutes} minutes...")
            print(f"  Will resume at ~{resume_hour:02d}:{resume_min:02d}")
            print(f"  (Press Ctrl+C to stop)\n")

            try:
                time.sleep(wait_minutes * 60)
            except KeyboardInterrupt:
                print(f"\n  Stopped by user after {attempt} attempt(s).")
                sys.exit(0)


if __name__ == "__main__":
    main()
