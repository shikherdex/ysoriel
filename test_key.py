import os

from config import BASE, get_key

print("Folder:", BASE)

p = BASE / ".streamlit" / "secrets.toml"
print("secrets.toml mila?:", p.exists(), "->", p)
print("Env var GEMINI_API_KEY set?:", bool(os.environ.get("GEMINI_API_KEY")))

k = get_key()
if not k:
    print("❌ Koi key mili hi nahi (file path ya naam galat hai)")
else:
    print("Key length:", len(k), "(normal: lagbhag 39)")
    print("Shuru ke 4 chars:", k[:4])
    print("Space/quote hai?:", k != k.strip() or '"' in k or "'" in k)
    print("Placeholder hai?:", "PASTE" in k.upper())
    if len(k) > 10:
        import llm
        try:
            print("Gemini jawab:", llm.ask("Bas 'ok' bolo."))
        except Exception as e:
            print("❌", str(e)[:200])
