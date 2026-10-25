"""Chief of Staff: plan -> parallel execute (dependency waves) -> verify+combine."""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import approvals
import llm
import store
from agents import REGISTRY

WORKERS = {k: a for k, a in REGISTRY.items() if k != "chief"}


def _agent_list():
    return "\n".join(f"- {k}: {a.spec.role}" for k, a in WORKERS.items())


def plan(request: str) -> list:
    mem = store.load()["memory"]
    prompt = f"""Aaj: {datetime.now().strftime('%Y-%m-%d (%A)')}
User memory: {json.dumps(mem, ensure_ascii=False)}
User request: {request}

Available agents:
{_agent_list()}

Request ko chhote tasks mein todo. Sirf zaroori agents lo (simple request = 1-2 tasks). Jo tasks independent hain unki depends_on khaali rakho (wo parallel chalenge).
Jab ek task ko dusre ka output chahiye (jaise itinerary ke baad calendar/invite), depends_on mein uska id do.
Har task mein poori detail do (dates, budget, city), kyunki agent ko sirf task text milega.
JSON do: {{"tasks":[{{"id":"t1","agent":"<key>","task":"...","depends_on":[]}}]}}"""
    data = llm.ask_json(prompt)
    tasks, ids = [], set()
    for t in data.get("tasks", []):
        if t.get("agent") in WORKERS and t.get("task"):
            t["id"] = str(t.get("id") or f"t{len(tasks)+1}")
            t["depends_on"] = [str(x) for x in t.get("depends_on", [])]
            tasks.append(t)
            ids.add(t["id"])
    for t in tasks:
        t["depends_on"] = [d for d in t["depends_on"] if d in ids and d != t["id"]]
    return tasks


def execute(tasks, progress=print):
    done, remaining = {}, {t["id"]: t for t in tasks}
    while remaining:
        ready = [t for t in remaining.values() if all(d in done for d in t["depends_on"])]
        if not ready:  # cycle safety
            ready = list(remaining.values())
        progress(f"▶ Wave: {', '.join(t['agent'] for t in ready)} (parallel)")

        def run_one(t):
            ctx = "\n\n".join(f"[{done[d].agent}] {done[d].output}" for d in t["depends_on"] if d in done)
            return t, WORKERS[t["agent"]].run(t["task"], ctx)

        with ThreadPoolExecutor(max_workers=4) as ex:
            for f in as_completed([ex.submit(run_one, t) for t in ready]):
                t, r = f.result()
                done[t["id"]] = r
                remaining.pop(t["id"], None)
                progress(f"{'✅' if r.ok else '❌'} {t['agent']} ({r.seconds:.1f}s)")
    return done


def _pending_text():
    p = approvals.pending()
    if not p:
        return ""
    lines = "\n".join(f"  #{a['id']} {a['summary']}" for a in p)
    return f"\n\n⏳ Approval ka wait ({len(p)}): /approve N ya /reject N\n{lines}"


def verify_and_compose(request, results):
    body = "\n\n".join(f"[{r.agent}] {r.output}" for r in results.values())
    pend = [{"id": a["id"], "summary": a["summary"]} for a in approvals.pending()]
    prompt = f"""User request: {request}

Agents ka kaam:
{body}

Pending approvals: {json.dumps(pend, ensure_ascii=False)}

Pehle verify karo: outputs request poori karte hain? Contradiction (budget, dates, numbers)? Koi agent ERROR de gaya? Koi action claim hua jo asal mein approval-pending hai?
Phir user ki bhasha mein ek clear final jawab likho (kya ho gaya, plan/numbers, kya approval ka wait kar raha hai). Lamba mat khicho.
JSON do: {{"ok": true/false, "issues": ["..."], "final": "..."}}"""
    try:
        data = llm.ask_json(prompt)
        final = data.get("final", "")
        if data.get("ok", True):
            return final + "\n\n✅ Verified: outputs consistent hain."
        return final + "\n\n⚠️ Verification notes:\n" + "\n".join(f"- {i}" for i in data.get("issues", []))
    except Exception as e:  # noqa
        return "Combine nahi ho paya, agents ka raw output:\n\n" + body + f"\n\n(error: {e})"


def handle(request: str, progress=print) -> str:
    progress("🧠 Chief of Staff plan bana raha hai...")
    tasks = plan(request)
    if not tasks:
        return "Plan nahi ban paya. Request thodi aur clearly likho."
    for t in tasks:
        dep = f" (after {','.join(t['depends_on'])})" if t["depends_on"] else ""
        progress(f"  • {t['id']} → {t['agent']}{dep}")
    results = execute(tasks, progress)
    if len(tasks) == 1:  # simple request: extra LLM calls skip
        r = next(iter(results.values()))
        return r.output + _pending_text()
    progress("🔎 Verify + final jawab...")
    return verify_and_compose(request, results)
