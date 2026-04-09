# KnowledgeWiki - Processing Instructions

## Prerequisites

1. **Google Drive credentials** — `credentials/token.json` must exist (OAuth token for Drive access)
2. **Gemini API key** — `Gemini_Api_Key` must be set in your `.env` file
3. **courses.json** — Must have your course configured with a Google Drive folder ID
4. **Python dependencies** — Install with `pip install -r requirements.txt`

---

## Step 1: Configure Your Course

Add your course to `courses.json`:

```json
{
  "Leading People": {
    "lectures_folder_id": "YOUR_GOOGLE_DRIVE_FOLDER_ID",
    "cases_folder_id": null,
    "transcripts_folder_id": null
  }
}
```

- `lectures_folder_id` — The ID from the Google Drive folder URL: `https://drive.google.com/drive/folders/THIS_PART`
- `cases_folder_id` — Set to a folder ID if the course has a separate cases folder, otherwise `null`
- `transcripts_folder_id` — Set to a folder ID if the course has a separate transcripts folder, otherwise `null`

---

## Step 2: Process Files

### Using `download_and_process.py` (Downloads from Google Drive + Processes)

#### List all available courses

```bash
python download_and_process.py
```

#### List files in the Leading People course

```bash
python download_and_process.py --course "Leading People"
```

Shows all files in the Google Drive folder with `[processed]` status for files already done. Shows lectures, cases, and transcripts sections if configured.

#### Process a single file from Google Drive

```bash
python download_and_process.py --course "Leading People" "Week 1"
```

Partial name matching works — "Week 1" will match "Week 1 Lecture Notes.pdf".

**Tip:** Not sure of the filename? List files first to see what's available:

```bash
python download_and_process.py --course "Leading People"
```

Then copy the name (or part of it) and pass it as the argument. The file will be downloaded from Google Drive and processed automatically.

#### Process a single file with image extraction

The `--images` flag only works with `--all` mode. To extract images from a single PDF, first download it via Google Drive, then process the local file directly:

```bash
# Step 1: Download (this also processes, but without images)
python download_and_process.py --course "Leading People" "Week 1"

# Step 2: Reprocess the downloaded file with images
python process_single_file.py "Transcript_class_lecture/Leading People/Week 1 Slides.pdf" --course "Leading People"
```

`process_single_file.py` extracts images by default for PDFs. The downloaded file will be in `Transcript_class_lecture/Leading People/`.

#### Process all files

```bash
python download_and_process.py --course "Leading People" --all
```

- Processes **lectures first** (PDFs by week number, then TXTs by week number)
- Then processes **cases** if `cases_folder_id` is configured
- Then processes **transcripts** if `transcripts_folder_id` is configured
- Skips already-processed files (tracked in `processed_files.json`)
- 15-30 second delay between files for Gemini free tier rate limits

#### Process only case reviews

```bash
python download_and_process.py --course "Leading People" --cases-only
```

Requires `cases_folder_id` to be set in `courses.json`. Processes only case review files, skips lectures and transcripts.

#### Process only transcripts

```bash
python download_and_process.py --course "Leading People" --transcripts-only
```

Requires `transcripts_folder_id` to be set in `courses.json`. Processes only transcript files. Transcripts do dual duty:
1. **Extract concepts** — same as lectures, creates/merges `Concept-*.md` files
2. **Update case discussions** — fills in the "Class Discussion & Takeaways" section of matching `Case-*.md` files

#### Process all files with image extraction

```bash
python download_and_process.py --course "Leading People" --all --images
```

Extracts charts/images from PDFs and saves them to `MBAWiki/assets/charts/`. Images under 10KB are skipped (logos, icons). Only applies to PDFs — TXT files have no images.

---

### Using `process_single_file.py` (Process a Local File Directly)

Use this if the file is already downloaded to your machine.

#### Process a local text file

```bash
python process_single_file.py "Transcript_class_lecture/Leading People/week1.txt" --course "Leading People"
```

#### Process a local PDF

```bash
python process_single_file.py "Transcript_class_lecture/Leading People/slides.pdf" --course "Leading People"
```

#### Process a case study

```bash
python process_single_file.py "Transcript_class_lecture/Leading People/cases/case.pdf" --course "Leading People" --type case
```

Creates a `Case-*.md` file with specialized sections: Core Dilemma, Key Stakeholders & Incentives, Financial Context & Constraints, and a placeholder Class Discussion & Takeaways section.

#### Process a transcript

```bash
python process_single_file.py "Transcript_class_lecture/Leading People/transcripts/transcript.txt" --course "Leading People" --type transcript
```

Extracts concepts AND updates matching case study discussion sections in a single API call.

#### Process without image extraction

```bash
python process_single_file.py "Transcript_class_lecture/Leading People/slides.pdf" --course "Leading People" --no-images
```

#### Options

| Flag | Description |
|------|-------------|
| `--course "Name"` | Tags concepts with the course name. Merges track which courses a concept appears in. |
| `--type lecture` | Process as lecture (default). Extracts concepts. |
| `--type case` | Process as case study. Creates `Case-*.md` with specialized format. |
| `--type transcript` | Process as transcript. Extracts concepts AND updates case discussions. |
| `--no-images` | Skip image extraction from PDFs. Faster processing. |

---

## Step 3: View the Wiki

```bash
python wiki_viewer/app.py
```

Open http://127.0.0.1:5000/ in your browser. The homepage shows both concepts and case studies.

- Concepts are at `/concept/<slug>`
- Cases are at `/case/<slug>`

---

## Step 4: Image Tagging (Optional)

Images extracted from PDFs are saved but not automatically shown in the wiki. To tag them:

```bash
# 1. Initialize image_tags.json with all PNG filenames
python init_image_tags.py

# 2. See which images are untagged
python tag_images.py --list

# 3. Manually edit MBAWiki/assets/charts/image_tags.json to add captions
#    Example: "Slides_Page15_Plot0.png": ["leadership styles comparison"]

# 4. Map captions to concepts (1 Gemini API call)
python tag_images.py --map

# 5. Verify mappings
python tag_images.py --status
```

---

## Reprocessing Files

Processed files are tracked in `processed_files.json`. To reprocess:

- **Single file:** Delete its entry from `processed_files.json`
- **Entire course:** Delete the course key from `processed_files.json`
- **Clean rebuild:** Delete all `MBAWiki/Concept-*.md` and `MBAWiki/Case-*.md` files and clear `processed_files.json`, then run `--all`

---

## How Processing Works

### Lectures (`--type lecture`, default)
1. Downloads the file from Google Drive (or reads local file)
2. Extracts text from PDF or TXT
3. **1 Gemini API call** — Extracts 3-10 concepts with definitions, key points, formulas, examples
4. Creates new `MBAWiki/Concept-*.md` files for new concepts
5. If duplicates are found, **1 more Gemini API call** — Merges new content into existing concept pages
6. Max 2 API calls per file

### Cases (`--type case`)
1. Downloads the file from Google Drive (or reads local file)
2. Extracts text from PDF or TXT
3. **1 Gemini API call** — Extracts case name, core dilemma, stakeholders, financial context
4. Creates `MBAWiki/Case-*.md` with specialized sections
5. "Class Discussion & Takeaways" section is left as placeholder
6. Max 1 API call per file

### Transcripts (`--type transcript`)
1. Downloads the file from Google Drive (or reads local file)
2. Extracts text from PDF or TXT
3. **1 Gemini API call** — Extracts BOTH concepts AND case discussions in a single JSON response
4. Creates/merges concept files (same as lectures)
5. Updates matching `Case-*.md` files' "Class Discussion & Takeaways" sections (file I/O only)
6. Changes case tags from `#unresolved` to `#resolved` when discussion is added
7. Max 2 API calls per file (1 extraction + 1 merge if duplicates found)
