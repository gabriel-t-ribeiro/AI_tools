#!/usr/bin/env python3
"""
vault_tidy.py: keep file and folder names in the vault snake_case and English.

    python3 vault_tidy.py check            # list names that break the convention
    python3 vault_tidy.py plan             # write rename_map.csv (review/edit it)
    python3 vault_tidy.py apply            # rename + rewrite every reference, write undo log
    python3 vault_tidy.py undo             # reverse the last apply

Convention: lowercase letters, digits, "_", "-" and "."; no spaces or accents.
Week prefix first when there is one: w39_ppfm_lecture1.md.

Skipped on purpose (see SKIP_DIRS / KEEP_NAMES): books, Zotero storage, past semesters,
git repositories shared with groups, Python environments and agent skill files.

The CSV has columns old_path,new_path. Only rows whose new_path differs are applied.
Edit new_path by hand to choose English names; `plan` keeps your edits on later runs.
"""
import csv
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
# The vault lives in Google Drive; `vault` is a link to it next to this script.
VAULT = Path(os.environ.get("VAULT_TIDY_ROOT", (HERE / "vault").resolve()))
MAP_FILE = HERE / "rename_map.csv"
UNDO_FILE = HERE / "rename_undo.json"

SKIP_DIRS = {".git", ".venv", "venv", ".obsidian", ".trash", "__pycache__", "node_modules",
             ".idea", ".vscode", "past_uni_files", "zotero", "1_livros", "1_Livros", "1_books", ".agents"}
KEEP_NAMES = {"AGENTS.md", "README.md", "SKILL.md", "CLAUDE.md", "Makefile", ".gitignore",
              ".gitattributes", ".DS_Store", "main.tex", "main.pdf"}
# Text files whose contents may reference paths or note names.
TEXT_EXT = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".sh", ".csv", ".canvas"}
# Extra places outside the vault that reference vault paths.
EXTRA_ROOTS = [Path.home() / ".claude" / "skills", HERE.parent] + list(
    (Path.home() / ".claude" / "projects").glob("*0-uni-obsidian/memory"))
if os.environ.get("VAULT_TIDY_ROOT"):  # test runs on a copy never touch outside files
    EXTRA_ROOTS = []

GOOD = re.compile(r"^[a-z0-9_.\-]+$")

# Common Portuguese words in note names -> English. Used only for auto suggestions in `plan`.
WORDS = {
    "transcricao": "transcription", "nota_consolidada": "ai_note", "introducao": "introduction",
    "aula": "lecture", "materia": "topics", "revisao": "review", "trabalho": "work",
    "grupo": "group", "pratico": "practical", "praticos": "practical", "calculos": "calculations",
    "forcas": "forces", "simulacao": "simulation", "ferramentas": "tools", "corte": "cutting",
    "copia": "copy", "planeamento": "planning", "estado_da_arte": "state_of_the_art",
    "avaliacao": "evaluation", "caracterizacao": "characterisation", "guia": "guide",
    "estudo": "study", "estudos": "study", "procedimento": "procedure", "relatorio": "report",
    "questionario": "quiz", "caso": "case", "ficha": "worksheet", "caudais": "flow_rates",
    "comparacao": "comparison", "guiao": "guide", "protocolo": "protocol",
    "laboratorial": "lab", "exercicios": "exercises", "fim": "end", "segunda": "second",
    "parte": "part", "notas": "notes", "projeto": "project", "seminarios": "seminars",
}


def is_skipped_dir(path: Path) -> bool:
    return path.name in SKIP_DIRS or (path / ".git").exists() and path != VAULT


def walk_names():
    """Yield vault-relative paths (dirs and files) that break the convention."""
    for root, dirs, files in os.walk(VAULT):
        r = Path(root)
        dirs[:] = sorted(d for d in dirs if not is_skipped_dir(r / d) or (r / d / ".git").exists())
        # A git repo folder may itself be renamed, but we never descend into it.
        repo_dirs = [d for d in dirs if (r / d / ".git").exists()]
        for name in sorted(dirs + files):
            if name in KEEP_NAMES or name.startswith("."):
                continue
            if not GOOD.match(name):
                yield (r / name).relative_to(VAULT)
        dirs[:] = [d for d in dirs if d not in repo_dirs]


def slug(name: str) -> str:
    stem, ext = (name, "") if "." not in name or name.startswith(".") else name.rsplit(".", 1)
    s = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    s = re.sub(r"_+", "_", s)
    for pt, en in sorted(WORDS.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(rf"(?<![a-z]){pt}(?![a-z])", en, s)
    return f"{s}.{ext.lower()}" if ext else s


def load_map():
    if not MAP_FILE.exists():
        return {}
    with open(MAP_FILE, newline="", encoding="utf-8") as f:
        return {row["old_path"]: row["new_path"] for row in csv.DictReader(f)}


def cmd_check():
    bad = list(walk_names())
    for p in bad:
        print(p)
    print(f"\n{len(bad)} names break the convention.")
    return 1 if bad else 0


def cmd_plan():
    old = load_map()
    rows = []
    for rel in walk_names():
        key = str(rel)
        if key in old:  # keep hand edits
            rows.append((key, old[key]))
        else:
            rows.append((key, str(rel.parent / slug(rel.name)) if str(rel.parent) != "." else slug(rel.name)))
    with open(MAP_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["old_path", "new_path"])
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {MAP_FILE.relative_to(VAULT)}. Edit new_path, then run `apply`.")


def full_new_paths(m):
    """Each map row renames only the last segment. Resolve every row to its final full path."""
    seg = {o: Path(n).name for o, n in m.items() if o != n}
    def resolve(p: str) -> str:
        parts = Path(p).parts
        out = []
        for i in range(len(parts)):
            cur = str(Path(*parts[: i + 1]))
            out.append(seg.get(cur, parts[i]))
        return str(Path(*out))
    return {o: resolve(o) for o in seg}


def text_files():
    roots = [VAULT] + [r for r in EXTRA_ROOTS if r.exists()]
    for root in roots:
        for r, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {".git", ".venv", "venv", "__pycache__", "node_modules", ".obsidian", "past_uni_files", "zotero"}]
            for fn in files:
                p = Path(r) / fn
                if p.suffix.lower() in TEXT_EXT and p != MAP_FILE and p != UNDO_FILE:
                    yield p


def rewrite_references(pairs):
    """pairs: list of (old_rel_path, new_rel_path), files and folders, vault-relative."""
    subs = []  # (regex, replacement)
    # macOS stores names decomposed (NFD); notes usually hold composed text (NFC). Try both.
    variants = []
    for old, new in pairs:
        for form in ("NFC", "NFD"):
            v = unicodedata.normalize(form, old)
            if (v, new) not in variants:
                variants.append((v, new))
    for old, new in sorted(variants, key=lambda x: -len(x[0])):
        # Full and prefix path mentions, plain and URL-encoded (Markdown links).
        subs.append((re.compile(re.escape(old) + r"(?=[/\]\)|`'\"#\s,]|$)"), new))
        enc_o, enc_n = quote(old), quote(new)
        if enc_o != old:
            subs.append((re.compile(re.escape(enc_o)), enc_n))
        # Partial paths written relative to a course folder: ".../old_name" -> ".../new_name"
        if Path(old).name != Path(new).name:
            names = [(Path(old).name, Path(new).name)]
            if old.endswith(".md"):  # [[folder/note]] links omit the extension
                names.append((Path(old).stem, Path(new).stem))
            for o_n, n_n in names:
                subs.append((re.compile(r"(?<=/)" + re.escape(o_n) + r"(?=[/\]\)|`'\"#\s,]|$)"),
                             n_n.replace("\\", "\\\\")))
        # Obsidian wikilinks/embeds by basename: [[name]], [[name|x]], [[name#h]], ![[file.ext]]
        ob, nb = Path(old).name, Path(new).name
        for o, n in ((ob, nb), (Path(ob).stem, Path(nb).stem)) if ob.endswith(".md") else ((ob, nb),):
            subs.append((re.compile(r"(\[\[)" + re.escape(o) + r"(?=[\]|#^])"), r"\g<1>" + n.replace("\\", "\\\\")))
    changed = {}
    for p in text_files():
        try:
            txt = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new_txt = txt
        for rx, rep in subs:
            new_txt = rx.sub(rep, new_txt)
        if new_txt != txt:
            p.write_text(new_txt, encoding="utf-8")
            changed[str(p)] = txt  # original text, so `undo` is exact
    return changed


def safe_rename(src: Path, dst: Path):
    if dst.exists() and os.path.samefile(src, dst):  # case-only or Unicode-form-only change
        tmp = src.with_name(src.name + ".__tidy_tmp__")
        src.rename(tmp)
        tmp.rename(dst)
    elif dst.exists():
        raise FileExistsError(f"Target exists: {dst}")
    else:
        src.rename(dst)


def cmd_apply():
    m = {o: n for o, n in load_map().items() if o != n}
    if not m:
        print("Nothing to apply.")
        return
    finals = full_new_paths(m)
    # Rename deepest first so parent paths stay valid.
    done = []
    pairs = list(finals.items())
    try:
        for old in sorted(m, key=lambda p: -len(Path(p).parts)):
            src = VAULT / old
            if not src.exists():
                print(f"skip (missing): {old}")
                continue
            dst = src.with_name(Path(m[old]).name)
            safe_rename(src, dst)
            done.append((old, str(dst.relative_to(VAULT))))
    finally:
        # Written even if a rename fails, so `undo` can always restore what was done.
        UNDO_FILE.write_text(json.dumps({"renamed": done, "pairs": pairs}, indent=1, ensure_ascii=False), encoding="utf-8")
    originals = rewrite_references(pairs)
    log = json.loads(UNDO_FILE.read_text(encoding="utf-8"))
    log["originals"] = originals
    UNDO_FILE.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    n = len(originals)
    print(f"Renamed {len(done)} items, updated references in {n} text files. Undo log: {UNDO_FILE.relative_to(VAULT)}")


def cmd_undo():
    if not UNDO_FILE.exists():
        print("No undo log.")
        return
    log = json.loads(UNDO_FILE.read_text(encoding="utf-8"))
    for old, after in reversed(log["renamed"]):
        # `after` was computed with parents still old; parents are restored later (reversed order).
        src = VAULT / after
        if src.exists():
            safe_rename(src, src.with_name(Path(old).name))
    # Restore edited text files exactly. Paths were recorded with their new names, so map them back.
    back = {}
    for o, n in log["pairs"]:
        back[str(VAULT / n)] = str(VAULT / o)
    for path, text in log.get("originals", {}).items():
        target = path
        for n_abs in sorted(back, key=len, reverse=True):
            if path == n_abs or path.startswith(n_abs + os.sep):
                target = back[n_abs] + path[len(n_abs):]
                break
        Path(target).write_text(text, encoding="utf-8")
    UNDO_FILE.rename(UNDO_FILE.with_suffix(".undone.json"))
    print("Undo complete.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    sys.exit({"check": cmd_check, "plan": cmd_plan, "apply": cmd_apply, "undo": cmd_undo}[cmd]() or 0)
