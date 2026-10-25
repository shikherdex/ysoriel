YSORIEL - web UI on the NEXUS agent backend

SETUP (once)
1. Double-click setup.bat   (installs google-genai + requests, then tests your key)
2. Your Gemini key goes in .streamlit\secrets.toml as  GEMINI_API_KEY = "..."
   (or set the GEMINI_API_KEY environment variable). Streamlit itself is no longer needed.

RUN
- Double-click run.bat, or run:  python app.py
- Open http://127.0.0.1:8000  (it also opens automatically)
- run_terminal.bat still starts the old command-line version (main.py).

HOW IT FITS TOGETHER
web/             The UI (index.html, styles.css, app.js). Only this folder is served.
app.py           Local server: serves web/ and a small JSON API (/api/state, /api/ask, ...).
orchestrator.py, agents.py, tools.py, approvals.py, store.py, llm.py   Unchanged NEXUS backend
                 (store.py now also keeps paused agents + mission history, and saves atomically).
data/store.json  All your data (calendar, expenses, memory, approvals, mission history).

NOTES
- Requests run in the background; the UI shows live progress. One request runs at a time.
- Bookings, purchases and messages are simulated: approving logs them, nothing is sent anywhere.
- The server only listens on 127.0.0.1 and rejects requests from other websites.
- Python 3.11+ is required (config.py uses tomllib).
