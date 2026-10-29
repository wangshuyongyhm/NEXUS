"""tests 自举：未 pip install 也能从 checkout 直接跑 pytest（gate C5/CI 友好）。"""
import sys
from pathlib import Path

_src = Path(__file__).resolve().parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
