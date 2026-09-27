#!/usr/bin/env python3
"""Clarity — Telegram group watchdog.

Sits in a group chat, reads every message, and flags deception, unfair
terms, pressure/manipulation tactics, and contradictions in real time.
Stays silent unless something is genuinely off.

Config via environment:
  TELEGRAM_TOKEN   Bot token from BotFather (required)
  OPENAI_API_KEY   OpenAI API key for message analysis (required)
  WATCHDOG_MODEL   Model to use (default: gpt-4o-mini)

State (update offset, transcripts, paused chats) lives in ./data/.
Secrets are never written to disk — they come from env only.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("WATCHDOG_MODEL", "gpt-4o-mini")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
OFFSET_FILE = os.path.join(DATA_DIR, "offset.txt")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

SYSTEM_PROMPT = """You are Clarity, a neutral watchdog monitoring a group chat \
where a deal or negotiation is being discussed. Your job: catch deception, \
unfairness, and manipulation in real time.

For the NEW message below, given the conversation history, decide whether it \
contains any of:
- Deception: statements that look false or contradict known facts / earlier messages
- Unfair terms: one-sided demands, hidden costs, shifting goalposts, "take it or leave it" ultimatums that change the deal
- Pressure/manipulation: threats, false urgency, guilt-tripping, gaslighting, love-bombing then switching
- Contradictions: saying the opposite of what the same person said earlier

Respond with ONLY a JSON object, no other text:
{"flag": true/false, "severity": "low|medium|high", "note": "one or two plain sentences explaining exactly what is off and why"}

Be strict: only flag genuinely concerning behavior. Normal disagreement, \
jokes, and small talk get flag=false. When in doubt, do not flag."""

MAX_HISTORY = 60


def tg(method, params=None, timeout=60):
    url = "https://api.telegram.org/bot{}/{}".format(TOKEN, method)
    data = None
    if params:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def openai_analyze(history, new_msg):
    """Ask the model to judge the new message. Returns dict or None on error."""
    transcript = "\n".join(
        "{}: {}".format(m["user"], m["text"]) for m in history[-MAX_HISTORY:]
    )
    user_content = "CONVERSATION HISTORY:\n{}\n\nNEW MESSAGE:\n{}: {}".format(
        transcript if transcript else "(no prior messages)",
        new_msg["user"],
        new_msg["text"],
    )
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": "Bearer " + OPENAI_KEY,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            resp = json.loads(r.read().decode())
        text = resp["choices"][0]["message"]["content"].strip()
        # tolerate code fences
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1] if "\n" in text else ""
            text = text.strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        return json.loads(text)
    except Exception as e:
        print("analysis error: {}".format(e), flush=True)
        return None


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"chats": {}, "paused": []}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


def get_offset():
    try:
        with open(OFFSET_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return 0


def set_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))


def describe_message(msg):
    """Plain-text description of a message for the transcript."""
    if "text" in msg:
        return msg["text"]
    for kind, label in [
        ("photo", "[photo]"), ("video", "[video]"),
        ("voice", "[voice message]"), ("document", "[document]"),
        ("sticker", "[sticker]"), ("location", "[location]"),
        ("contact", "[contact]"),
    ]:
        if kind in msg:
            cap = msg.get("caption", "")
            return "{} {}".format(label, cap).strip()
    return "[non-text message]"


def handle_command(chat_id, text, state, sender):
    cmd = text.split()[0].split("@")[0].lower()
    if cmd == "/pause":
        if chat_id not in state["paused"]:
            state["paused"].append(chat_id)
            save_state(state)
        tg("sendMessage", {"chat_id": chat_id,
                           "text": "⏸️ Watchdog paused by {}. /resume to restart.".format(sender)})
    elif cmd == "/resume":
        if chat_id in state["paused"]:
            state["paused"].remove(chat_id)
            save_state(state)
        tg("sendMessage", {"chat_id": chat_id, "text": "▶️ Watchdog resumed."})
    elif cmd == "/start":
        tg("sendMessage", {"chat_id": chat_id,
                           "text": "I'm Clarity, a watchdog for this chat. "
                                   "I flag deception, unfair terms, and manipulation. "
                                   "I stay quiet unless something looks off. "
                                   "Commands: /pause /resume."})


def main():
    if not TOKEN or not OPENAI_KEY:
        print("TELEGRAM_TOKEN and OPENAI_API_KEY are required", flush=True)
        sys.exit(1)
    me = tg("getMe", timeout=20)["result"]
    bot_id = me["id"]
    print("watchdog live as @{}".format(me.get("username")), flush=True)
    state = load_state()
    offset = get_offset()

    while True:
        try:
            updates = tg("getUpdates", {"offset": offset, "timeout": 50,
                                        "allowed_updates": ["message"]}).get("result", [])
        except Exception as e:
            print("poll error: {}".format(e), flush=True)
            time.sleep(5)
            continue
        for upd in updates:
            offset = upd["update_id"] + 1
            set_offset(offset)
            msg = upd.get("message")
            if not msg:
                continue
            chat = msg.get("chat", {})
            chat_id = chat.get("id")
            chat_type = chat.get("type", "")
            sender = msg.get("from", {})
            if sender.get("is_bot"):
                continue
            name = sender.get("first_name", "Someone")
            if sender.get("username"):
                name += " (@" + sender["username"] + ")"
            text = describe_message(msg)

            if chat_type == "private":
                if text.startswith("/"):
                    handle_command(chat_id, text, state, name)
                else:
                    tg("sendMessage", {"chat_id": chat_id,
                                       "text": "Add me to a group chat and I'll watch it. "
                                               "Commands: /pause /resume."})
                continue

            # group / supergroup
            if text.startswith("/"):
                handle_command(chat_id, text, state, name)
                continue
            if chat_id in state["paused"]:
                continue

            key = str(chat_id)
            history = state["chats"].get(key, [])
            new_msg = {"user": name, "text": text}
            verdict = openai_analyze(history, new_msg)
            history.append(new_msg)
            state["chats"][key] = history[-MAX_HISTORY:]
            save_state(state)

            if verdict and verdict.get("flag"):
                sev = verdict.get("severity", "medium")
                note = verdict.get("note", "Something looks off.")
                icon = {"low": "⚠️", "medium": "🚨", "high": "🚨"}.get(sev, "⚠️")
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": "{} Watchdog flag ({}): {}".format(icon, sev, note),
                })
                print("flagged in {}: {}".format(chat_id, note), flush=True)


if __name__ == "__main__":
    main()
