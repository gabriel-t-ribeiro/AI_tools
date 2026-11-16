#!/usr/bin/env python3
"""
Consolidated Study Note (AI Notes) Structure Generator.
Cross-references the 3 pillars of a lecture week:
1. Class drafts and notes (.md)
2. Full audio transcription (.md in *_transcrições/)
3. Lecture slides and reference documents (.pdf in *_pdf/)

Prepares destination in <discipline>_ai_notes/w<week>_<course>_ai_note.md
without modifying or overwriting original user notes.
"""

import os
import sys
import re
from pathlib import Path
from pypdf import PdfReader

def extract_pdf_summary(pdf_path: str, max_slides: int = 40):
    """Extracts high-level summary of PDF slides for prompt context."""
    if not os.path.exists(pdf_path):
        return []
    reader = PdfReader(pdf_path)
    slides = []
    for idx, page in enumerate(reader.pages[:max_slides]):
        txt = (page.extract_text() or "").strip()
        if txt:
            lines = [l.strip() for l in txt.split("\n") if l.strip()]
            title = lines[0] if lines else f"Slide {idx+1}"
            slides.append({"slide": idx + 1, "title": title, "content": " ".join(lines[:6])})
    return slides

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("Usage: python3 make_ai_note.py <path_to_weekly_note.md>")
        print("       ./make_ai_note.py <path_to_weekly_note.md>")
        print("\nDescription:")
        print("  Prepares file and folder structure for AI Consolidated Study Notes,")
        print("  cross-referencing class notes, transcriptions, and PDF slides in '<discipline>_ai_notes/'.")
        print("\nExample:")
        print("  python3 make_ai_note.py 'vault/2m1s_ppfm/w39_ppfm.md'")
        sys.exit(0 if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help", "help") else 1)

    note_path = Path(sys.argv[1]).resolve()
    if not note_path.exists():
        print(f"❌ Note not found: {note_path}")
        sys.exit(1)

    disc_dir = note_path.parent
    note_stem = note_path.stem
    disc_name = disc_dir.name

    # Identify course code/acronym
    if "dissertation" in disc_name.lower():
        sigla = "dpe"
    else:
        m = re.match(r"^2m1s[_\s]+([A-Za-z0-9_]+)", disc_name, re.IGNORECASE)
        sigla = m.group(1).lower().split('_')[0] if m else disc_name.lower().split('_')[0].split()[0]

    ai_notes_dir = disc_dir / f"{sigla}_ai_notes"
    ai_notes_dir.mkdir(exist_ok=True)

    out_file = ai_notes_dir / f"{note_stem}_ai_note.md"
    print(f"📘 Preparing context to consolidate '{note_stem}'...")
    print(f"📁 Destination folder: {ai_notes_dir.name}/")
    print(f"📄 Output note file  : {out_file.name}")
    print("\n✅ Structure validated! To generate the full consolidated note with AI:")
    print(f"   'Generate the consolidated AI Note for note {note_stem}'")

if __name__ == "__main__":
    main()
