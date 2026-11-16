#!/usr/bin/env python3
"""
Model Benchmark and Testing Script:
Runs transcription with an alternative model (e.g. whisper-large-v3-turbo)
and saves output with a suffix: 'teste_<model_label>' in transcriptions directory,
without modifying the main transcript or the class note.
"""

import os
import sys
import re

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

from transcribe import (
    identify_discipline_key,
    get_transcriptions_dir,
    clean_repeated_segments,
    generate_markdown_content,
    DISCIPLINE_PROMPTS
)
import mlx_whisper

def test_transcribe(audio_path: str, model_repo: str, model_label: str):
    """Executes benchmark transcription using specified model repository."""
    audio_path = os.path.abspath(audio_path)
    if not os.path.exists(audio_path):
        print(f"❌ Audio file not found: {audio_path}")
        sys.exit(1)

    audio_dir = os.path.dirname(audio_path)
    audio_filename = os.path.basename(audio_path)
    base_name, _ = os.path.splitext(audio_filename)

    parent_dir = os.path.dirname(audio_dir)
    audio_dir_name = os.path.basename(audio_dir).lower()
    disc_dir = parent_dir if (audio_dir_name == "mp" or audio_dir_name.endswith("_mp")) else audio_dir
    transcriptions_dir = get_transcriptions_dir(disc_dir)

    out_file = os.path.join(transcriptions_dir, f"{base_name}_transcription_test_{model_label}.md")

    disc_key = identify_discipline_key(audio_path)
    prompt = DISCIPLINE_PROMPTS.get(disc_key, "Transcrição de aula de engenharia.")

    print(f"🎙️ Testing model [{model_label}] ({model_repo})...")
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=model_repo,
        language="pt",
        initial_prompt=prompt,
        temperature=(0.0, 0.2, 0.4),
        condition_on_previous_text=False,
        compression_ratio_threshold=2.4,
        no_speech_threshold=0.6,
        hallucination_silence_threshold=1.5
    )

    if "segments" in result:
        result["segments"] = clean_repeated_segments(result["segments"])
        result["text"] = " ".join(s.get("text", "").strip() for s in result["segments"] if s.get("text", "").strip())

    md_content = generate_markdown_content(result, audio_filename)
    md_content = md_content.replace(
        "Whisper Large-v3 (Precisão Máxima PT-PT)",
        f"Whisper ({model_label})"
    )

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"✅ Test transcript saved to:\n{out_file}")
    return out_file

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help", "help"):
        print("Usage: python3 test_transcription_model.py [audio_path] [model_repo] [model_label]")
        print("       ./test_transcription_model.py [audio_path] [model_repo] [model_label]")
        print("\nDescription:")
        print("  Tests transcription using an alternative MLX model (e.g. whisper-large-v3-turbo)")
        print("  and writes output to a test file without touching production transcripts.")
        print("\nExample:")
        print("  python3 test_transcription_model.py 'vault/2m1s_ppfm/ppfm_mp/w39_ppfm_a1.m4a' mlx-community/whisper-large-v3-turbo turbo")
        sys.exit(0)

    audio = sys.argv[1] if len(sys.argv) > 1 else "2m1s PPFM/ppfm_mp/w39_ppfm_end_of_lecture.m4a"
    model = sys.argv[2] if len(sys.argv) > 2 else "mlx-community/whisper-large-v3-turbo"
    label = sys.argv[3] if len(sys.argv) > 3 else "whisper_large_v3_turbo"

    test_transcribe(audio, model, label)
