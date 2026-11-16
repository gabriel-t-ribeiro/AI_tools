#!/usr/bin/env python3
"""
PDF Slide Text and Structure Extractor.
Extracts slide-by-slide text from lecture PDF slides for enriching
weekly study notes and Antigravity AI prompts.
"""

import os
import sys
from pypdf import PdfReader

def extract_pdf_slides(pdf_path: str):
    """Extracts text content per page/slide from a PDF file."""
    if not os.path.exists(pdf_path):
        return []
    reader = PdfReader(pdf_path)
    slides = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        slides.append({"page": i + 1, "text": text.strip()})
    return slides

def extract_transcript_text(transcript_path: str) -> str:
    """Reads Markdown transcription content."""
    if not os.path.exists(transcript_path):
        return ""
    with open(transcript_path, "r", encoding="utf-8") as f:
        return f.read()

def extract_draft_notes(draft_path: str) -> str:
    """Reads raw class draft notes."""
    if not os.path.exists(draft_path):
        return ""
    with open(draft_path, "r", encoding="utf-8") as f:
        return f.read()

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("Usage: python3 enrich_note.py <pdf_path> [transcription.md] [draft.md]")
        print("       ./enrich_note.py <pdf_path>")
        print("\nDescription:")
        print("  Extracts text and slide structure from PDF lecture slides")
        print("  for cross-referencing with audio transcriptions and class notes.")
        print("\nExample:")
        print("  python3 enrich_note.py 'vault/2m1s_ppfm/ppfm_pdf/w38 ppfm.pdf'")
        sys.exit(0 if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help", "help") else 1)

    pdf_path = sys.argv[1]
    slides = extract_pdf_slides(pdf_path)
    print(f"📄 Extracted {len(slides)} slides from '{os.path.basename(pdf_path)}'.")

if __name__ == "__main__":
    main()
