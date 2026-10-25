"""NEXUS ko Agentverse + ASI:One se jodta hai (Agent Chat Protocol, mailbox).

Run:  python agent_chat.py
Zaroori: .streamlit/secrets.toml mein  AGENT_SEED = "koi-lamba-random-phrase"
Poora flow ASI:One chat ke andar chalta hai: request -> multi-agent kaam -> approve/reject bhi chat mein.
"""
import asyncio
import os
import re
import tomllib
from datetime import datetime, timezone
from uuid import uuid4

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

import approvals
import orchestrator
import store
from config import BASE


def _secret(name):
    v = os.environ.get(name)
    if v:
        return v
    p = BASE / ".streamlit" / "secrets.toml"
    if p.exists():
        return tomllib.loads(p.read_text(encoding="utf-8")).get(name)
    return None


SEED = _secret("AGENT_SEED")
if not SEED:
    raise SystemExit(
        'AGENT_SEED nahi mila. .streamlit/secrets.toml mein ek line add karo:\n'
        'AGENT_SEED = "koi-lamba-random-phrase-yahan"'
    )

# Python 3.14/3.15 fix: uagents ko ek ready event loop chahiye
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

agent = Agent(
    name="NEXUS Life OS",
    seed=SEED,
    port=8001,
    mailbox=True,
    publish_agent_details=True,
    loop=_loop,
)
protocol = Protocol(spec=chat_protocol_spec)

HELP = (
    "**NEXUS: Personal Life OS** (12 specialised agents + Chief of Staff)\n\n"
    "Kuch bhi likho, jaise:\n"
    "- Next month Goa ka 3 din ka trip plan karo, budget 20k, calendar mein daalo aur dosto ko invite draft karo\n"
    "- Mera monthly budget 15000 hai, aaj 800 ka khana kharch hua\n"
    "- Is hafte mujhe kis cheez pe dhyan dena chahiye?\n\n"
    "Bookings, payments, messages aur deletes **tumhari approval ke bina nahi hote**.\n"
    "Commands: `pending`, `approve N`, `reject N`, `approve all`, `memory`, `help`"
)


def _pending_text():
    p = approvals.pending()
    if not p:
        return "Koi pending approval nahi."
    return "⏳ **Pending approvals:**\n" + "\n".join(
        f"- #{a['id']} [{a['agent']}] {a['summary']}" for a in p
    ) + "\n\nLikho: `approve N` ya `reject N` (ya `approve all`)."


def _command(text):
    """Chat commands. Match na ho toh None (matlab normal request)."""
    t = text.strip().lower().lstrip("/")
    if t in ("help", "hi", "hello", "start"):
        return HELP
    if t in ("pending", "approvals"):
        return _pending_text()
    if t == "memory":
        import json
        mem = store.load()["memory"]
        return "🧠 **Tumhari memory:**\n```\n" + (json.dumps(mem, indent=2, ensure_ascii=False) if mem else "(khaali)") + "\n```"
    m = re.match(r"^(approve|reject)\s+(all|\d+)$", t)
    if m:
        act, which = m.groups()
        ids = [a["id"] for a in approvals.pending()] if which == "all" else [int(which)]
        if not ids:
            return "Koi pending approval nahi."
        out = [f"{'✅' if act == 'approve' else '🚫'} #{i}: {approvals.decide(i, act == 'approve')}" for i in ids]
        return "\n".join(out)
    return None


async def _say(ctx: Context, to: str, text: str):
    """Ek message bhejta hai. Fail ho toh 3 baar retry (same msg_id, taaki duplicate na bane)."""
    mid = uuid4()
    for attempt in range(1, 4):
        try:
            res = await ctx.send(to, ChatMessage(
                timestamp=datetime.now(timezone.utc),
                msg_id=mid,
                content=[TextContent(type="text", text=text)],
            ))
            status = str(getattr(res, "status", res)).lower()
            if "fail" in status:
                ctx.logger.warning(f"⚠ Send fail (try {attempt}/3): {status}")
                await asyncio.sleep(2 * attempt)
                continue
            ctx.logger.info(f"📤 Reply bheja ({len(text)} chars, try {attempt})")
            return
        except Exception:  # noqa
            ctx.logger.exception(f"❌ Send error (try {attempt}/3)")
            await asyncio.sleep(2 * attempt)


@protocol.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    ctx.logger.info(f"📩 Message aaya from {sender[:20]}...")
    try:
        await ctx.send(sender, ChatAcknowledgement(
            timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))
        ctx.logger.info("✔ Ack bhej diya")
    except Exception:  # noqa
        ctx.logger.exception("❌ Ack bhejne mein error")

    text = "".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()
    text = re.sub(r"@agent1[a-z0-9]+", "", text).strip()  # ASI:One @mention hatao
    ctx.logger.info(f"📝 Text: {text[:80]!r}")
    if not text:
        await _say(ctx, sender, HELP)
        return

    try:
        quick = _command(text)
        if quick is not None:
            await _say(ctx, sender, quick)
            return

        trail = []
        answer = await asyncio.to_thread(orchestrator.handle, text, trail.append)

        reply = answer
        if approvals.pending() and "approve" not in answer.lower():
            reply += "\n\n" + _pending_text()
        if trail:
            reply += "\n\n---\n**🔧 Agents ka kaam (trail):**\n" + "\n".join(f"- {x.strip()}" for x in trail)
        await _say(ctx, sender, reply)
    except Exception as e:  # noqa
        ctx.logger.exception("request fail")
        await _say(ctx, sender, f"❌ Kuch gadbad hui: {str(e)[:200]}\nThodi der baad dobara try karo.")


@protocol.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(protocol, publish_manifest=True)


@agent.on_event("startup")
async def hello(ctx: Context):
    ctx.logger.info(f"NEXUS address: {ctx.agent.address}")


if __name__ == "__main__":
    agent.run()
