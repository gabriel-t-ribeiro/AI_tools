#!/usr/bin/env python3
"""
Compatibility alias for transcribe.py.
Permite executar indistintamente:
  python3 transcription_pipeline.py <audio>
  python3 transcribe.py <audio>
"""
import os
import sys

# Garante que importa o módulo transcrever do mesmo diretório
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from transcribe import main

if __name__ == "__main__":
    main()
