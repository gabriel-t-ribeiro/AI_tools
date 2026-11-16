#!/usr/bin/env python3
"""
High-Fidelity Local Audio Transcription Module for Obsidian Vault.
Leverages MLX-Whisper with Apple Silicon GPU/Metal acceleration.
Default high-precision model: mlx-community/whisper-large-v3-mlx (1550M parameters).

Features:
- Automatic technical vocabulary prompt injection per academic course.
- Whisper repetition loop and hallucination suppressor.
- Output storage in <discipline>_transcrições (e.g. ppfm_transcrições).
- Automatic bidirectional Obsidian wikilink insertion into corresponding weekly note.
"""

import os
import sys
import re
import glob
import time
import math

# Ensure Homebrew binaries (e.g. ffmpeg) are on PATH
os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

# High-precision default model (Full Large-v3)
DEFAULT_MODEL = "mlx-community/whisper-large-v3-mlx"

# Automatic technical vocabularies and context prompts (PT-PT)
DISCIPLINE_PROMPTS = {
    "ppfm": (
        "Aula de Processamento de Polímeros e Ferramentas Moldantes (PPFM). "
        "Terminologia estrita em Português de Portugal (PT-PT): "
        "DSC (Calorimetria Diferencial de Varrimento ou Análise Diferencial de Varrimento), "
        "TGA (Termogravimetria ou Análise Termogravimétrica), "
        "termograma, linha de base, fluxo de calor, sinal exo up / endo down, "
        "Tg (temperatura de transição vítrea), Tm (temperatura de fusão), Tc / Tcc (temperatura de cristalização / a frio), "
        "temperatura onset e endset, integral do pico de fusão, entalpia de fusão (ΔHm), grau de cristalinidade (Xc), "
        "esferulitos, polímeros amorfos, semicristalinos, isotáctico, sin táctico, atáctico, "
        "higroscópico, reologia, viscosidade, extrusão, moldação por injeção, nanocompósitos, nanopartículas de cobre, "
        "degradação térmica, janela de processamento, contração volumétrica, empeno, patamares de compactação, atmosfera inerte de azoto."
    ),
    "ma": (
        "Aula de Maquinagem Avançada (MA) na Universidade de Aveiro. "
        "Termos técnicos: fresagem, torneamento, maquinabilidade, compósitos, maquinagem a alta velocidade (HSM), "
        "maquinagem por abrasão, retificação plana, maquinagem sustentável, fluido de corte de base vegetal, óleo vegetal, "
        "desgaste de flanco (VB), equação de Taylor, forças de corte, rugosidade superficial (Ra, Rz), formação de apara/cavaco, "
        "ferramentas de corte em metal duro, cerâmica, PCD, CBN, CAD/CAM, eixos CNC."
    ),
    "savi": (
        "Aula de Sistemas Autónomos e Visão Industrial (SAVI). "
        "Termos técnicos: visão por computador, processamento de imagem, OpenCV, ROS, ROS2, robótica autónoma, "
        "calibração de câmara, matriz intrínseca, extrínseca, deteção de contornos, segmentação, point clouds, LIDAR."
    ),
    "dpe": (
        "Reunião e aula de Dissertação e Projeto de Engenharia (DPE) / Apoio à Dissertação e Projeto de Engenharia (ADPE). "
        "Termos técnicos: dissertação de mestrado, tese, planeamento, organização e métodos, metodologia científica, "
        "operação eficiente de bombagem, bomba centrífuga, caudalímetro, manómetro, condutas, atrito dinâmico, "
        "Darcy-Weisbach, equação de continuidade, perdas de carga, pump scheduling problem, controlo adaptativo, estado da arte."
    ),
    "adpe": (
        "Aula de Apoio à Dissertação e Projeto de Engenharia (ADPE). "
        "Termos técnicos: dissertação de mestrado, tese, planeamento, organização e métodos, metodologia científica, estado da arte."
    ),
    "sem": (
        "Seminários de Engenharia Mecânica (SEM). "
        "Termos técnicos: seminário, conferência, investigação e desenvolvimento, indústria, projeto, inovação."
    )
}

def format_timestamp(seconds: float) -> str:
    """Converts seconds into [HH:MM:SS] or [MM:SS] with protection against NaN/inf."""
    if seconds is None or not isinstance(seconds, (int, float)) or math.isnan(seconds) or math.isinf(seconds):
        return "00:00"
    total_seconds = max(0, int(round(float(seconds))))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

class WhisperProgressBar:
    """
    Real-time progress bar for Whisper transcription:
    - Clean visual progress bar: [████████████░░░░░░░░░░]
    - Percentage with 1 decimal place (e.g. 45.2%)
    - Processed audio time vs total duration: 14:32 / 32:11
    - Elapsed time and ETA estimation: 00:45 < ETA 00:55
    - Processing speed multiplier: ~26.5x
    """
    def __init__(self, total=None, unit="frames", disable=False, bar_length=24, **kwargs):
        self.total = max(1, total) if total else 1
        self.disable = disable
        self.bar_length = bar_length
        self.current = 0
        self.start_time = time.time()
        self.last_print_time = 0
        self.closed = False

        # 100 mel frames = 1 second of audio (160 hops / 16000 Hz = 0.01s)
        self.total_seconds = max(1.0, round(float(self.total) * 0.01))

        if not self.disable:
            self._render(initial=True)

    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds is None or not isinstance(seconds, (int, float)) or math.isnan(seconds) or math.isinf(seconds):
            return "00:00"
        total = max(0, int(round(float(seconds))))
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def update(self, n=1):
        if self.disable or self.closed:
            return
        valid_n = 0
        try:
            if n is not None and not math.isnan(n) and not math.isinf(n):
                valid_n = max(0, float(n))
        except (TypeError, ValueError):
            valid_n = 0

        self.current = min(self.total, self.current + valid_n)
        now = time.time()
        if now - self.last_print_time >= 0.15 or self.current >= self.total:
            self.last_print_time = now
            self._render()

    def _render(self, initial=False):
        now = time.time()
        elapsed = max(0.001, now - self.start_time)

        ratio = min(1.0, max(0.0, float(self.current) / float(self.total)))
        pct = round(ratio * 100.0, 1)

        if self.current >= self.total:
            pct = 100.0
            ratio = 1.0

        filled_len = int(round(self.bar_length * ratio))
        filled_len = min(self.bar_length, max(0, filled_len))
        bar = "█" * filled_len + "░" * (self.bar_length - filled_len)

        curr_sec = round(self.current * 0.01)
        curr_str = self._format_time(curr_sec)
        total_str = self._format_time(self.total_seconds)

        elapsed_str = self._format_time(elapsed)

        if ratio > 0.001 and self.current < self.total:
            remaining_sec = max(0.0, (elapsed / ratio) - elapsed)
            eta_str = self._format_time(remaining_sec)
            speed = round(curr_sec / elapsed, 1) if elapsed > 0 else 1.0
            speed_str = f"{speed:.1f}x"
        elif self.current >= self.total:
            eta_str = "00:00"
            speed = round(self.total_seconds / elapsed, 1) if elapsed > 0 else 1.0
            speed_str = f"{speed:.1f}x"
        else:
            eta_str = "--:--"
            speed_str = "--x"

        line = f"\r⏳ Transcribing: [{bar}] {pct:5.1f}% | 🎵 {curr_str} / {total_str} | ⏱️ {elapsed_str} < ETA {eta_str} ({speed_str})"
        sys.stderr.write(line)
        sys.stderr.flush()

    def close(self):
        if self.closed or self.disable:
            return
        self.closed = True
        self.current = self.total
        self._render()
        elapsed = max(0.001, time.time() - self.start_time)
        speed = round(self.total_seconds / elapsed, 1) if elapsed > 0 else 1.0
        sys.stderr.write(f"\n✨ Transcription completed in {self._format_time(elapsed)} ({speed:.1f}x real-time speed)!\n")
        sys.stderr.flush()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def identify_discipline_key(name_str: str) -> str:
    """Identifies the course code from filename and folder hierarchy."""
    basename = os.path.basename(name_str).lower()

    parent_path = os.path.dirname(name_str)
    disc_folder = ""
    for _ in range(3):
        folder_name = os.path.basename(parent_path).lower()
        if folder_name == "mp" or folder_name.endswith("_mp") or "pdf" in folder_name or "transcri" in folder_name:
            parent_path = os.path.dirname(parent_path)
            continue
        disc_folder = folder_name
        break

    combined = f"{disc_folder} {basename}"

    if "ppfm" in combined:
        return "ppfm"
    if "maquinagem" in combined or re.search(r"\bma\b", basename):
        return "ma"
    if "savi" in combined:
        return "savi"
    if "dissertation" in combined or "dissertação" in combined or re.search(r"\bdpe\b", combined):
        return "dpe"
    if "adpe" in combined:
        return "adpe"
    if re.search(r"\bsem\b", basename) or "semin" in combined:
        return "sem"
    if re.search(r"\bma\b", disc_folder) or "maquinagem" in disc_folder:
        return "ma"
    if re.search(r"\bsem\b", disc_folder):
        return "sem"
    return "geral"

def get_transcriptions_dir(disc_dir: str) -> str:
    """Gets or creates the transcriptions folder: <discipline>_transcriptions."""
    disc_name = os.path.basename(disc_dir)
    existing = [d for d in os.listdir(disc_dir) if os.path.isdir(os.path.join(disc_dir, d)) and "transcri" in d.lower()]
    if existing:
        return os.path.join(disc_dir, existing[0])

    sigla = identify_discipline_key(disc_name)
    if sigla == "geral":
        sigla = re.sub(r"^2m1s[_\s]*", "", disc_name, flags=re.IGNORECASE)
        sigla = re.sub(r"^2m[_\s]*", "", sigla, flags=re.IGNORECASE).strip().lower().split('_')[0].split()[0]

    target_dir = os.path.join(disc_dir, f"{sigla}_transcriptions")
    os.makedirs(target_dir, exist_ok=True)
    return target_dir

def clean_repeated_segments(segments: list, max_consecutive_repeats: int = 2) -> list:
    """Removes or truncates repeated hallucination loops from Whisper output."""
    cleaned = []
    current_repeat_count = 0
    last_normalized_text = ""

    for seg in segments:
        text = seg.get("text", "").strip()
        norm_text = re.sub(r"[^\w\s]", "", text.lower()).strip()

        if norm_text and norm_text == last_normalized_text:
            current_repeat_count += 1
        else:
            current_repeat_count = 1
            last_normalized_text = norm_text

        if current_repeat_count <= max_consecutive_repeats:
            cleaned.append(seg)
        elif current_repeat_count == max_consecutive_repeats + 1:
            print(f"⚠️ Blocked hallucination/repetition loop: '{text}'")

    return cleaned

def transcribe_audio(audio_path: str, model_name: str = DEFAULT_MODEL, language: str = "pt"):
    """Transcribes audio using MLX-Whisper with visual progress bar and vocabulary injection."""
    import mlx_whisper
    import tqdm

    disc_key = identify_discipline_key(audio_path)
    prompt = DISCIPLINE_PROMPTS.get(disc_key, "Transcrição de aula universitária em Português de Portugal com termos técnicos de engenharia.")

    model_display = os.path.basename(model_name)
    print(f"🎙️ Transcribing '{os.path.basename(audio_path)}' with {model_display}...")
    print(f"💡 Detected Course: [{disc_key.upper()}] — Technical vocabulary prompt active.")

    orig_tqdm = tqdm.tqdm
    tqdm.tqdm = WhisperProgressBar
    try:
        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=model_name,
            language=language,
            initial_prompt=prompt,
            temperature=(0.0, 0.2, 0.4),
            condition_on_previous_text=False,
            compression_ratio_threshold=2.4,
            no_speech_threshold=0.6,
            verbose=False,
        )
    finally:
        tqdm.tqdm = orig_tqdm

    if "segments" in result:
        result["segments"] = clean_repeated_segments(result["segments"])
        result["text"] = " ".join(s.get("text", "").strip() for s in result["segments"] if s.get("text", "").strip())
    return result

def generate_markdown_content(result: dict, audio_filename: str) -> str:
    """Generates formatted Markdown content with timestamps and clean text blocks."""
    segments = result.get("segments", [])
    full_text = result.get("text", "").strip()

    md_lines = [
        f"# Transcrição: {audio_filename}",
        "",
        f"**Ficheiro áudio:** ![[{audio_filename}]]",
        f"**Modelo utilizado:** Whisper Large-v3 (Precisão Máxima PT-PT)",
        "",
        "---",
        "",
        "## ⏱️ Transcrição com Timestamps",
        ""
    ]

    for seg in segments:
        start_str = format_timestamp(seg.get("start", 0))
        end_str = format_timestamp(seg.get("end", 0))
        text = seg.get("text", "").strip()
        if text:
            md_lines.append(f"- **`[{start_str} -> {end_str}]`** {text}")

    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## 📝 Texto Contínuo")
    md_lines.append("")
    md_lines.append(full_text)
    md_lines.append("")

    return "\n".join(md_lines)

def find_week_note(disc_dir: str, week_str: str):
    """Locates the primary weekly lecture note in the course folder."""
    pattern = rf"^{week_str}(?![0-9]).*\.md$"
    candidates = []
    for item in os.listdir(disc_dir):
        if re.match(pattern, item, re.IGNORECASE) and not item.lower().endswith(("trabalho de grupo.md", "group_work.md", "_ai_note.md", "_transcription.md")):
            candidates.append(item)

    if candidates:
        candidates.sort(key=len)
        return os.path.join(disc_dir, candidates[0])
    return None

def connect_transcription_to_week_note(disc_dir: str, audio_filename: str, transcript_md_name: str, week_str: str = None):
    """Inserts [[transcription]] wikilink below audio embed in the weekly note without altering draft notes."""
    audio_embed = f"![[{audio_filename}]]"
    transcription_link = f"[[{transcript_md_name}]]"

    if not week_str:
        m = re.match(r"^(w\d+)", audio_filename, re.IGNORECASE)
        if m:
            week_str = m.group(1).lower()

    target_note = None
    for root, _, files in os.walk(disc_dir):
        if "transcri" in root.lower():
            continue
        for f in files:
            if f.endswith(".md"):
                p = os.path.join(root, f)
                try:
                    with open(p, "r", encoding="utf-8") as nf:
                        content = nf.read()
                    if audio_embed.lower() in content.lower():
                        target_note = p
                        break
                except Exception:
                    pass
        if target_note:
            break

    if not target_note and week_str:
        target_note = find_week_note(disc_dir, week_str)

    if not target_note:
        print(f"⚠️ Corresponding lecture note for '{audio_filename}' was not found for automatic link insertion.")
        return False

    with open(target_note, "r", encoding="utf-8") as nf:
        content = nf.read()

    if transcription_link in content:
        print(f"ℹ️ Link '{transcription_link}' already exists in '{os.path.basename(target_note)}'.")
        return True

    if audio_embed in content:
        pattern = re.compile(rf"({re.escape(audio_embed)})", re.IGNORECASE)
        new_content = pattern.sub(rf"\1\n> 📜 Transcrição: {transcription_link}", content, count=1)
    else:
        new_content = f"> 📜 Transcrição: {transcription_link}\n\n" + content

    with open(target_note, "w", encoding="utf-8") as nf:
        nf.write(new_content)

    print(f"🔗 Transcription linked successfully to: {os.path.basename(target_note)}")
    return True

def process_single_audio(audio_path: str, model_name: str = DEFAULT_MODEL):
    """Transcribes an audio file and connects it to the weekly lecture note."""
    audio_path = os.path.abspath(audio_path)
    if not os.path.exists(audio_path):
        print(f"❌ Audio file not found: {audio_path}")
        return None

    audio_dir = os.path.dirname(audio_path)
    audio_filename = os.path.basename(audio_path)
    base_name, _ = os.path.splitext(audio_filename)

    parent_dir = os.path.dirname(audio_dir)
    audio_dir_name = os.path.basename(audio_dir).lower()
    disc_dir = parent_dir if (audio_dir_name == "mp" or audio_dir_name.endswith("_mp")) else audio_dir

    transcriptions_dir = get_transcriptions_dir(disc_dir)

    transcript_md_name = f"{base_name}_transcription"
    out_file = os.path.join(transcriptions_dir, f"{transcript_md_name}.md")

    result = transcribe_audio(audio_path, model_name=model_name)
    md_content = generate_markdown_content(result, audio_filename)

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"✅ Transcription saved to: {out_file}")

    connect_transcription_to_week_note(disc_dir, audio_filename, transcript_md_name)

    return out_file

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("Usage: python3 transcribe.py <path_to_audio.m4a>")
        print("       ./transcribe.py <path_to_audio.m4a>")
        print("\nDescription:")
        print("  Transcribes class recordings locally with Metal acceleration (Apple Silicon)")
        print("  using MLX-Whisper Large-v3.")
        print("  Injects technical course vocabularies, creates Markdown with timestamps,")
        print("  and links the transcript to the corresponding weekly lecture note.")
        print("\nExample:")
        print("  python3 transcribe.py 'vault/2m1s_ppfm/ppfm_mp/w39_ppfm_a1.m4a'")
        sys.exit(0 if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help", "help") else 1)

    target_audio = sys.argv[1]
    process_single_audio(target_audio)

if __name__ == "__main__":
    main()
