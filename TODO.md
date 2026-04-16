# TODO

## Web App
- [ ] Add `start_wiki.bat` to Windows Startup folder so wiki runs automatically on login (use `pythonw` for no console window)

## Periodic Linting (Karpathy alignment: 0/10 -> 8/10)
- [x] Create `lint_wiki.py` with the following checks:
  - [x] Orphan pages — concepts with 0 inbound wikilinks
  - [x] Broken wikilinks — links to non-existent pages
  - [x] Missing concepts — terms mentioned in text but lacking their own page
  - [x] Stale content — pages not updated after related transcripts were processed
- [x] Add alias resolution to wikilink processor (abbreviations, slugs, prefix matching)
- [x] Reports saved to `Maintenance/` folder as markdown
- [ ] Fix remaining 17 broken wikilinks (truly missing pages — will resolve as more courses are processed)
- [ ] Reduce orphan count (158 concepts with 0 inbound links)

## Query-to-Wiki Filing (Karpathy alignment: 0/10)
- [ ] Add mechanism to persist query answers back into the wiki as new concept pages
- [ ] Option A: CLI command — `python file_answer.py "Topic Title" answer.md`
- [ ] Option B: "Save to Wiki" button in the web viewer

## Contradiction Tracking (Karpathy alignment: 3/10)
- [ ] Aggregate contradictions into a reviewable format (e.g., `contradictions.md`)
- [ ] Surface contradictions during merge: "Source A says X, Source B says Y"
- [ ] Track across the wiki, not just per-page in the schema template
