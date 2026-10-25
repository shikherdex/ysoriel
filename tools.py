"""Real tools jo agents call karte hain. Docstrings + type hints zaroori hain (Gemini inhe padhta hai)."""
from datetime import datetime, timedelta

import requests

import approvals
import llm
import store


# ---------- Memory ----------
def memory_get() -> dict:
    """User ki saved preferences, goals, routines, past decisions return karta hai."""
    return store.load()["memory"]


def memory_set(key: str, value: str) -> str:
    """User ki koi preference/goal/routine/decision memory mein save karo (key short snake_case)."""
    store.update(lambda d: d["memory"].__setitem__(key, value))
    return f"Saved: {key} = {value}"


def request_delete_memory(key: str) -> str:
    """Memory entry delete karne ki request. User approval ke baad hi delete hoga."""
    aid = approvals.request("delete_memory", f"Memory delete: {key}", {"key": key}, "memory")
    return f"PENDING APPROVAL #{aid}: delete memory '{key}'. Abhi delete nahi hua."


# ---------- Calendar / reminders ----------
def _parse(date, time_):
    return datetime.strptime(f"{date} {time_}", "%Y-%m-%d %H:%M")


def add_event(title: str, date: str, start_time: str, duration_min: int = 60) -> str:
    """Calendar mein event add karo. date=YYYY-MM-DD, start_time=HH:MM (24h). Conflict ho toh add nahi hota."""
    try:
        s = _parse(date, start_time)
    except ValueError:
        return "ERROR: date YYYY-MM-DD aur time HH:MM format mein do."
    e = s + timedelta(minutes=duration_min)

    def _f(d):
        for ev in d["events"]:
            if (ev["title"], ev["date"], ev["start"], ev["duration"]) == (title, date, start_time, duration_min):
                return f"Already in calendar: {title} on {date} {start_time} (duplicate ignored)"
        for ev in d["events"]:
            es = _parse(ev["date"], ev["start"])
            ee = es + timedelta(minutes=ev["duration"])
            if s < ee and es < e:
                return f"CONFLICT with '{ev['title']}' ({ev['date']} {ev['start']}). Event add nahi hua, dusra time suggest karo."
        d["events"].append({"title": title, "date": date, "start": start_time, "duration": duration_min})
        return f"Event added: {title} on {date} {start_time} ({duration_min} min)"
    return store.update(_f)


def list_events() -> list:
    """Saare calendar events (date order mein)."""
    return sorted(store.load()["events"], key=lambda x: (x["date"], x["start"]))


def remove_event(title: str = "", date: str = "", start_time: str = "") -> str:
    """Calendar se ek event hatao. title (chhota hissa chalega), date (YYYY-MM-DD) ya start_time (HH:MM, 24h) mein se kam se kam ek do. Kai match hon toh hataata nahi, list batata hai."""
    tl = title.strip().lower()
    if not (tl or date or start_time):
        return "ERROR: title, date ya start_time mein se kuch to do."

    def _f(d):
        hits = [e for e in d["events"]
                if (not tl or tl in e["title"].lower()) and (not date or e["date"] == date)
                and (not start_time or e["start"] == start_time)]
        if not hits:
            return "Koi matching event nahi mila."
        if len(hits) > 1:
            return "Kai events match hue, kaunsa hataun? " + "; ".join(f"{e['title']} {e['date']} {e['start']}" for e in hits)
        d["events"].remove(hits[0])
        return f"Event removed: {hits[0]['title']} ({hits[0]['date']} {hits[0]['start']})"
    return store.update(_f)


def add_reminder(text: str, due_date: str) -> str:
    """Reminder/deadline add karo. due_date=YYYY-MM-DD."""
    def _f(d):
        if any(r["text"] == text and r["due"] == due_date for r in d["reminders"]):
            return f"Reminder already set: {text} (due {due_date})"
        d["reminders"].append({"text": text, "due": due_date, "done": False})
        return f"Reminder set: {text} (due {due_date})"
    return store.update(_f)


def remove_reminder(text: str, due_date: str = "") -> str:
    """Ek reminder hatao. text ka chhota hissa chalega; due_date (YYYY-MM-DD) optional. Kai match hon toh list batata hai."""
    tl = text.strip().lower()

    def _f(d):
        hits = [r for r in d["reminders"] if tl and tl in r["text"].lower() and (not due_date or r["due"] == due_date)]
        if not hits:
            return "Koi matching reminder nahi mila."
        if len(hits) > 1:
            return "Kai reminders match hue, kaunsa hataun? " + "; ".join(f"{r['text']} ({r['due']})" for r in hits)
        d["reminders"].remove(hits[0])
        return f"Reminder removed: {hits[0]['text']}"
    return store.update(_f)


def list_reminders() -> list:
    """Saare reminders/deadlines."""
    return store.load()["reminders"]


# ---------- Finance ----------
def add_expense(amount: float, category: str, note: str = "") -> str:
    """Expense record karo (INR). category: food, travel, shopping, bills, health, other."""
    now = datetime.now()

    def _f(d):
        for x in reversed(d["expenses"][-5:]):
            if (x["amount"], x["category"], x["note"]) == (amount, category.lower(), note) and x.get("ts") \
                    and (now - datetime.fromisoformat(x["ts"])).total_seconds() < 120:
                return f"Expense already saved: Rs {amount} ({category}) (duplicate ignored)"
        d["expenses"].append({"amount": amount, "category": category.lower(), "note": note,
                              "date": now.strftime("%Y-%m-%d"), "ts": now.isoformat(timespec="seconds")})
        return f"Expense saved: Rs {amount} ({category})"
    return store.update(_f)


def request_reset_money(also_budgets: bool = False) -> str:
    """Saare expenses (spent ko 0) hatane ki request; also_budgets=True ho toh budgets bhi. User approval ke baad hi hoga."""
    what = "all expenses + budgets" if also_budgets else "all expenses (spent -> 0)"
    aid = approvals.request("reset_money", f"Reset money: {what}", {"budgets": also_budgets}, "finance")
    return f"PENDING APPROVAL #{aid}: reset money ({what}). Abhi kuch delete nahi hua."


def set_budget(category: str, amount: float) -> str:
    """Category ka monthly budget set karo (INR). category 'total' bhi ho sakta hai."""
    store.update(lambda d: d["budgets"].__setitem__(category.lower(), amount))
    return f"Budget set: {category} = Rs {amount}"


def expense_summary() -> dict:
    """Category-wise kharcha, budgets, aur overspending warnings."""
    d = store.load()
    tot, by = 0.0, {}
    for x in d["expenses"]:
        by[x["category"]] = by.get(x["category"], 0) + x["amount"]
        tot += x["amount"]
    warn = []
    for c, b in d["budgets"].items():
        spent = tot if c == "total" else by.get(c, 0)
        if spent > b:
            warn.append(f"{c}: Rs {spent} > budget Rs {b}")
        elif b and spent > 0.8 * b:
            warn.append(f"{c}: 80% budget use ho gaya (Rs {spent}/{b})")
    return {"total": tot, "by_category": by, "budgets": d["budgets"], "warnings": warn}


# ---------- Home ----------
def add_list_item(list_name: str, item: str) -> str:
    """Kisi list (grocery, chores, repairs) mein item add karo."""
    store.update(lambda d: d["lists"].setdefault(list_name.lower(), []).append(item))
    return f"Added '{item}' to {list_name}"


def remove_list_item(list_name: str, item: str = "") -> str:
    """List se ek item hatao; item khali ho toh poori list hat jaati hai."""
    def _f(d):
        k = list_name.lower()
        if k not in d["lists"]:
            return f"List '{list_name}' nahi mili."
        if not item:
            d["lists"].pop(k)
            return f"List removed: {list_name}"
        for x in d["lists"][k]:
            if x.lower() == item.lower():
                d["lists"][k].remove(x)
                return f"Removed '{x}' from {list_name}"
        return f"'{item}' list mein nahi mila."
    return store.update(_f)


def get_lists() -> dict:
    """Saari lists (grocery, chores, ...)."""
    return store.load()["lists"]


# ---------- Communication (draft free, send = approval) ----------
def save_draft(to: str, subject: str, body: str) -> str:
    """Email/message ka draft save karo. Ye bhejta nahi hai."""
    store.update(lambda d: d["drafts"].append({"to": to, "subject": subject, "body": body}))
    return f"Draft saved for {to}: {subject}"


def request_send_message(to: str, subject: str, body: str) -> str:
    """Message/email bhejne ki request. User approval ke baad hi jayega."""
    aid = approvals.request("send_message", f"Send to {to}: {subject}",
                            {"to": to, "subject": subject, "body": body}, "communication")
    return f"PENDING APPROVAL #{aid}: message to {to}. Abhi bheja nahi gaya."


# ---------- Bookings / purchases (approval-gated) ----------
def request_booking(what: str, details: str, estimated_cost_inr: float) -> str:
    """Hotel/transport/appointment booking ki request. Approval ke baad hi confirm hoga."""
    aid = approvals.request("booking", f"Book: {what} (~Rs {estimated_cost_inr})",
                            {"what": what, "details": details, "cost": estimated_cost_inr}, "travel")
    return f"PENDING APPROVAL #{aid}: booking '{what}'. Abhi book nahi hua."


def request_purchase(item: str, price_inr: float, store_name: str) -> str:
    """Kuch kharidne ki request. Payment approval ke baad hi hoga."""
    aid = approvals.request("purchase", f"Buy: {item} @ Rs {price_inr} ({store_name})",
                            {"item": item, "price": price_inr, "store": store_name}, "shopping")
    return f"PENDING APPROVAL #{aid}: purchase '{item}'. Abhi payment nahi hua."


# ---------- Real-world data ----------
def web_search(query: str) -> str:
    """Web par current info search karo (hotels, prices, jobs, reviews, news). Short summary return karta hai."""
    try:
        return llm.ask(f"Search karke concise, factual jawab do (sources/prices ke saath jahan ho): {query}", grounded=True)
    except Exception as e:  # noqa
        return f"ERROR: web search fail hua ({e})"


def get_weather(city: str) -> str:
    """Kisi city ka current weather + aaj ka forecast (Open-Meteo)."""
    try:
        g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": city, "count": 1}, timeout=10).json()
        if not g.get("results"):
            return f"City '{city}' nahi mili."
        r = g["results"][0]
        w = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": r["latitude"], "longitude": r["longitude"],
            "current": "temperature_2m,precipitation,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum", "timezone": "auto",
            "forecast_days": 3}, timeout=10).json()
        return f"{r['name']}: abhi {w['current']['temperature_2m']}C, daily max/min {w['daily']['temperature_2m_max']}/{w['daily']['temperature_2m_min']}, rain mm {w['daily']['precipitation_sum']}"
    except Exception as e:  # noqa
        return f"ERROR: weather fail ({e})"
