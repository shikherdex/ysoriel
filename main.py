"""Terminal test. Run: python main.py"""
import json

import approvals
import orchestrator
import store

HELP = "Commands: /pending  /approve N  /reject N  /memory  /help  /quit"


def main():
    print("NEXUS ready.", HELP)
    while True:
        try:
            q = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q == "/quit":
            break
        if q == "/help":
            print(HELP)
        elif q == "/pending":
            p = approvals.pending()
            print("\n".join(f"#{a['id']} [{a['agent']}] {a['summary']}" for a in p) or "Koi pending action nahi.")
        elif q.startswith("/approve ") or q.startswith("/reject "):
            cmd, n = q.split(maxsplit=1)
            print(approvals.decide(int(n), cmd == "/approve"))
        elif q == "/memory":
            print(json.dumps(store.load()["memory"], indent=2, ensure_ascii=False))
        else:
            try:
                print("\n" + orchestrator.handle(q))
            except Exception as e:  # noqa
                print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
