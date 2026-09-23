# 💎 💎 Diamond TopUp BD Bot

Telegram-based Diamond/Coin/Token top-up and balance management system.

## Included
- 18 default applications
- Separate offers per application
- Deposit + Transaction ID verification
- User balance
- Orders
- Admin panel inside Telegram
- Application activation/deactivation
- Offer creation
- User balance adjustment
- Broadcast
- Logs
- SQLite database
- GitHub Actions deployment
- No bot-generated Copy buttons

## GitHub Actions setup

1. Upload these files to your repository.
2. Open **Settings → Secrets and variables → Actions**.
3. Create repository secret `BOT_TOKEN`.
4. Create repository secret `ADMIN_IDS`.
5. `ADMIN_IDS` must be your Telegram numeric User ID, for example `123456789`.
6. Open **Actions → 💎 Diamond TopUp BD → Run workflow**.
7. Keep the workflow running while you want the bot online.

### Important
GitHub Actions is suitable for testing/low-cost running, but it is not designed as a permanent 24/7 hosting service. For a production bot, use a proper always-on server.

## Local run

Python 3.10+:
```bash
pip install -r requirements.txt
export BOT_TOKEN="..."
export ADMIN_IDS="123456789"
python bot.py
```

Never put the real BOT_TOKEN inside `bot.py`, README, screenshots, or public GitHub files.
