# 💎 Diamond TopUp BD Bot Database

SQLite database: `diamond_coin.db`

Tables:
- users
- applications
- offers
- deposits
- orders
- transactions
- admin_logs
- broadcasts
- settings

Important rules:
- Deposit adds balance only after admin approval.
- Order price is deducted once when confirmed.
- Transaction ID is UNIQUE.
- Admin access uses Telegram User ID from ADMIN_IDS.
- Secrets are not stored in source code.
- The bot does not create Copy buttons.
