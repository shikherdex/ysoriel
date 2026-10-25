"""Shared, user-controlled memory + data. Ek hi JSON file (data/store.json)."""
import json
import os
import threading

from config import DATA

_lock = threading.RLock()
FILE = DATA / "store.json"
DEFAULT = {
    "memory": {}, "expenses": [], "budgets": {}, "events": [], "reminders": [],
    "lists": {}, "drafts": [], "approvals": [], "log": [],
    "settings": {}, "jobs": [],
}


def load():
    with _lock:
        d = {}
        if FILE.exists():
            try:
                d = json.loads(FILE.read_text(encoding="utf-8"))
            except Exception:
                d = {}
        for k, v in DEFAULT.items():
            d.setdefault(k, type(v)())
        return d


def save(d):
    with _lock:
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, FILE)


def update(fn):
    with _lock:
        d = load()
        r = fn(d)
        save(d)
        return r
