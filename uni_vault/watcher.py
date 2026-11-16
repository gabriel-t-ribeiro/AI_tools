#!/usr/bin/env python3
"""
Real-time Lecture Monitor for Obsidian Vault.
Monitors root directory for newly dropped audio, PDF, and image/print files,
moves them to their respective 2m1s or 2m discipline folders,
copies an Obsidian embed link to the clipboard,
and kicks off a background transcription via MLX-Whisper for audio files.
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vault_tidy import slug  # snake_case names for new files

AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.mp4', '.wav', '.ogg', '.aac', '.flac'}
PDF_EXTENSIONS = {'.pdf'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff'}

# Delay in seconds before moving/renaming prints to give Obsidian time to register
# the initial paste and update links automatically via app.json (alwaysUpdateLinks: true)
PRINT_SETTLE_DELAY = 1.5

# Mapping of course abbreviations/names to folder patterns and target names
DISCIPLINES = {
    'dpe': {'name': 'DPE', 'dir_pattern': 'dissertation'},
    'dissertation': {'name': 'DPE', 'dir_pattern': 'dissertation'},
    'dissertacao': {'name': 'DPE', 'dir_pattern': 'dissertation'},
    'dissertação': {'name': 'DPE', 'dir_pattern': 'dissertation'},
    'ppfm': {'name': 'PPFM', 'dir_pattern': 'ppfm'},
    'savi': {'name': 'SAVI', 'dir_pattern': 'savi'},
    'ma': {'name': 'MA', 'dir_pattern': 'ma'},
    'maquinagem': {'name': 'MA', 'dir_pattern': 'ma'},
    'adpe': {'name': 'ADPE', 'dir_pattern': 'adpe'},
    'sem': {'name': 'SEM', 'dir_pattern': 'sem'},
    'seminarios': {'name': 'SEM', 'dir_pattern': 'sem'},
    'seminários': {'name': 'SEM', 'dir_pattern': 'sem'},
}

def copy_to_clipboard(text: str):
    """Copies given text to macOS system clipboard using pbcopy."""
    try:
        process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        process.communicate(text.encode('utf-8'))
    except Exception:
        pass

def find_discipline_dir(vault_dir: str, pattern: str):
    """Finds the course directory matching the given pattern (e.g. 2m1s_*, 2m_*)."""
    for entry in os.listdir(vault_dir):
        full_path = os.path.join(vault_dir, entry)
        if os.path.isdir(full_path) and (entry.lower().startswith('2m1s') or entry.lower().startswith('2m_') or entry.lower().startswith('2m ')):
            if pattern in entry.lower():
                return full_path, entry
    return None, None

def get_next_audio_index(target_folder: str, week_str: str, disc_name: str) -> int:
    """Finds the next audio index (a1, a2, a3...) for the current week and discipline."""
    if not os.path.exists(target_folder):
        return 1

    max_idx = 0
    # Search files matching: w{week} {disc} a{num}.ext
    pattern = re.compile(rf'^{week_str}[\s_]+{disc_name}[\s_]+a(\d+)', re.IGNORECASE)

    for f in os.listdir(target_folder):
        m = pattern.search(f)
        if m:
            idx = int(m.group(1))
            if idx > max_idx:
                max_idx = idx

    return max_idx + 1

def resolve_target_note_stem(vault_dir: str, disc_dir: str, week_str: str, disc_slug: str) -> str:
    """
    Identifies the note into which the print is being pasted:
    1. Checks active editor tab in Obsidian's workspace.json if it belongs to this course.
    2. Searches for current week's note (e.g. w41_... or w41 ...) in the course root.
    3. Falls back to the most recently modified note in the course folder, or w<week>_<disc>.
    """
    # 1. Active tab in workspace.json
    ws_path = os.path.join(vault_dir, '.obsidian', 'workspace.json')
    if os.path.exists(ws_path):
        try:
            with open(ws_path, 'r', encoding='utf-8') as f:
                d = json.load(f)

            def walk_for_id(obj, target):
                if isinstance(obj, dict):
                    if obj.get('id') == target:
                        return obj
                    for v in obj.values():
                        res = walk_for_id(v, target)
                        if res:
                            return res
                elif isinstance(obj, list):
                    for item in obj:
                        res = walk_for_id(item, target)
                        if res:
                            return res
                return None

            active_id = d.get('active')
            if active_id:
                leaf = walk_for_id(d, active_id)
                if leaf and leaf.get('type') == 'markdown':
                    rel_file = leaf.get('state', {}).get('file', '')
                    if rel_file and rel_file.endswith('.md'):
                        full_f = os.path.normpath(os.path.join(vault_dir, rel_file))
                        norm_disc = os.path.normpath(disc_dir)
                        if os.path.exists(full_f) and full_f.startswith(norm_disc):
                            return os.path.splitext(os.path.basename(full_f))[0]
        except Exception:
            pass

    # 2. Look for weekly note in course directory root
    candidates = []
    if os.path.exists(disc_dir):
        for f in os.listdir(disc_dir):
            if f.lower().endswith('.md') and not f.startswith('.'):
                candidates.append(os.path.join(disc_dir, f))

    week_matches = [c for c in candidates if os.path.basename(c).lower().startswith(week_str.lower())]
    if week_matches:
        # Prioritize root week note, picking the shortest or most recently modified
        week_matches.sort(key=lambda p: (len(os.path.basename(p)), -os.path.getmtime(p)))
        return os.path.splitext(os.path.basename(week_matches[0]))[0]

    # 3. Most recently modified note in the course root
    if candidates:
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return os.path.splitext(os.path.basename(candidates[0]))[0]

    # Fallback to week and discipline
    return f"{week_str}_{disc_slug}"

def get_next_print_index(target_folder: str, prefix_stem: str) -> int:
    """Finds the next print/figure index (1, 2, 3...) for <prefix_stem>_p<index>.ext."""
    if not os.path.exists(target_folder):
        return 1

    max_idx = 0
    # Matches patterns like <prefix_stem>_p1.png or <prefix_stem>_p2.png
    pattern = re.compile(rf'^{re.escape(prefix_stem)}_p(\d+)\.[^.]+$', re.IGNORECASE)

    for f in os.listdir(target_folder):
        m = pattern.search(f)
        if m:
            idx = int(m.group(1))
            if idx > max_idx:
                max_idx = idx

    return max_idx + 1

def is_file_ready(filepath: str, min_delay: float = 0.5) -> bool:
    """Ensures file writing has finished by checking size stability across a time window."""
    try:
        initial_size = os.path.getsize(filepath)
        time.sleep(min_delay)
        return os.path.getsize(filepath) == initial_size
    except OSError:
        return False

def update_note_image_links(disc_dir: str, old_filename: str, new_filename: str):
    """
    Safeguard: If Obsidian didn't automatically update the link in the note
    (e.g. if the note was saved before or during rename), replace any reference
    to ![[old_filename]] with ![[new_filename]].
    """
    old_embed = f"![[{old_filename}]]"
    new_embed = f"![[{new_filename}]]"

    # Also match markdown-style links or bare filenames if needed
    for root, _, files in os.walk(disc_dir):
        for f in files:
            if f.endswith('.md'):
                f_path = os.path.join(root, f)
                try:
                    with open(f_path, 'r', encoding='utf-8') as fh:
                        content = fh.read()
                    if old_embed in content or old_filename in content:
                        new_content = content.replace(old_embed, new_embed)
                        # Also replace any non-embed wikilink [[old_filename]]
                        new_content = new_content.replace(f"[[{old_filename}]]", f"[[{new_filename}]]")
                        with open(f_path, 'w', encoding='utf-8') as fh:
                            fh.write(new_content)
                        print(f"   🔗 Link updated in note: {os.path.basename(f_path)}")
                except Exception:
                    pass

def watch(vault_dir: str, disc_key: str):
    """Monitors the vault root directory for new media files."""
    script_dir = os.path.join(vault_dir, '0_util') if os.path.exists(os.path.join(vault_dir, '0_util')) else os.path.join(vault_dir, 'util')
    disc_info = DISCIPLINES[disc_key]
    disc_name = disc_info['name']
    disc_dir, disc_folder_name = find_discipline_dir(vault_dir, disc_info['dir_pattern'])

    if not disc_dir:
        print(f"❌ Error: Folder corresponding to '{disc_name}' was not found in the vault root.")
        sys.exit(1)

    disc_slug = disc_name.lower()

    # Subfolder for audio files (e.g. dpe_mp, ppfm_mp, ma_mp, savi_mp...)
    existing_audio_folders = [d for d in os.listdir(disc_dir) if os.path.isdir(os.path.join(disc_dir, d)) and d.lower().endswith('_mp')]
    audio_dir = os.path.join(disc_dir, existing_audio_folders[0] if existing_audio_folders else f"{disc_slug}_mp")

    # Subfolder for PDF files
    pdf_dir = os.path.join(disc_dir, f"{disc_slug}_pdfs")

    # Subfolder for screenshots / prints / images (e.g. dpe_prints, ppfm_prints...)
    existing_print_folders = [
        d for d in os.listdir(disc_dir)
        if os.path.isdir(os.path.join(disc_dir, d)) and (d.lower().endswith('_prints') or d.lower().endswith('_images'))
    ]
    prints_dir = os.path.join(disc_dir, existing_print_folders[0] if existing_print_folders else f"{disc_slug}_prints")

    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(prints_dir, exist_ok=True)

    week_num = datetime.datetime.now().isocalendar()[1]
    week_str = f"w{week_num}"

    print("=" * 60)
    print(f"🎧 WATCHER ACTIVE — Course: {disc_name} ({week_str})")
    print(f"📁 Course Folder  : {disc_folder_name}")
    print(f"🎵 Audio Folder   : {os.path.relpath(audio_dir, vault_dir)}")
    print(f"📄 PDF Folder     : {os.path.relpath(pdf_dir, vault_dir)}")
    print(f"🖼️ Prints Folder  : {os.path.relpath(prints_dir, vault_dir)}")
    print("=" * 60)
    print("👀 Listening for new files in Obsidian vault root...")
    print("👉 Press Ctrl + C to stop when class finishes.\n")

    initial_files = set(os.listdir(vault_dir))

    try:
        while True:
            current_files = set(os.listdir(vault_dir))
            new_files = current_files - initial_files

            for filename in sorted(new_files):
                filepath = os.path.join(vault_dir, filename)

                if not os.path.isfile(filepath) or filename.startswith('.'):
                    continue

                ext = os.path.splitext(filename)[1].lower()

                if ext in AUDIO_EXTENSIONS:
                    if not is_file_ready(filepath):
                        continue

                    idx = get_next_audio_index(audio_dir, week_str, disc_name)
                    new_filename = f"{week_str}_{disc_name.lower()}_a{idx}{ext.lower()}"
                    dest_path = os.path.join(audio_dir, new_filename)

                    shutil.move(filepath, dest_path)
                    initial_files.add(filename)

                    link = f"![[{new_filename}]]"
                    copy_to_clipboard(link)

                    print("✅ [AUDIO DETECTED]")
                    print(f"   Source     : {filename}")
                    print(f"   Destination: {os.path.relpath(dest_path, vault_dir)}")
                    print(f"   📋 Copied to clipboard: {link}  (press Cmd+V in your note)\n")

                    # Launch background transcription without blocking watcher
                    transcribe_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transcribe.py")
                    subprocess.Popen([sys.executable, transcribe_script, dest_path])
                    print(f"   ⚡ Whisper transcription started in background for '{new_filename}'!\n")

                elif ext in PDF_EXTENSIONS:
                    if not is_file_ready(filepath):
                        continue

                    if not re.match(r'^w\d+', filename, re.IGNORECASE):
                        new_filename = f"{week_str}_{disc_name.lower()}_{slug(filename)}"
                    else:
                        new_filename = slug(filename)

                    dest_path = os.path.join(pdf_dir, new_filename)
                    shutil.move(filepath, dest_path)
                    initial_files.add(filename)

                    link = f"[[{new_filename}]]"
                    copy_to_clipboard(link)

                    print("📄 [PDF DETECTED]")
                    print(f"   Destination: {os.path.relpath(dest_path, vault_dir)}")
                    print(f"   📋 Copied to clipboard: {link}  (press Cmd+V in your note)\n")

                elif ext in IMAGE_EXTENSIONS:
                    # 1. Ensure file is completely written by Obsidian
                    if not is_file_ready(filepath, min_delay=0.6):
                        continue

                    # 2. Settle delay: Give Obsidian a moment to paste and register the link
                    time.sleep(PRINT_SETTLE_DELAY)

                    # Check file still exists in case it was modified/moved
                    if not os.path.exists(filepath):
                        continue

                    # 3. Determine target filename
                    if re.search(r'_p\d+$', os.path.splitext(filename)[0], re.IGNORECASE):
                        new_filename = filename
                    else:
                        note_stem = resolve_target_note_stem(vault_dir, disc_dir, week_str, disc_slug)
                        p_idx = get_next_print_index(prints_dir, note_stem)
                        new_filename = f"{note_stem}_p{p_idx}{ext}"

                    dest_path = os.path.join(prints_dir, new_filename)
                    shutil.move(filepath, dest_path)
                    initial_files.add(filename)

                    link = f"![[{new_filename}]]"
                    copy_to_clipboard(link)

                    print("🖼️ [PRINT / IMAGE DETECTED]")
                    print(f"   Source     : {filename}")
                    print(f"   Destination: {os.path.relpath(dest_path, vault_dir)}")
                    print(f"   📋 Copied to clipboard: {link}  (press Cmd+V in your note)")

                    # 4. Safeguard: update link in note if Obsidian didn't catch the rename
                    update_note_image_links(disc_dir, filename, new_filename)
                    print()

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n👋 Watcher stopped. Good study session!")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    vault_root = os.path.realpath(os.path.join(script_dir, "vault"))  # link to the Obsidian vault in Google Drive

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("Usage: python3 watcher.py <discipline>")
        print("       ./watcher.py <discipline>")
        print("\nDescription:")
        print("  Real-time lecture monitor. Detects new audio, PDF, and image/print files")
        print("  pasted in the vault root, moves them to the designated discipline folders")
        print("  (<discipline>_mp/, <discipline>_pdfs/, <discipline>_prints/).")
        print("  Screenshots/prints are automatically named after the note they were pasted into")
        print("  with sequential identifiers: <note_name>_p1.<ext>, <note_name>_p2.<ext>, etc.")
        print("  Waits a configurable settle time before renaming so Obsidian registers the link,")
        print("  and verifies/updates the markdown link automatically.")
        print("\nSupported disciplines: dpe, dissertation, ppfm, savi, ma, adpe, sem")
        print("\nExample: python3 watcher.py dpe")
        sys.exit(0 if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help", "help") else 1)

    disc_arg = sys.argv[1].lower().strip()
    if disc_arg not in DISCIPLINES:
        print(f"❌ Discipline '{disc_arg}' not recognized.")
        print(f"Available options: {', '.join(sorted(set(DISCIPLINES.keys())))}")
        sys.exit(1)

    watch(vault_root, disc_arg)

if __name__ == '__main__':
    main()
