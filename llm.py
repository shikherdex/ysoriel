import json
import re
import time

from google import genai
from google.genai import types

from config import MODELS, ATTEMPTS, get_key

_client = None
TIMEOUT_MS = 25000
_no_think_bad = set()  # jin models par thinking_budget=0 invalid nikla


def client():
    global _client
    if _client is None:
        key = get_key()
        if not key:
            raise RuntimeError("GEMINI_API_KEY nahi mili. .streamlit/secrets.toml mein daalo.")
        _client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    return _client


def _build_cfg(system, tools, json_mode, grounded, temperature, no_think):
    kw = dict(system_instruction=system or None, temperature=temperature)
    if grounded:
        kw["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    elif tools:
        kw["tools"] = tools
        kw["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(maximum_remote_calls=8)
    if json_mode:
        kw["response_mime_type"] = "application/json"
    if no_think:
        kw["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    return types.GenerateContentConfig(**kw)


def _call(model, prompt, system, tools, json_mode, grounded, temperature):
    """Ek request. 400 aaye to thinking config hata kar usi model par ek baar dobara."""
    no_think = model not in _no_think_bad
    try:
        cfg = _build_cfg(system, tools, json_mode, grounded, temperature, no_think)
        return client().models.generate_content(model=model, contents=prompt, config=cfg).text or ""
    except Exception as e:  # noqa
        msg = str(e)
        if no_think and ("400" in msg or "INVALID_ARGUMENT" in msg or "thinking" in msg.lower()):
            _no_think_bad.add(model)
            cfg = _build_cfg(system, tools, json_mode, grounded, temperature, False)
            return client().models.generate_content(model=model, contents=prompt, config=cfg).text or ""
        raise


def ask(prompt, system="", tools=None, json_mode=False, grounded=False, temperature=0.4):
    """Workflow: ATTEMPTS baar request, models ke order mein (.5 -> .7 -> .8 -> .5 -> .7 ...)."""
    last = None
    for i in range(ATTEMPTS):
        model = MODELS[i % len(MODELS)]
        t0 = time.time()
        try:
            out = _call(model, prompt, system, tools, json_mode, grounded, temperature)
            print(f"   [llm] try {i + 1}/{ATTEMPTS} {model} OK {time.time() - t0:.1f}s")
            return out
        except Exception as e:  # noqa
            last = e
            print(f"   [llm] try {i + 1}/{ATTEMPTS} {model} FAIL {time.time() - t0:.1f}s: {str(e)[:120]}")
            time.sleep(0.5)
    raise RuntimeError(f"{ATTEMPTS} koshish ke baad bhi fail: {last}")


def _parse_json(raw):
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        cand = m.group(0)
        for fixed in (cand, re.sub(r",\s*([}\]])", r"\1", cand)):  # trailing comma hatao
            try:
                return json.loads(fixed)
            except Exception:
                pass
    raise ValueError("JSON parse nahi hua")


def ask_json(prompt, system="", temperature=0.2):
    """JSON galat aaye toh auto-repair, phir max 3 baar dobara maangta hai."""
    last = None
    for i in range(3):
        p = prompt if i == 0 else prompt + "\n\nIMPORTANT: sirf valid JSON do. Double quotes, strings ke andar quotes escape karo, koi trailing comma ya extra text nahi."
        raw = ask(p, system=system, json_mode=True, temperature=temperature if i == 0 else 0)
        try:
            return _parse_json(raw)
        except Exception as e:  # noqa
            last = e
            print(f"   [llm] JSON galat aaya (try {i + 1}/3): {e}")
    raise RuntimeError(f"JSON 3 baar galat aaya: {last}")
