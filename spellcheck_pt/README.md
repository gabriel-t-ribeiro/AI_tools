# 🇵🇹 Spellcheck pt-PT

A fast, lightweight, and completely local (**0 AI tokens / 0 API credits**) spellchecker and style guard for **European Portuguese (`pt-PT`)**.

Designed to verify academic reports, scientific papers, LaTeX documents, and PDFs in under a second.

---

## ✨ Features

- **2,060,000+ European Portuguese Inflections:** Built from the official Natura/LibreOffice Hunspell dictionaries combined with 110,000+ lemmas from the *Grande Dicionário da Língua Portuguesa da Porto Editora*. Automatically handles all verb conjugations, enclitic pronouns (*fazer-se*, *disse-lhe*), plurals, and feminines.
- **Brazilian Portuguese (pt-BR) Filter:** Intercepts common pt-BR vocabulary and orthography (*usuário* $\rightarrow$ *utilizador*, *tela* $\rightarrow$ *ecrã*, *arquivo* $\rightarrow$ *ficheiro*, *cadastrar* $\rightarrow$ *registar*, *time* $\rightarrow$ *equipa*, *trem* $\rightarrow$ *comboio*, *contatar* $\rightarrow$ *contactar*).
- **AI-ism & False Friend Guard:** Intercepts typical LLM translation calques (e.g. **`escopo`** $\rightarrow$ *âmbito*, *alcance*; **`acurácia`** $\rightarrow$ *exatidão*, *precisão*; **`alavancar`** $\rightarrow$ *potenciar*, *impulsionar*; **`customizar`** $\rightarrow$ *personalizar*; **`performar`** $\rightarrow$ *desempenhar*).
- **Format Support:** Works seamlessly on:
  - **PDF documents** (`.pdf`) — outputs page numbers.
  - **LaTeX sources** (`.tex`) — automatically ignores LaTeX markup, environments (`table`, `figure`), references (`\cite`, `\ref`), and math blocks (`$...$`, `$$...$$`).
  - **Markdown & Plain Text** (`.md`, `.txt`).
- **Domain Whitelist (`whitelist.txt`):** Easily ignore technical acronyms (*CAD*, *CFD*, *ORC*), project names (*BW2C*, *SustainC*), and code variables.

---

## 🚀 Quick Start

Run directly from your project terminal:

```bash
# Check a PDF file
python3 tools/spellcheck_pt/check_pt.py document.pdf

# Check a LaTeX file
python3 tools/spellcheck_pt/check_pt.py report/src/01_intro.tex

# Check a Markdown or text file
python3 tools/spellcheck_pt/check_pt.py README.md

# Add a project-specific word to the whitelist
python3 tools/spellcheck_pt/check_pt.py --whitelist-add "MinhaPalavraTecnica"
```

---

## 📁 Folder Structure

```text
tools/spellcheck_pt/
├── check_pt.py               # Main CLI checker
├── vocab_builder.py          # Vocabulary compiler with morphological inflection
├── dictionaries/
│   ├── pt_PT.aff             # Official Hunspell affix inflection rules
│   ├── pt_PT.dic             # Official European Portuguese word stems
│   ├── porto_editora_lemmas.txt # Extracted Porto Editora lemmas
│   └── pt_PT_vocab.pkl.gz    # Pre-compiled high-speed cache (loads in ~0.1s)
├── rules/
│   ├── ai_isms.json          # AI cliches & false friends (escopo, acurácia, etc.)
│   └── pt_br_lexicon.json    # pt-BR detection & pt-PT suggestions
├── whitelist.txt             # Project-specific approved terminology
├── test_sample.txt           # Sample test file
└── README.md                 # This documentation
```

---

## 📦 How to Use in Future Projects

This tool is 100% portable and has **no system package dependencies**.

To use it in another project:
1. Copy the `tools/spellcheck_pt` folder into your new project:
   ```bash
   cp -r tools/spellcheck_pt /path/to/my_new_project/tools/
   ```
2. Run it with Python 3:
   ```bash
   python3 tools/spellcheck_pt/check_pt.py my_document.pdf
   ```
*(Note: standard Python 3 is all that is required; `pypdf` is only needed if reading `.pdf` files).*
