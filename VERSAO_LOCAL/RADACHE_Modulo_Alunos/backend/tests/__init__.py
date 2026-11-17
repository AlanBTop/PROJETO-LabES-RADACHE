"""Testes de demonstração: importações reproduzíveis sem configurar PYTHONPATH."""
import os
from pathlib import Path
import sys

os.environ.setdefault('RADACHE_DEMO', '1')
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
