#!/usr/bin/env python3
"""
Batch Media, PDF, Image and Note Organizer for Obsidian Vault.
Scans the vault root and course root folders for loose notes, audio, PDF, and image files,
identifies target course via filename keywords, and routes them to their
respective locations (notes to course root; media to <course>_mp/, <course>_pdfs/, <course>_prints/).
"""

import os
import re
import shutil
import sys

AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.mp4', '.wav', '.ogg', '.aac', '.flac'}
PDF_EXTENSIONS = {'.pdf'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff'}
NOTE_EXTENSIONS = {'.md'}

def get_target_discipline_dir(base_dir: str, filename: str):
    """Identifies the target course directory matching keywords in the filename."""
    name_clean = filename.replace('_', ' ').replace('-', ' ').lower()

    discipline_key = None
    if re.search(r'\b(dissertation|dissertação|dissertacao|dpe)\b', name_clean):
        discipline_key = 'dpe'
    elif re.search(r'\badpe\b', name_clean):
        discipline_key = 'adpe'
    elif re.search(r'\bppfm\b', name_clean):
        discipline_key = 'ppfm'
    elif re.search(r'\bsavi\b', name_clean):
        discipline_key = 'savi'
    elif re.search(r'\b(sem|semin[aá]rios?)\b', name_clean):
        discipline_key = 'sem'
    elif re.search(r'\b(ma|maquinagem)\b', name_clean):
        discipline_key = 'ma'

    if not discipline_key:
        return None

    # Search corresponding folder (e.g. 2m_dissertation, 2m1s_*)
    for entry in os.listdir(base_dir):
        full_p = os.path.join(base_dir, entry)
        if os.path.isdir(full_p) and (entry.lower().startswith("2m1s") or entry.lower().startswith("2m_") or entry.lower().startswith("2m ")):
            entry_lower = entry.lower()
            if discipline_key == 'dpe' and ('dissertation' in entry_lower or entry_lower.endswith('_dpe')):
                return full_p
            elif discipline_key == 'adpe' and ('adpe' in entry_lower):
                return full_p
            elif discipline_key == 'ppfm' and 'ppfm' in entry_lower:
                return full_p
            elif discipline_key == 'savi' and 'savi' in entry_lower:
                return full_p
            elif discipline_key == 'sem' and ('sem' in entry_lower or 'semin' in entry_lower):
                return full_p
            elif discipline_key == 'ma' and ('ma' in entry_lower or 'maquinagem' in entry_lower):
                return full_p

    return None

def extract_course_prefix(dir_name: str) -> str:
    """Extracts short prefix identifier (e.g. adpe, dpe, ppfm, ma, savi, sem) from folder name."""
    clean = dir_name.lower()
    if 'adpe' in clean:
        return 'adpe'
    if 'dissertation' in clean or 'dpe' in clean:
        return 'dpe'
    clean = re.sub(r"^2m1s[_\s]*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^2m[_\s]*", "", clean, flags=re.IGNORECASE)
    return clean.strip().split('_')[0].split()[0]

def get_subfolder_for_file(disc_dir: str, disc_key: str, ext: str) -> str:
    """Returns the matching subfolder name for the file extension."""
    if ext in AUDIO_EXTENSIONS:
        existing = [d for d in os.listdir(disc_dir) if os.path.isdir(os.path.join(disc_dir, d)) and d.lower().endswith('_mp')]
        return existing[0] if existing else f"{disc_key}_mp"
    elif ext in PDF_EXTENSIONS:
        existing = [d for d in os.listdir(disc_dir) if os.path.isdir(os.path.join(disc_dir, d)) and 'pdf' in d.lower()]
        return existing[0] if existing else f"{disc_key}_pdfs"
    elif ext in IMAGE_EXTENSIONS:
        existing = [
            d for d in os.listdir(disc_dir)
            if os.path.isdir(os.path.join(disc_dir, d)) and (d.lower().endswith('_prints') or d.lower().endswith('_images'))
        ]
        return existing[0] if existing else f"{disc_key}_prints"
    return disc_key

def organize(vault_dir: str, dry_run: bool = False):
    """Organizes loose notes, audio, PDF, and image files from the vault root into course folders."""
    moved_count = 0
    media_supported = AUDIO_EXTENSIONS | PDF_EXTENSIONS | IMAGE_EXTENSIONS
    all_supported = media_supported | NOTE_EXTENSIONS

    # 1. Process files in vault root
    for item in sorted(os.listdir(vault_dir)):
        item_path = os.path.join(vault_dir, item)
        if not os.path.isfile(item_path):
            continue

        ext = os.path.splitext(item)[1].lower()
        if ext not in all_supported:
            continue

        disc_dir = get_target_discipline_dir(vault_dir, item)
        if not disc_dir:
            continue

        if ext in NOTE_EXTENSIONS:
            # Markdown notes sit directly in the course root directory
            target_dir = disc_dir
        else:
            disc_key = extract_course_prefix(os.path.basename(disc_dir))
            subfolder_name = get_subfolder_for_file(disc_dir, disc_key, ext)
            target_dir = os.path.join(disc_dir, subfolder_name)

        target_path = os.path.join(target_dir, item)

        action_tag = "DRY-RUN" if dry_run else "MOVING"
        print(f"[{action_tag}] {item} -> {os.path.relpath(target_path, vault_dir)}")

        if not dry_run:
            os.makedirs(target_dir, exist_ok=True)
            shutil.move(item_path, target_path)
            moved_count += 1

    # 2. Check loose media sitting directly inside course folders
    for entry in os.listdir(vault_dir):
        disc_dir = os.path.join(vault_dir, entry)
        if os.path.isdir(disc_dir) and (entry.lower().startswith("2m1s") or entry.lower().startswith("2m_")):
            sigla = extract_course_prefix(entry)
            for f in sorted(os.listdir(disc_dir)):
                f_path = os.path.join(disc_dir, f)
                if os.path.isfile(f_path):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in media_supported:
                        subfolder_name = get_subfolder_for_file(disc_dir, sigla, ext)
                        target_dir = os.path.join(disc_dir, subfolder_name)
                        target_path = os.path.join(target_dir, f)

                        action_tag = "DRY-RUN" if dry_run else "MOVING"
                        print(f"[{action_tag}] {os.path.relpath(f_path, vault_dir)} -> {os.path.relpath(target_path, vault_dir)}")
                        if not dry_run:
                            os.makedirs(target_dir, exist_ok=True)
                            shutil.move(f_path, target_path)
                            moved_count += 1

    if dry_run:
        print("\nDry-run completed. No files were moved.")
    else:
        print(f"\nCompleted! Organized {moved_count} file(s).")

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    vault_root = os.path.realpath(os.path.join(script_dir, "vault"))  # link to the Obsidian vault in Google Drive

    if "-h" in sys.argv or "--help" in sys.argv or "help" in sys.argv:
        print("Usage: python3 organise_media.py [--dry-run | -n]")
        print("       ./organise_media.py [--dry-run]")
        print("\nDescription:")
        print("  Organizes loose notes (.md), media files, PDFs, and screenshots/prints in vault root.")
        print("  Moves notes to the course root folder, audio files to '<discipline>_mp/',")
        print("  PDFs to '<discipline>_pdfs/', and prints/images to '<discipline>_prints/'")
        print("  by auto-detecting the subject from file names (including DPE/dissertation).")
        print("\nOptions:")
        print("  --dry-run, -n    Simulate organization without moving any files.")
        print("  -h, --help       Show this help message.")
        sys.exit(0)

    is_dry = '--dry-run' in sys.argv or '-n' in sys.argv
    organize(vault_root, dry_run=is_dry)
