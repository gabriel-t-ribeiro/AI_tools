#!/usr/bin/env python3
"""
Cloud Audio Transcription Benchmark and Testing Script.
Tests audio transcription using Cloud AI APIs (Google Gemini 2.5 Pro or Groq Whisper Large-v3).
Requires API keys configured in .env file.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def test_gemini(audio_path: Path, api_key: str) -> str:
    """Sends audio to Gemini 2.5 Pro for fidelity transcription in European Portuguese."""
    from google import genai
    from google.genai import types

    print("Initializing Gemini client...")
    client = genai.Client(api_key=api_key)

    print(f"Uploading file: {audio_path.name}...")
    audio_file = client.files.upload(file=str(audio_path))

    prompt = """
    És um assistente de transcrição de aulas de engenharia em português de Portugal.
    Transcreve o áudio em anexo. 
    Se possível, adiciona timestamps no início de cada bloco principal de ideias.
    Não resumas, apenas transcreve fielmente o que é dito.
    """

    print("Generating Cloud transcription (Gemini 2.5 Pro)...")
    response = client.models.generate_content(
        model='gemini-2.5-pro',
        contents=[audio_file, prompt]
    )

    return response.text

def test_groq(audio_path: Path, api_key: str) -> str:
    """Sends audio to Groq Whisper-large-v3 API."""
    from groq import Groq

    print("Initializing Groq client...")
    client = Groq(api_key=api_key)

    print("Transcribing with Whisper Large v3 on Groq Cloud...")
    with open(audio_path, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(audio_path.name, file.read()),
            model="whisper-large-v3",
            prompt="Transcreve a aula. O idioma é português de Portugal. A aula é sobre Processamento e Propriedades de Ficheiros Metálicos.",
            response_format="verbose_json",
        )

    formatted_text = ""
    for segment in transcription.segments:
        start = int(segment['start'])
        minutes, seconds = divmod(start, 60)
        formatted_text += f"- **`[{minutes:02}:{seconds:02}]`** {segment['text'].strip()}\n"

    return formatted_text

def main():
    load_dotenv()

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("Usage: python3 test_cloud_transcription.py <path_to_audio.m4a> [--gemini | --groq]")
        print("       ./test_cloud_transcription.py <path_to_audio.m4a> [--gemini | --groq]")
        print("\nDescription:")
        print("  Tests audio transcription using Cloud AI services")
        print("  (Gemini 2.5 Pro or Groq Whisper Large-v3). Requires API keys in .env.")
        print("\nExample:")
        print("  python3 test_cloud_transcription.py 'vault/2m1s_ppfm/ppfm_mp/w39_ppfm_a1.m4a' --groq")
        return

    audio_path = Path(sys.argv[1])
    if not audio_path.exists():
        print(f"File not found: {audio_path}")
        return

    print(f"Selected audio: {audio_path.name}")

    choice = None
    if len(sys.argv) >= 3:
        if sys.argv[2] == "--gemini":
            choice = "1"
        elif sys.argv[2] == "--groq":
            choice = "2"

    if not choice:
        print("Which cloud service would you like to test?")
        print("1) Gemini 2.5 Pro (Requires GEMINI_API_KEY)")
        print("2) Groq Whisper-large-v3 (Requires GROQ_API_KEY)")
        choice = input("Option (1 or 2): ").strip()

    if choice == "1":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY not found in .env")
            return
        text_out = test_gemini(audio_path, api_key)
        prefix = "Gemini"
    elif choice == "2":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("Error: GROQ_API_KEY not found in .env")
            return
        text_out = test_groq(audio_path, api_key)
        prefix = "Groq"
    else:
        print("Invalid option.")
        return

    # Save to distinct test file
    base_name = audio_path.stem
    parent_folder = audio_path.parent
    course_folder = parent_folder.parent

    try:
        transcription_folder = next(course_folder.glob("*_transcrições"))
    except StopIteration:
        sigla = course_folder.name.split(' ', 1)[1].lower()[:4]
        transcription_folder = course_folder / f"{sigla}_transcrições"

    transcription_folder.mkdir(exist_ok=True)
    new_file = transcription_folder / f"{base_name}_transcription_{prefix.lower()}_cloud.md"

    with open(new_file, "w", encoding="utf-8") as f:
        f.write(f"# Transcrição Cloud ({prefix})\n\n")
        f.write(text_out)

    print(f"Transcription successfully saved to: {new_file}")

if __name__ == "__main__":
    main()
