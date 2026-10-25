"""Approval gate: consequential actions pehle PENDING banate hain, user approve karta hai."""
from datetime import datetime

import store


def request(kind, summary, payload, agent):
    def _f(d):
        for x in d["approvals"]:  # a retry must not create a second identical pending request
            if x["status"] == "pending" and x["kind"] == kind and x["payload"] == payload:
                return x["id"]
        aid = (max([a["id"] for a in d["approvals"]], default=0)) + 1
        d["approvals"].append({
            "id": aid, "kind": kind, "summary": summary, "payload": payload,
            "agent": agent, "status": "pending",
            "created": datetime.now().isoformat(timespec="seconds"),
        })
        return aid
    return store.update(_f)


def pending():
    return [a for a in store.load()["approvals"] if a["status"] == "pending"]


def _execute(a, d):
    k, p = a["kind"], a["payload"]
    if k == "delete_memory":
        existed = d["memory"].pop(p["key"], None) is not None
        return "Memory deleted" if existed else "Key nahi mili"
    if k == "reset_money":
        n = len(d["expenses"])
        d["expenses"] = []
        if p.get("budgets"):
            d["budgets"] = {}
        return f"Money reset: {n} expenses hata diye" + (" aur budgets bhi" if p.get("budgets") else "")
    if k == "send_message":
        d["log"].append({"t": datetime.now().isoformat(timespec="seconds"), "event": "MESSAGE SENT (simulated)", "data": p})
        return f"Message {p.get('to')} ko bhej diya (simulated)"
    if k == "booking":
        d["log"].append({"t": datetime.now().isoformat(timespec="seconds"), "event": "BOOKING CONFIRMED (simulated)", "data": p})
        return f"Booking confirm: {p.get('what')} (simulated)"
    if k == "purchase":
        d["log"].append({"t": datetime.now().isoformat(timespec="seconds"), "event": "PURCHASE DONE (simulated)", "data": p})
        return f"Purchase done: {p.get('item')} (simulated)"
    return "Unknown action"


def decide(aid, approve):
    def _f(d):
        for a in d["approvals"]:
            if a["id"] == aid and a["status"] == "pending":
                if approve:
                    msg = _execute(a, d)
                    a["status"] = "approved"
                else:
                    msg, a["status"] = "Reject kar diya", "rejected"
                return msg
        return "Is ID ka pending action nahi mila"
    return store.update(_f)
