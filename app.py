"""YSORIEL: local web app. Serves the UI in web/ and a JSON API on top of the NEXUS backend.

Run: python app.py      (then open http://127.0.0.1:8000)
"""
import json
import re
import threading
import uuid
import webbrowser
from datetime import date, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import approvals
import llm
import orchestrator
import store
import tools as T
from agents import REGISTRY, SPECS

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"  # only this folder is served: store.json and secrets.toml stay private
HOST, PORT = "127.0.0.1", 8000
llm.TIMEOUT_MS = 45000  # 25s was too tight for tool-calling requests and caused retries

# ---------- AGENT META (names/roles/tools come from the real agents) ----------
GLYPHS = {
    "chief": "✧", "secretary": "◷", "travel": "⌁", "finance": "↗", "shopping": "◇", "health": "♡",
    "comms": "✉", "home": "⌂", "career": "✦", "research": "◎", "memory": "◉", "proactive": "⚡",
}
PERMS = {
    "chief": ["Task routing", "Agent delegation", "Result synthesis"],
    "secretary": ["Calendar review", "Conflict checking", "Reminder setting", "Remove events & reminders"],
    "travel": ["Travel research", "Itinerary planning", "Booking requests (approval)"],
    "finance": ["Budget analysis", "Expense tracking", "Overspending alerts", "Reset money (approval)"],
    "shopping": ["Product comparison", "Price research", "Purchase requests (approval)"],
    "health": ["Wellness plans", "Meal & workout ideas", "Weather-aware advice"],
    "comms": ["Draft emails", "Rewrite tone", "Send requests (approval)"],
    "home": ["Errand lists", "Grocery & chores", "Edit & remove list items", "Local research"],
    "career": ["Opportunity research", "Skill paths", "Deadline reminders"],
    "research": ["Source comparison", "Evidence checking", "Decision summaries"],
    "memory": ["Preference storage", "Context retrieval", "Delete requests (approval)"],
    "proactive": ["Conflict detection", "Budget alerts", "Priority suggestions"],
}
APPROVAL_AGENT = {"comms": "communication"}  # approvals.py uses a different name for comms

# ---------- PAUSED AGENTS ----------

def paused_keys():
    return set(store.load()["settings"].get("paused", []))


def sync_workers():
    """Paused agents are removed from the orchestrator's worker list; the rest are put back."""
    paused = paused_keys()
    for k, a in REGISTRY.items():
        if k == "chief":
            continue
        if k in paused:
            orchestrator.WORKERS.pop(k, None)
        else:
            orchestrator.WORKERS[k] = a


# ---------- JOBS (a request can take 30-60s, so it runs in a thread and the UI polls) ----------
JOBS = {}
JOBS_LOCK = threading.Lock()
CURRENT = {"id": None}  # one request at a time keeps pause/resume and statuses consistent
STALE_AFTER = 360  # seconds: a request stuck longer than this stops blocking new ones


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _running_job():
    """The job that is genuinely running now (caller holds JOBS_LOCK). A hung one is marked failed so you are never locked out."""
    j = JOBS.get(CURRENT["id"]) if CURRENT["id"] else None
    if not j or j["status"] != "running":
        return None
    if (datetime.now() - datetime.fromisoformat(j["started"])).total_seconds() < STALE_AFTER:
        return j
    j["status"], j["updated"] = "error", _now()
    j["answer"] = "Ye request bahut der se atki thi (Gemini slow ya timeout), isliye chhod di. Dobara try karo."
    CURRENT["id"] = None
    return None


def _public_job(j):
    total = j["total"]
    if j["status"] == "running":
        pct = 8 if not total else min(95, round(j["done"] / (total + 1) * 100))
    else:
        pct = 100
    return {
        "id": j["id"], "q": j["q"], "status": j["status"], "started": j["started"], "updated": j["updated"],
        "done": j["done"], "total": total, "pct": pct, "agents": list(j["agents"]) or j["planned"][:],
        "ran": j["agents"], "answer": j["answer"], "log": j["log"],
    }


def _on_progress(job, msg):
    with JOBS_LOCK:
        job["log"].append(msg)
        job["updated"] = _now()
        m = re.match(r"^\s*• (\S+) → (\w+)", msg)
        if m:
            job["total"] += 1
            job["planned"].append(m.group(2))
        m = re.match(r"^(✅|❌) (\w+) \(([\d.]+)s\)", msg)
        if m:
            job["agents"][m.group(2)] = {"ok": m.group(1) == "✅", "sec": float(m.group(3))}
            job["done"] += 1


def _run_job(job):
    try:
        try:
            ans = orchestrator.handle(job["q"], progress=lambda m: _on_progress(job, m))
            status = "done"
        except Exception as e:  # noqa
            ans, status = f"Error: {e}", "error"
        ans = ans.split("\n\n⏳")[0]  # the terminal-only "/approve N" hint is not needed in the UI
        with JOBS_LOCK:
            job["answer"], job["status"], job["updated"] = ans, status, _now()
            snap = _public_job(job)
        store.update(lambda d: d["jobs"].__setitem__(slice(None), (d["jobs"] + [snap])[-30:]))
    finally:
        with JOBS_LOCK:
            if CURRENT["id"] == job["id"]:
                CURRENT["id"] = None


def start_job(q):
    with JOBS_LOCK:
        if _running_job():
            return None
        job = {"id": uuid.uuid4().hex[:10], "q": q, "status": "running", "started": _now(), "updated": _now(),
               "log": [], "total": 0, "done": 0, "planned": [], "agents": {}, "answer": ""}
        JOBS[job["id"]] = job
        CURRENT["id"] = job["id"]
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    return job["id"]


def get_job(jid):
    with JOBS_LOCK:
        if jid in JOBS:
            return _public_job(JOBS[jid])
    return next((j for j in store.load()["jobs"] if j["id"] == jid), None)


# ---------- STATE ----------

def _activity(d, jobs):
    items = []
    for e in d["log"][-10:]:
        data = e.get("data", {})
        detail = data.get("what") or data.get("item") or (f"to {data['to']}" if data.get("to") else "")
        items.append({"t": e["t"], "tone": "blue", "who": "You approved", "text": f"{e['event'].capitalize()} {detail}".strip()})
    for a in d["approvals"][-10:]:
        items.append({"t": a["created"], "tone": "violet", "who": a["agent"].capitalize(),
                      "text": f"asked for your approval: {a['summary']}"})
    for j in jobs:
        if j["status"] != "running":
            n = len(j["ran"])
            items.append({"t": j["updated"], "tone": "mint" if j["status"] == "done" else "violet", "who": "Chief of Staff",
                          "text": f"finished “{j['q'][:70]}” using {n} agent{'s' if n != 1 else ''}"})
    return sorted(items, key=lambda x: x["t"], reverse=True)[:6]


def build_state():
    d = store.load()
    with JOBS_LOCK:
        _running_job()
        live = [_public_job(j) for j in JOBS.values()]
    seen = {j["id"] for j in live}
    jobs = sorted(live + [j for j in d["jobs"] if j["id"] not in seen], key=lambda j: j["started"], reverse=True)[:12]
    running = next((j["id"] for j in jobs if j["status"] == "running"), None)
    last = next((j for j in jobs if j["status"] != "running"), None)
    last_ran = last["ran"] if last else {}
    paused = paused_keys()

    agents = []
    for s in SPECS:
        if s.key in paused:
            status = "paused"
        elif s.key == "chief":
            status = "active" if jobs else "idle"
        else:
            status = "active" if s.key in last_ran else "idle"
        mine = [a for a in d["approvals"] if a["agent"] == APPROVAL_AGENT.get(s.key, s.key)]
        agents.append({
            "key": s.key, "name": s.name, "role": s.role, "glyph": GLYPHS.get(s.key, "✦"), "status": status,
            "tools": [f.__name__ for f in s.tools] or ["Orchestrator"], "perms": PERMS.get(s.key, []),
            "last": last_ran.get(s.key), "history": [f"#{a['id']} {a['summary']} · {a['status']}" for a in mine[-3:]],
        })

    summ = T.expense_summary()
    mem = d["memory"]
    name = next((str(mem[k]) for k in ("name", "user_name", "full_name", "first_name") if mem.get(k)), "")
    pending = [a for a in d["approvals"] if a["status"] == "pending"]
    return {
        "today": date.today().isoformat(), "name": name,
        "events": sorted(d["events"], key=lambda x: (x["date"], x["start"])),
        "reminders": sorted(d["reminders"], key=lambda x: x["due"]),
        "pending": pending,
        "money": {"spent": summ["total"], "budget": summ["budgets"].get("total", 0), "by_category": summ["by_category"],
                  "budgets": summ["budgets"], "warnings": summ["warnings"]},
        "agents": agents, "paused": len(paused), "jobs": jobs, "running": running,
        "activity": _activity(d, jobs),
        "expenses": [{**e, "i": i} for i, e in enumerate(d["expenses"])][-8:][::-1],
        "memory": mem, "lists": d["lists"], "drafts": [{**x, "i": i} for i, x in enumerate(d["drafts"])],
    }


# ---------- DIRECT EDITS (UI buttons; the click itself is the user's consent) ----------

def _del_event(d, b):
    key = (b.get("title"), b.get("date"), b.get("start"))
    for e in d["events"]:
        if (e["title"], e["date"], e["start"]) == key:
            d["events"].remove(e)
            return f"Removed: {e['title']}"
    return "Event pehle hi hat chuka hai."


def _clear_day(d, b):
    n = len(d["events"])
    d["events"] = [e for e in d["events"] if e["date"] != b.get("date")]
    return f"{n - len(d['events'])} event(s) removed."


def _del_reminder(d, b):
    for r in d["reminders"]:
        if (r["text"], r["due"]) == (b.get("text"), b.get("due")):
            d["reminders"].remove(r)
            return f"Reminder removed: {r['text']}"
    return "Reminder pehle hi hat chuka hai."


def _del_expense(d, b):
    i = b.get("i")
    if isinstance(i, int) and 0 <= i < len(d["expenses"]):
        x = d["expenses"][i]
        if (x["amount"], x["category"]) == (b.get("amount"), b.get("category")):
            d["expenses"].pop(i)
            return f"Expense removed: Rs {x['amount']:g} ({x['category']})"
    return "Expense badal chuka hai, page refresh karo."


def _reset_money(d, b):
    msgs = []
    if b.get("expenses"):
        msgs.append(f"{len(d['expenses'])} expenses cleared, spent is now Rs 0")
        d["expenses"] = []
    if b.get("budgets"):
        d["budgets"] = {}
        msgs.append("budgets cleared")
    out = "; ".join(msgs)
    return (out[0].upper() + out[1:]) if out else "Kuch select nahi hua."


def _del_memory(d, b):
    return "Memory deleted." if d["memory"].pop(b.get("key"), None) is not None else "Key nahi mili."


def _del_list(d, b):
    k = str(b.get("list", "")).lower()
    if k not in d["lists"]:
        return "List nahi mili."
    if b.get("item") in (None, ""):
        d["lists"].pop(k)
        return f"List '{k}' removed."
    if b["item"] in d["lists"][k]:
        d["lists"][k].remove(b["item"])
    return f"Removed '{b['item']}'."


def _del_draft(d, b):
    i = b.get("i")
    if isinstance(i, int) and 0 <= i < len(d["drafts"]) and d["drafts"][i].get("subject") == b.get("subject"):
        d["drafts"].pop(i)
        return "Draft deleted."
    return "Draft badal chuka hai, page refresh karo."


EDITS = {
    "/api/events/delete": _del_event, "/api/events/clear_day": _clear_day,
    "/api/reminders/delete": _del_reminder, "/api/expenses/delete": _del_expense,
    "/api/money/reset": _reset_money, "/api/memory/delete": _del_memory,
    "/api/lists/delete": _del_list, "/api/drafts/delete": _del_draft,
}


# ---------- HTTP ----------

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _safe(self):
        """Block DNS-rebinding and cross-site requests: other websites must not be able to approve actions."""
        host = (self.headers.get("Host") or "").split(":")[0]
        origin = self.headers.get("Origin")
        if host not in ("127.0.0.1", "localhost"):
            return False
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
            return False
        return True

    def do_GET(self):
        if not self._safe():
            return self._json({"error": "Forbidden"}, 403)
        path = urlparse(self.path).path
        if path == "/api/state":
            return self._json(build_state())
        if path.startswith("/api/job/"):
            j = get_job(path.rsplit("/", 1)[1])
            return self._json(j) if j else self._json({"error": "Job nahi mili"}, 404)
        if path.startswith("/api/"):
            return self._json({"error": "Not found"}, 404)
        return super().do_GET()

    def do_POST(self):
        if not self._safe() or "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._json({"error": "Forbidden"}, 403)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except Exception:
            return self._json({"error": "Bad JSON"}, 400)
        path = urlparse(self.path).path

        if path == "/api/ask":
            q = str(body.get("q", "")).strip()
            if not q:
                return self._json({"error": "Request khali hai"}, 400)
            jid = start_job(q[:2000])
            if not jid:
                return self._json({"error": "Ek request abhi chal rahi hai. Thoda ruko."}, 409)
            return self._json({"id": jid})

        if path in EDITS:
            return self._json({"message": store.update(lambda d: EDITS[path](d, body))})

        m = re.fullmatch(r"/api/approvals/(\d+)", path)
        if m:
            return self._json({"message": approvals.decide(int(m.group(1)), bool(body.get("approve")))})

        m = re.fullmatch(r"/api/agents/(\w+)/pause", path)
        if m and m.group(1) in REGISTRY and m.group(1) != "chief":
            with JOBS_LOCK:
                busy = _running_job() is not None
            if busy:
                return self._json({"error": "Request chal rahi hai. Khatam hone ke baad pause/resume karo."}, 409)
            key, want = m.group(1), bool(body.get("paused"))
            store.update(lambda d: d["settings"].__setitem__(
                "paused", sorted((set(d["settings"].get("paused", [])) | {key}) if want else (set(d["settings"].get("paused", [])) - {key}))))
            sync_workers()
            return self._json({"ok": True})

        return self._json({"error": "Not found"}, 404)


if __name__ == "__main__":
    sync_workers()
    url = f"http://{HOST}:{PORT}"
    print(f"Ysoriel is ready at {url}")
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        raise SystemExit(f"Port {PORT} busy hai. Purana Ysoriel/streamlit band karo aur dobara chalao.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nYsoriel server stopped.")
