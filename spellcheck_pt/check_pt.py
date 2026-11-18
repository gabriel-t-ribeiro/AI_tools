#!/usr/bin/env python3
"""
Spellcheck & Style Guard for European Portuguese (pt-PT).

Features:
1. Fast sub-second local checking (0 API credits / 0 AI tokens).
2. Conjugation & morphology validation via European Portuguese rules (1.5M+ inflections).
3. Brazilian Portuguese (pt-BR) detection & replacement suggestions (e.g., usuário -> utilizador).
4. AI-ism & False Friend detection (e.g., escopo -> âmbito, acurácia -> exatidão, performar -> ter desempenho).
5. Support for PDF files, LaTeX (.tex) sources, Markdown (.md), and plain text.
6. Custom project whitelist (whitelist.txt) for domain jargon, author names, and code variables.
"""

import argparse
import json
import os
import re
import sys
import time

try:
    import pypdf
except ImportError:
    pypdf = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_DIR = os.path.join(BASE_DIR, "rules")
WHITELIST_FILE = os.path.join(BASE_DIR, "whitelist.txt")
AI_ISMS_FILE = os.path.join(RULES_DIR, "ai_isms.json")
PT_BR_FILE = os.path.join(RULES_DIR, "pt_br_lexicon.json")

# Import vocabulary builder
from vocab_builder import build_vocabulary


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_whitelist(path):
    whitelist = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    whitelist.add(line.lower())
    return whitelist


def extract_text_from_pdf(pdf_path):
    if pypdf is None:
        raise RuntimeError("pypdf is required to inspect PDF documents. Install via: pip install pypdf")
    reader = pypdf.PdfReader(pdf_path)
    pages_text = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages_text.append((idx + 1, text))
    return pages_text


def strip_latex_markup(text):
    """Remove LaTeX comments, commands, environments, and math blocks while preserving text content."""
    # Remove comments
    text = re.sub(r"(?<!\\)%.*$", "", text, flags=re.MULTILINE)
    # Remove math $$...$$ and $...$
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.DOTALL)
    text = re.sub(r"\$.*?\$", " ", text)
    # Remove \begin{env} and \end{env}
    text = re.sub(r"\\(?:begin|end)\{[^}]*\}", " ", text)
    # Remove citation/reference/label commands
    text = re.sub(r"\\(?:cite|citep|citet|ref|label|autoref|pageref|eqref|url|href|input|include)\*?(?:\[[^\]]*\])?\{[^}]*\}", " ", text)
    # Replace formatting commands like \textbf{word} with word
    text = re.sub(r"\\(?:textbf|textit|emph|underline|section|subsection|subsubsection|caption|item|author|title)\*?\{([^}]*)\}", r" \1 ", text)
    # Remove remaining backslash commands with optional arguments
    text = re.sub(r"\\[a-zA-Z]+(\[[^\]]*\])?", " ", text)
    return text


def extract_text_from_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    
    if ext in (".tex", ".latex"):
        # Process lines keeping line numbers
        processed_lines = []
        for line_idx, line in enumerate(lines):
            clean_line = strip_latex_markup(line)
            processed_lines.append((line_idx + 1, clean_line))
        return processed_lines
    else:
        return [(idx + 1, line) for idx, line in enumerate(lines)]


WORD_REGEX = re.compile(r"\b[a-zA-ZçáéíóúâêôãõàüÁÉÍÓÚÂÊÔÃÕÀÜ-]+(?:\b|(?=[-]))")

# Common function words, auxiliaries, and non-verb -ar/-er/-ir nouns/adjectives
# excluded from Option A same-sentence verb-repetition checks.
REPETITION_IGNORE_WORDS = {
    "sobre", "entre", "através", "para", "como", "mais", "menos", "quando",
    "onde", "porque", "mesmo", "mesma", "mesmos", "mesmas", "muito", "muita",
    "muitos", "muitas", "outro", "outra", "outros", "outras", "tanto", "tanta",
    "tantos", "tantas", "assim", "ainda", "também", "apenas", "durante",
    "enquanto", "segundo", "conforme", "sendo", "estar", "estava", "estão",
    "foram", "serão", "seria", "tendo", "tinha", "havia", "houve", "poder",
    "podem", "podendo", "fazer", "fazem", "fazendo", "dever", "devem",
    "lugar", "melhor", "maior", "menor", "superior", "inferior", "anterior",
    "posterior", "exterior", "interior", "particular", "similar", "regular",
    "linear", "circular", "angular", "modular", "familiar", "popular",
    "singular", "tabular", "retangular", "triangular", "perpendicular",
}

VERB_SUFFIXES = (
    "aríamos", "eríamos", "iríamos", "ávamos", "íamos",
    "ariam", "eriam", "iriam", "armos", "ermos", "irmos",
    "arão", "erão", "irão", "ando", "endo", "indo",
    "aram", "eram", "iram", "avam", "aria", "eria", "iria",
    "arei", "erei", "irei", "asse", "esse", "isse",
    "aste", "este", "iste", "amos", "emos", "imos",
    "ará", "erá", "irá", "ara", "era", "ira", "ava",
    "ou", "eu", "iu", "ar", "er", "ir", "am", "em",
)

DEVERBAL_SUFFIXES = (
    "ações", "ições", "ação", "ição", "amento", "imento",
    "ados", "adas", "idos", "idas", "ado", "ada", "ido", "ida",
    "ante", "ente", "inte", "ável", "ível",
)


def _verb_stem_pt(word_lower):
    """Return (stem, is_verb_form) for Option A same-sentence repetition checks."""
    if len(word_lower) < 5 or "-" in word_lower or word_lower in REPETITION_IGNORE_WORDS:
        return None, False

    # Engineering/abstract nouns ending in -agem / -igem (e.g., maquinagem, fresagem, estampagem)
    if word_lower.endswith(("agem", "igem")):
        return word_lower, False

    for suffix in VERB_SUFFIXES:
        if word_lower.endswith(suffix):
            stem = word_lower[: -len(suffix)]
            if len(stem) >= 4:
                return stem, True

    for suffix in DEVERBAL_SUFFIXES:
        if word_lower.endswith(suffix):
            stem = word_lower[: -len(suffix)]
            if len(stem) >= 4:
                return stem, False

    return word_lower, False


def find_sentence_verb_repetitions(text):
    """Find repeated verb/deverbal stems within the same sentence (Option A)."""
    repeats = []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sent in sentences:
        if not sent.strip():
            continue
        tokens = re.findall(r"\b[a-zA-ZçáéíóúâêôãõàüÁÉÍÓÚÂÊÔÃÕÀÜ-]+\b", sent)
        by_stem = {}
        for tok in tokens:
            if is_number_or_code(tok):
                continue
            w_lower = tok.lower()
            stem, is_verb = _verb_stem_pt(w_lower)
            if not stem:
                continue
            by_stem.setdefault(stem, []).append((tok, is_verb))

        for stem, occs in by_stem.items():
            if len(occs) >= 2 and any(is_verb for _, is_verb in occs):
                words = [w for w, _ in occs]
                repeats.append((stem, words))
    return repeats


def is_number_or_code(token):
    # Contains digits, underscores, slashes, or symbols
    if any(c.isdigit() or c in r"_/\<>{}=+*@#$%^&~`|" for c in token):
        return True
    # Single character (except standard Portuguese single-letter words: a, e, o, à, é)
    if len(token) == 1 and token.lower() not in ("a", "e", "o", "à", "é"):
        return True
    return False


def check_portuguese(file_path, verbose=False):
    t0 = time.time()
    vocab = build_vocabulary(force_rebuild=False)
    ai_isms = load_json(AI_ISMS_FILE).get("terms", {})
    pt_br_data = load_json(PT_BR_FILE)
    pt_br_words = pt_br_data.get("word_replacements", {})
    pt_br_consonants = pt_br_data.get("consonant_rules", {})
    whitelist = load_whitelist(WHITELIST_FILE)

    pages_or_lines = extract_text_from_file(file_path)
    is_pdf = file_path.lower().endswith(".pdf")
    loc_label = "Page" if is_pdf else "Line"

    findings = []
    seen_keys = set()  # (word_lower, loc, category)

    for loc, text in pages_or_lines:
        if not text.strip():
            continue

        # 0. Same-sentence verb stem repetition check (Option A)
        for stem, rep_words in find_sentence_verb_repetitions(text):
            key = (stem, loc, "VERB_REPEAT")
            if key not in seen_keys:
                seen_keys.add(key)
                joined = " ... ".join(f"'{w}'" for w in rep_words)
                findings.append({
                    "loc": loc,
                    "type": "Style / Repetition",
                    "severity": "MEDIUM",
                    "word": " ... ".join(rep_words),
                    "suggestion": "Variar o verbo ou reestruturar a frase",
                    "explanation": f"Repetição do mesmo radical verbal na mesma frase ({joined}).",
                })

        # 1. Multi-word phrases in pt-BR or AI-isms (e.g. "carteira de motorista", "faixa de pedestres")
        text_lower = text.lower()
        for phrase, info in pt_br_words.items():
            if " " in phrase and phrase in text_lower:
                key = (phrase, loc, "PT-BR Phrase")
                if key not in seen_keys:
                    seen_keys.add(key)
                    findings.append({
                        "loc": loc,
                        "type": "PT-BR Lexicon",
                        "severity": "HIGH",
                        "word": phrase,
                        "suggestion": info.get("suggestion"),
                        "explanation": info.get("explanation"),
                    })

        # 2. Tokenize words
        raw_words = re.findall(r"\b[a-zA-ZçáéíóúâêôãõàüÁÉÍÓÚÂÊÔÃÕÀÜ-]+(?:\b|(?=[.,;!?\s]))", text)
        for w in raw_words:
            w_clean = w.strip("-").strip()
            if not w_clean or is_number_or_code(w_clean):
                continue

            w_lower = w_clean.lower()

            # Skip whitelisted words
            if w_lower in whitelist:
                continue

            # Check 1: AI-ism / False Friend (Highest Priority check)
            if w_lower in ai_isms:
                key = (w_lower, loc, "AI-ISM")
                if key not in seen_keys:
                    seen_keys.add(key)
                    findings.append({
                        "loc": loc,
                        "type": "AI-ISM / Calque",
                        "severity": "CRITICAL" if w_lower in ("escopo", "escopos", "acurácia") else "MEDIUM",
                        "word": w_clean,
                        "suggestion": ai_isms[w_lower].get("suggestion"),
                        "explanation": ai_isms[w_lower].get("explanation"),
                    })
                continue

            # Check 2: pt-BR Specific Lexicon
            if w_lower in pt_br_words:
                key = (w_lower, loc, "PT-BR")
                if key not in seen_keys:
                    seen_keys.add(key)
                    findings.append({
                        "loc": loc,
                        "type": "PT-BR Lexicon",
                        "severity": "HIGH",
                        "word": w_clean,
                        "suggestion": pt_br_words[w_lower].get("suggestion"),
                        "explanation": pt_br_words[w_lower].get("explanation"),
                    })
                continue

            # Check 3: pt-BR Consonant dropping (e.g. contatar -> contactar)
            if w_lower in pt_br_consonants:
                key = (w_lower, loc, "PT-BR Consonant")
                if key not in seen_keys:
                    seen_keys.add(key)
                    findings.append({
                        "loc": loc,
                        "type": "PT-BR Spelling",
                        "severity": "HIGH",
                        "word": w_clean,
                        "suggestion": pt_br_consonants[w_lower],
                        "explanation": f"Grafia brasileira ou consoante muda. Em pt-PT usa-se '{pt_br_consonants[w_lower]}'.",
                    })
                continue

            # Check 4: Enclitic pronouns in Portuguese (e.g. realizou-se, dar-lhe-á, encontram-se)
            # If word contains hyphens, check the parts if not found directly
            if "-" in w_lower and w_lower not in vocab:
                parts = w_lower.split("-")
                base_verb = parts[0]
                pronouns = {"se", "me", "te", "nos", "vos", "o", "a", "os", "as", "lhe", "lhes", "lo", "la", "los", "las", "no", "na", "nos", "nas"}
                if base_verb in vocab and all(p in pronouns for p in parts[1:]):
                    continue

            # Check 5: General pt-PT Vocabulary & Conjugations
            if w_lower not in vocab:
                key = (w_lower, loc, "SPELLING")
                if key not in seen_keys:
                    seen_keys.add(key)
                    findings.append({
                        "loc": loc,
                        "type": "Spelling / Unknown",
                        "severity": "LOW",
                        "word": w_clean,
                        "suggestion": "Verificar ortografia ou adicionar a whitelist.txt",
                        "explanation": f"A palavra '{w_clean}' não foi encontrada no vocabulário oficial de português europeu (Porto Editora / Natura).",
                    })

    elapsed = time.time() - t0
    return findings, elapsed, loc_label


def format_report(file_path, findings, elapsed, loc_label):
    lines = []
    lines.append("=" * 80)
    lines.append(f"  PORTUGUESE (pt-PT) SPELLCHECK & STYLE REPORT")
    lines.append(f"  Target: {os.path.basename(file_path)}")
    lines.append(f"  Execution Time: {elapsed:.2f}s (0 AI tokens / 0 API credits)")
    lines.append("=" * 80)

    if not findings:
        lines.append("\n  ✅ Parabéns! Não foram encontrados desvios ortográficos nem termos pt-BR/IA.")
        lines.append("=" * 80)
        return "\n".join(lines)

    # Group findings by type
    ai_isms = [f for f in findings if f["type"] == "AI-ISM / Calque"]
    pt_br = [f for f in findings if "PT-BR" in f["type"]]
    repetitions = [f for f in findings if f["type"] == "Style / Repetition"]
    spelling = [f for f in findings if f["type"] == "Spelling / Unknown"]

    lines.append(f"\nSummary: {len(findings)} items flagged")
    lines.append(f"  - 🚫 AI-isms / False Friends (e.g. escopo): {len(ai_isms)}")
    lines.append(f"  - 🇧🇷 Brazilian Portuguese (pt-BR terms):     {len(pt_br)}")
    lines.append(f"  - 🔁 Verb Repetitions (same sentence):      {len(repetitions)}")
    lines.append(f"  - ✍️ Unknown / Spelling doubts:             {len(spelling)}")
    lines.append("-" * 80)

    if ai_isms:
        lines.append("\n[1] 🚫 AI-ISMS & FALSE FRIENDS (Correção Recomendada):")
        for item in ai_isms:
            lines.append(f"  • [{loc_label} {item['loc']}] '{item['word']}'")
            lines.append(f"    ➜ Sugestão pt-PT: {item['suggestion']}")
            lines.append(f"    ℹ {item['explanation']}\n")

    if pt_br:
        lines.append("\n[2] 🇧🇷 BRAZILIAN PORTUGUESE (pt-BR detectado):")
        for item in pt_br:
            lines.append(f"  • [{loc_label} {item['loc']}] '{item['word']}'")
            lines.append(f"    ➜ Sugestão pt-PT: {item['suggestion']}")
            lines.append(f"    ℹ {item['explanation']}\n")

    if repetitions:
        lines.append("\n[3] 🔁 REPETIÇÕES VERBAIS NA MESMA FRASE (Estilo):")
        for item in repetitions:
            lines.append(f"  • [{loc_label} {item['loc']}] {item['word']}")
            lines.append(f"    ➜ Sugestão: {item['suggestion']}")
            lines.append(f"    ℹ {item['explanation']}\n")

    if spelling:
        lines.append(f"\n[4] ✍️ OUTRAS PALAVRAS NÃO RECONHECIDAS ({len(spelling)}):")
        lines.append("  (Se forem termos técnicos legítimos, adicione-os ao ficheiro 'whitelist.txt')")
        for item in spelling[:30]:  # limit to first 30 to avoid overwhelming output
            lines.append(f"  • [{loc_label} {item['loc']}] '{item['word']}'")
        if len(spelling) > 30:
            lines.append(f"  ... e mais {len(spelling) - 30} palavras.")

    lines.append("=" * 80)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Check European Portuguese (pt-PT) in PDF, LaTeX, and text files.")
    parser.add_argument("file", nargs="?", default=None, help="Path to file to check (.pdf, .tex, .md, .txt)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--whitelist-add", help="Add a word to whitelist.txt and exit")
    args = parser.parse_args()

    if args.whitelist_add:
        word = args.whitelist_add.strip()
        with open(WHITELIST_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{word}\n")
        print(f"Added '{word}' to {WHITELIST_FILE}")
        return

    if not args.file:
        parser.print_help()
        sys.exit(1)

    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}")
        sys.exit(1)

    findings, elapsed, loc_label = check_portuguese(args.file)

    if args.json:
        print(json.dumps({"file": args.file, "elapsed": elapsed, "findings": findings}, indent=2, ensure_ascii=False))
    else:
        print(format_report(args.file, findings, elapsed, loc_label))


if __name__ == "__main__":
    main()
