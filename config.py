import os
import tomllib
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

# Models retire hote rehte hain: list edit kar sakte ho
MODELS = ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3.8-flash"]  # order = try order
ATTEMPTS = 5  # total requests: .5 -> .7 -> .8 -> .5 -> .7


def get_key():
    k = os.environ.get("GEMINI_API_KEY")
    if k:
        return k
    p = BASE / ".streamlit" / "secrets.toml"
    if p.exists():
        return tomllib.loads(p.read_text(encoding="utf-8")).get("GEMINI_API_KEY")
    return None
