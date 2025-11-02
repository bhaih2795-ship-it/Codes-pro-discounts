# Codes Pro Discounts - Telegram Shop Bot (Production-ready)

This repository contains a secure, environment-configured Telegram bot that sells vouchers, redeem codes, and mobile recharges.
It includes features requested: screenshot forwarding to admin, payment QR generation, and a verification redirect to support.

## Files
- `bot.py` - main bot script
- `requirements.txt` - dependencies
- `.env.example` - example environment file (copy to `.env` and edit)
- `README.md` - this file

## Setup (Replit / Render / Termux / Local)
1. Copy repository to your machine / Replit.
2. Create a `.env` file in project root with values (you can copy from `.env.example`):
```
BOT_TOKEN=YOUR_BOT_TOKEN
OWNER_ID=YOUR_TELEGRAM_ID
SUPPORT_USERNAME=@rcsupportbot
DB_PATH=shop.db
```
3. Install dependencies:
```
pip install -r requirements.txt
```
4. Run the bot:
```
python bot.py
```
### Notes
- Do **not** share your `BOT_TOKEN` publicly. Keep `.env` private.
- If you want to auto-start on Replit, add a run command and keep the repl alive.

