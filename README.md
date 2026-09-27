# Clarity — Telegram group accountability bot

Sits in a Telegram group chat, reads every message, and publicly calls out
deception, unfair terms, pressure/manipulation tactics, and contradictions —
right in the conversation, as they happen. A neutral third party on the
record, so nobody can rewrite history.

It only speaks when something is genuinely off. Everything else gets silence.

DM the bot `/start` once to take control.
DM commands: `/pause`, `/resume`, `/status`.
The bot never responds to commands inside the group.

## Deploy on Render (free)

1. Create a new **Web Service** on Render from this repo
   (or use the `render.yaml` blueprint) — pick the **Free** plan.
   (Background workers are paid-only; a web service works because the bot
   long-polls and just needs to stay awake.)
2. Set these environment variables in the Render dashboard — the keys never
   go through any chat:
   - `TELEGRAM_TOKEN` — bot token from [@BotFather](https://t.me/BotFather)
   - `OPENAI_API_KEY` — from https://platform.openai.com/api-keys
   - `WATCHDOG_MODEL` — optional, defaults to `gpt-4o-mini`
3. Keep it awake: free web services sleep after 15 min with no traffic.
   Add a free monitor at https://uptimerobot.com pointed at
   `https://<your-service>.onrender.com/health` every 5 minutes.
   (One free service running 24/7 fits inside Render's 750 free hours/month.)
4. In [@BotFather](https://t.me/BotFather): `/setprivacy` → pick your bot →
   **Disable**, so it can read all group messages (not just commands).
5. Create your Telegram group, add the other party and the bot. Done —
   Clarity starts watching immediately.

## Rotate exposed keys

If a bot token or API key was ever pasted in a chat, rotate it:
- Telegram: [@BotFather](https://t.me/BotFather) → `/revoke`
- OpenAI: platform.openai.com → API keys → rotate

## How it works

`bot.py` long-polls `getUpdates`, keeps a rolling transcript per chat
(`./data/`, last 60 messages), and sends each new message plus history to
the model. Only messages judged genuinely concerning produce a flag.
State (update offset, transcripts, paused chats) persists across restarts.
