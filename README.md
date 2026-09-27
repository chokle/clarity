# Clarity — Telegram group watchdog

Sits in a Telegram group chat, reads every message, and flags deception,
unfair terms, pressure/manipulation tactics, and contradictions in real time.
Stays silent unless something is genuinely off. Flags are posted publicly
in the group so everyone sees them.

Commands in the group: `/pause`, `/resume`.

## Deploy on Render

1. Create a new **Background Worker** on Render from this repo
   (or use the `render.yaml` blueprint).
2. Set these environment variables in the Render dashboard — the keys never
   go through any chat:
   - `TELEGRAM_TOKEN` — bot token from [@BotFather](https://t.me/BotFather)
   - `OPENAI_API_KEY` — from https://platform.openai.com/api-keys
   - `WATCHDOG_MODEL` — optional, defaults to `gpt-4o-mini`
3. In [@BotFather](https://t.me/BotFather): `/setprivacy` → pick your bot →
   **Disable**, so it can read all group messages (not just commands).
4. Create your Telegram group, add the other party and the bot. Done —
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
