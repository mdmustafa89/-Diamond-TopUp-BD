import asyncio
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
DB_PATH = os.getenv("DB_PATH", "diamond_coin.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing.")
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS is missing. Example: ADMIN_IDS=123456789")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def money(v):
    return f"৳{Decimal(str(v)):.2f}".replace(".00", "")

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        username TEXT,
        balance TEXT NOT NULL DEFAULT '0',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        logo TEXT,
        category TEXT,
        status TEXT NOT NULL DEFAULT 'active'
    );
    CREATE TABLE IF NOT EXISTS offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_id INTEGER NOT NULL,
        amount TEXT NOT NULL,
        price TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        FOREIGN KEY(app_id) REFERENCES applications(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount TEXT NOT NULL,
        transaction_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        app_id INTEGER NOT NULL,
        offer_id INTEGER NOT NULL,
        target TEXT NOT NULL,
        price TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(app_id) REFERENCES applications(id),
        FOREIGN KEY(offer_id) REFERENCES offers(id)
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        amount TEXT NOT NULL,
        balance_before TEXT NOT NULL,
        balance_after TEXT NOT NULL,
        reference TEXT,
        details TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        target TEXT,
        details TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS broadcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        audience TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    defaults = {
        "bot_name": "💎 💎 Diamond TopUp BD",
        "welcome": "স্বাগতম 💎 Diamond TopUp BD Bot-এ।\\nএখানে Balance Deposit করে বিভিন্ন App-এর Diamond/Coin/Token Top-Up করতে পারবেন।",
        "deposit_number": "01XXXXXXXXX",
        "minimum_deposit": "100",
        "support_username": "",
        "maintenance": "off",
        "ai_enabled": "on",
    }
    for k, v in defaults.items():
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    count = con.execute("SELECT COUNT(*) c FROM applications").fetchone()["c"]
    if count == 0:
        apps = [
            ("⭐ STARMAKER COIN","⭐","Coin"),("💎 IMO DIAMOND","💎","Diamond"),
            ("💎 BIGO LIVE","💎","Diamond"),("💎 CHAMET","💎","Coin"),
            ("💎 POPPO LIVE","💎","Diamond"),("💎 LIKEE DIAMOND","💎","Diamond"),
            ("💎 MICO LIVE","💎","Coin"),("💎 YALLA LIVE","💎","Coin"),
            ("💎 SUGO LITE","💎","Coin"),("💎 TANTAN TOP UP","💎","Top Up"),
            ("💎 4FUN DIAMOND","💎","Diamond"),("💎 MANGO LIVE","💎","Coin"),
            ("💎 MIGO LIVE","💎","Coin"),("💰 TANGO COINS","💰","Coin"),
            ("💰 LIVU COINS","💰","Coin"),("🪙 JAWAKER TOKEN","🪙","Token"),
            ("⭐ PARTY STAR","⭐","Coin"),("💰 FALLA LIVE COIN","💰","Coin")
        ]
        con.executemany("INSERT INTO applications(name,logo,category) VALUES(?,?,?)", apps)
    con.commit(); con.close()

def setting(key):
    con=db(); r=con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone(); con.close()
    return r["value"] if r else ""

def set_setting(key, value):
    con=db(); con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value)); con.commit(); con.close()

def ensure_user(m: Message):
    con=db()
    u=con.execute("SELECT * FROM users WHERE id=?", (m.from_user.id,)).fetchone()
    name=(m.from_user.full_name or "User").strip()
    username=m.from_user.username
    if u:
        con.execute("UPDATE users SET name=?,username=? WHERE id=?", (name,username,m.from_user.id))
    else:
        con.execute("INSERT INTO users(id,name,username,created_at) VALUES(?,?,?,?)",(m.from_user.id,name,username,now()))
    con.commit(); con.close()

def user_row(uid):
    con=db(); r=con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(); con.close(); return r

def add_log(admin_id, action, target="", details=""):
    con=db(); con.execute("INSERT INTO admin_logs(admin_id,action,target,details,created_at) VALUES(?,?,?,?,?)",(admin_id,action,target,details,now())); con.commit(); con.close()

def change_balance(uid, amount, typ, reference="", details=""):
    con=db()
    u=con.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()
    if not u: con.close(); raise ValueError("User not found")
    before=Decimal(u["balance"]); after=before+Decimal(str(amount))
    if after < 0: con.close(); raise ValueError("Insufficient balance")
    con.execute("UPDATE users SET balance=? WHERE id=?", (str(after),uid))
    con.execute("""INSERT INTO transactions(user_id,type,amount,balance_before,balance_after,reference,details,created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",(uid,typ,str(amount),str(before),str(after),reference,details,now()))
    con.commit(); con.close()
    return before, after

def main_kb():
    rows=[]
    con=db()
    apps=con.execute("SELECT * FROM applications WHERE status='active' ORDER BY id").fetchall()
    con.close()
    for i in range(0,len(apps),2):
        row=[]
        for a in apps[i:i+2]:
            row.append(InlineKeyboardButton(text=a["name"],callback_data=f"app:{a['id']}"))
        rows.append(row)
    rows += [
        [InlineKeyboardButton(text="💰 MY BALANCE",callback_data="balance"),
         InlineKeyboardButton(text="➕ DEPOSIT",callback_data="deposit")],
        [InlineKeyboardButton(text="📦 MY ORDERS",callback_data="orders"),
         InlineKeyboardButton(text="🆘 HELP CENTER",callback_data="help")],
        [InlineKeyboardButton(text="👤 MY ACCOUNT",callback_data="account")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 BACK",callback_data="home")]])

def is_admin(uid): return uid in ADMIN_IDS

class OrderStates(StatesGroup):
    target=State(); confirm=State()

class DepositStates(StatesGroup):
    amount=State(); txid=State(); confirm=State()

class AdminStates(StatesGroup):
    add_app=State(); add_offer_app=State(); add_offer_amount=State(); add_offer_price=State()
    balance_uid=State(); balance_amount=State(); broadcast=State()

async def home_message(m: Message, text=None):
    text=text or f"<b>{setting('bot_name')}</b>\\n\\n{setting('welcome')}"
    await m.answer(text, reply_markup=main_kb())

@dp.message(Command("start"))
async def start(m: Message):
    ensure_user(m)
    if setting("maintenance")=="on" and not is_admin(m.from_user.id):
        return await m.answer("🛠️ Bot বর্তমানে Maintenance Mode-এ আছে। পরে আবার চেষ্টা করুন।")
    await home_message(m)

@dp.callback_query(F.data=="home")
async def home(c: CallbackQuery, state:FSMContext):
    await state.clear(); await c.message.edit_text(f"<b>{setting('bot_name')}</b>\\n\\n{setting('welcome')}",reply_markup=main_kb()); await c.answer()

@dp.callback_query(F.data.startswith("app:"))
async def app_offers(c: CallbackQuery):
    aid=int(c.data.split(":")[1]); con=db()
    app=con.execute("SELECT * FROM applications WHERE id=? AND status='active'",(aid,)).fetchone()
    offers=con.execute("SELECT * FROM offers WHERE app_id=? AND status='active' ORDER BY id",(aid,)).fetchall()
    con.close()
    if not app: return await c.answer("Application unavailable.",show_alert=True)
    text=f"<b>{app['name']}</b>\\n\\n"
    if not offers: text+="এখন কোনো Offer available নেই।"
    rows=[]
    for o in offers:
        text += f"💎 {o['amount']} — {money(o['price'])}\\n"
        rows.append([InlineKeyboardButton(text=f"💎 {o['amount']} — {money(o['price'])}",callback_data=f"offer:{o['id']}")])
    rows.append([InlineKeyboardButton(text="🔙 BACK",callback_data="home")])
    await c.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("offer:"))
async def choose_offer(c: CallbackQuery,state:FSMContext):
    oid=int(c.data.split(":")[1]); con=db()
    o=con.execute("SELECT o.*,a.name app FROM offers o JOIN applications a ON a.id=o.app_id WHERE o.id=? AND o.status='active' AND a.status='active'",(oid,)).fetchone()
    con.close()
    if not o: return await c.answer("Offer unavailable.",show_alert=True)
    await state.update_data(offer_id=oid,app_id=o["app_id"],offer_amount=o["amount"],price=o["price"],app=o["app"])
    await state.set_state(OrderStates.target)
    await c.message.answer(f"💎 <b>{o['app']}</b>\\n\\nআপনার এই অ্যাপের প্রয়োজনীয় ID/Number লিখুন:")
    await c.answer()

@dp.message(OrderStates.target)
async def order_target(m: Message,state:FSMContext):
    data=await state.get_data(); u=user_row(m.from_user.id); target=m.text.strip()
    price=Decimal(data["price"]); bal=Decimal(u["balance"])
    if bal < price:
        await state.clear()
        return await m.answer(f"❌ আপনার Balance পর্যাপ্ত নয়।\\n\\n💰 Current Balance: {money(bal)}\\n💵 Required: {money(price)}",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ DEPOSIT",callback_data="deposit")],[InlineKeyboardButton(text="🔙 BACK",callback_data="home")]]))
    await state.update_data(target=target)
    await state.set_state(OrderStates.confirm)
    remaining=bal-price
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ CONFIRM ORDER",callback_data="confirm_order"),
         InlineKeyboardButton(text="❌ CANCEL ORDER",callback_data="cancel_order")]])
    await m.answer(f"""<b>📦 ORDER SUMMARY</b>

📱 Application: {data['app']}
💎 Offer: {data['offer_amount']}
💰 Price: {money(price)}
👤 User ID/Number: {target}
💳 Current Balance: {money(bal)}
💵 Remaining Balance: {money(remaining)}""",reply_markup=kb)

@dp.callback_query(F.data=="cancel_order")
async def cancel_order(c:CallbackQuery,state:FSMContext):
    await state.clear(); await c.message.answer("❌ Order Cancelled.",reply_markup=main_kb()); await c.answer()

@dp.callback_query(F.data=="confirm_order")
async def confirm_order(c:CallbackQuery,state:FSMContext):
    data=await state.get_data(); uid=c.from_user.id
    con=db()
    u=con.execute("SELECT balance,status FROM users WHERE id=?",(uid,)).fetchone()
    if not u or u["status"]!="active": con.close(); return await c.answer("Account is blocked.",show_alert=True)
    price=Decimal(data["price"]); bal=Decimal(u["balance"])
    if bal<price: con.close(); await state.clear(); return await c.answer("Insufficient balance.",show_alert=True)
    newbal=bal-price
    con.execute("UPDATE users SET balance=? WHERE id=?",(str(newbal),uid))
    cur=con.execute("""INSERT INTO orders(user_id,app_id,offer_id,target,price,status,created_at)
                       VALUES(?,?,?,?,?,'pending',?)""",(uid,data["app_id"],data["offer_id"],data["target"],str(price),now()))
    oid=cur.lastrowid
    con.execute("""INSERT INTO transactions(user_id,type,amount,balance_before,balance_after,reference,details,created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",(uid,"order",-price,str(bal),str(newbal),f"ORDER#{oid}",data["app"]))
    con.commit(); con.close(); await state.clear()
    await c.message.answer(f"✅ <b>Order Submitted Successfully</b>\\n\\n📦 Order ID: #{oid}\\n💎 {data['app']} — {data['offer_amount']}\\n💰 Amount: {money(price)}\\n🟡 Status: Pending",reply_markup=main_kb())
    for aid in ADMIN_IDS:
        try: await bot.send_message(aid,f"🔔 <b>NEW ORDER #{oid}</b>\\n\\n📱 {data['app']}\\n💎 {data['offer_amount']}\\n💰 {money(price)}\\n👤 User: {uid}\\n🪪 Target: {data['target']}\\n🟡 Pending")
        except Exception: pass
    await c.answer()

@dp.callback_query(F.data=="balance")
async def balance(c:CallbackQuery):
    u=user_row(c.from_user.id)
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 BUY DIAMOND",callback_data="home")],
        [InlineKeyboardButton(text="➕ DEPOSIT",callback_data="deposit")],
        [InlineKeyboardButton(text="📜 TRANSACTION HISTORY",callback_data="history")],
        [InlineKeyboardButton(text="🔙 BACK",callback_data="home")]])
    await c.message.edit_text(f"<b>💰 MY BALANCE</b>\\n\\nআপনার বর্তমান Balance:\\n<b>{money(u['balance'])}</b>",reply_markup=kb); await c.answer()

@dp.callback_query(F.data=="history")
async def history(c:CallbackQuery):
    con=db(); rows=con.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 20",(c.from_user.id,)).fetchall(); con.close()
    text="<b>📜 TRANSACTION HISTORY</b>\\n\\n"
    if not rows: text+="কোনো Transaction নেই।"
    for r in rows:
        sign="➕" if Decimal(r["amount"])>=0 else "➖"
        text+=f"{sign} {r['type']} — {money(abs(Decimal(r['amount'])))}\\n{r['created_at']}\\nStatus: Recorded\\n\\n"
    await c.message.edit_text(text,reply_markup=back_kb()); await c.answer()

@dp.callback_query(F.data=="deposit")
async def deposit(c:CallbackQuery,state:FSMContext):
    await state.set_state(DepositStates.amount)
    await c.message.answer(f"💰 <b>Deposit করুন</b>\\n\\n📱 Deposit Number: {setting('deposit_number')}\\n💵 Minimum Deposit: {money(setting('minimum_deposit'))}\\n\\nআপনার Deposit Amount লিখুন:")
    await c.answer()

@dp.message(DepositStates.amount)
async def dep_amount(m:Message,state:FSMContext):
    try: amount=Decimal(m.text.strip())
    except: return await m.answer("❌ সঠিক Amount লিখুন।")
    if amount < Decimal(setting("minimum_deposit")): return await m.answer(f"❌ Minimum Deposit {money(setting('minimum_deposit'))}.")
    await state.update_data(amount=str(amount)); await state.set_state(DepositStates.txid)
    await m.answer("আপনার Transaction ID লিখুন:")

@dp.message(DepositStates.txid)
async def dep_txid(m:Message,state:FSMContext):
    tx=m.text.strip()
    con=db(); exists=con.execute("SELECT id FROM deposits WHERE transaction_id=?",(tx,)).fetchone(); con.close()
    if exists: return await m.answer("⚠️ This Transaction ID has already been submitted.")
    await state.update_data(txid=tx); await state.set_state(DepositStates.confirm)
    d=await state.get_data()
    await m.answer(f"<b>Deposit Request Confirmation</b>\\n\\n💵 Amount: {money(d['amount'])}\\n🧾 Transaction ID: {tx}\\n🕐 Time: {now()}",
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ SUBMIT DEPOSIT",callback_data="submit_deposit"),InlineKeyboardButton(text="❌ CANCEL",callback_data="cancel_deposit")]]))

@dp.callback_query(F.data=="cancel_deposit")
async def cancel_deposit(c:CallbackQuery,state:FSMContext):
    await state.clear(); await c.message.answer("❌ Deposit Request Cancelled.",reply_markup=main_kb()); await c.answer()

@dp.callback_query(F.data=="submit_deposit")
async def submit_deposit(c:CallbackQuery,state:FSMContext):
    d=await state.get_data()
    con=db()
    try:
        con.execute("INSERT INTO deposits(user_id,amount,transaction_id,created_at) VALUES(?,?,?,?)",(c.from_user.id,d["amount"],d["txid"],now()))
        did=con.execute("SELECT last_insert_rowid() x").fetchone()["x"]; con.commit()
    except sqlite3.IntegrityError:
        con.close(); await state.clear(); return await c.answer("Transaction ID already submitted.",show_alert=True)
    con.close(); await state.clear()
    await c.message.answer("✅ Deposit Request Submitted\\nআপনার Deposit Admin Verification-এর জন্য পাঠানো হয়েছে।",reply_markup=main_kb())
    for aid in ADMIN_IDS:
        try: await bot.send_message(aid,f"💰 <b>NEW DEPOSIT REQUEST #{did}</b>\\n\\n👤 User: {c.from_user.id}\\n💵 Amount: {money(d['amount'])}\\n🧾 Transaction ID: {d['txid']}\\n🕐 {now()}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ APPROVE",callback_data=f"depapprove:{did}"),InlineKeyboardButton(text="❌ REJECT",callback_data=f"depreject:{did}")]]))
        except Exception: pass
    await c.answer()

@dp.callback_query(F.data.startswith("depapprove:"))
async def depapprove(c:CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("Access Denied",show_alert=True)
    did=int(c.data.split(":")[1]); con=db(); d=con.execute("SELECT * FROM deposits WHERE id=?",(did,)).fetchone()
    if not d or d["status"]!="pending": con.close(); return await c.answer("Already processed.",show_alert=True)
    con.execute("UPDATE deposits SET status='approved' WHERE id=?",(did,)); con.commit(); con.close()
    before,after=change_balance(d["user_id"],Decimal(d["amount"]),"deposit",f"DEPOSIT#{did}","Deposit approved")
    add_log(c.from_user.id,"approve_deposit",str(did),f"user={d['user_id']} amount={d['amount']}")
    await c.message.edit_text(c.message.text+"\\n\\n🟢 APPROVED")
    try: await bot.send_message(d["user_id"],f"✅ <b>Deposit Approved</b>\\n\\nআপনার Balance-এ {money(d['amount'])} যোগ হয়েছে।\\n💰 Current Balance: {money(after)}")
    except Exception: pass
    await c.answer("Approved")

@dp.callback_query(F.data.startswith("depreject:"))
async def depreject(c:CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("Access Denied",show_alert=True)
    did=int(c.data.split(":")[1]); con=db(); d=con.execute("SELECT * FROM deposits WHERE id=?",(did,)).fetchone()
    if not d or d["status"]!="pending": con.close(); return await c.answer("Already processed.",show_alert=True)
    con.execute("UPDATE deposits SET status='rejected' WHERE id=?",(did,)); con.commit(); con.close()
    add_log(c.from_user.id,"reject_deposit",str(did),f"user={d['user_id']}")
    await c.message.edit_text(c.message.text+"\\n\\n🔴 REJECTED")
    try: await bot.send_message(d["user_id"],"❌ Deposit Request Rejected\\nআপনার Deposit Request Admin কর্তৃক Reject করা হয়েছে।")
    except Exception: pass
    await c.answer("Rejected")

@dp.callback_query(F.data=="orders")
async def orders(c:CallbackQuery):
    con=db(); rows=con.execute("""SELECT o.*,a.name app,of.amount offer FROM orders o JOIN applications a ON a.id=o.app_id JOIN offers of ON of.id=o.offer_id WHERE o.user_id=? ORDER BY o.id DESC LIMIT 20""",(c.from_user.id,)).fetchall(); con.close()
    text="<b>📦 MY ORDERS</b>\\n\\n"
    if not rows:text+="কোনো Order নেই।"
    for r in rows: text+=f"#{r['id']}\\n{r['app']} — {r['offer']}\\n💰 {money(r['price'])}\\nStatus: {r['status']}\\n\\n"
    await c.message.edit_text(text,reply_markup=back_kb()); await c.answer()

@dp.callback_query(F.data=="account")
async def account(c:CallbackQuery):
    u=user_row(c.from_user.id); con=db(); total=con.execute("SELECT COUNT(*) c FROM orders WHERE user_id=?",(c.from_user.id,)).fetchone()["c"]; con.close()
    await c.message.edit_text(f"<b>👤 MY ACCOUNT</b>\\n\\n👤 Name: {u['name']}\\n@Username: @{u['username'] or 'N/A'}\\n🆔 Telegram User ID: {u['id']}\\n💰 Current Balance: {money(u['balance'])}\\n📦 Total Orders: {total}\\n🟢 Account Status: {u['status'].title()}",reply_markup=back_kb()); await c.answer()

@dp.callback_query(F.data=="help")
async def help_center(c:CallbackQuery):
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 AI HELP",callback_data="aihelp"),InlineKeyboardButton(text="👤 PERSONAL SUPPORT",callback_data="support")],
        [InlineKeyboardButton(text="💰 DEPOSIT HELP",callback_data="dephelp"),InlineKeyboardButton(text="💎 BUYING GUIDE",callback_data="buyhelp")],
        [InlineKeyboardButton(text="📦 ORDER PROBLEM",callback_data="orderhelp"),InlineKeyboardButton(text="💳 BALANCE PROBLEM",callback_data="balhelp")],
        [InlineKeyboardButton(text="📞 CONTACT ADMIN",callback_data="support")],[InlineKeyboardButton(text="🔙 BACK",callback_data="home")]])
    await c.message.edit_text("<b>🆘 HELP CENTER</b>",reply_markup=kb); await c.answer()

@dp.callback_query(F.data.in_({"aihelp","dephelp","buyhelp","orderhelp","balhelp","support"}))
async def help_item(c:CallbackQuery):
    texts={
    "aihelp":"🤖 AI HELP\\n\\nআমি সাধারণভাবে Bot ব্যবহার, Deposit, Balance ও Order সম্পর্কে সাহায্য করতে পারি। Balance বা Admin Action নিজে পরিবর্তন করতে পারি না।",
    "dephelp":"💰 DEPOSIT HELP\\n\\nDeposit Number-এ টাকা পাঠিয়ে Amount ও Transaction ID Submit করুন। Admin Verify করার পর Balance যোগ হবে।",
    "buyhelp":"💎 BUYING GUIDE\\n\\nApplication → Offer → আপনার ID/Number → Confirm Order। পর্যাপ্ত Balance থাকলে Order Pending হবে।",
    "orderhelp":"📦 ORDER PROBLEM\\n\\nOrder ID দিয়ে Admin/Support-এর সাথে যোগাযোগ করুন।",
    "balhelp":"💳 BALANCE PROBLEM\\n\\nDeposit Approved না হওয়া পর্যন্ত Balance যোগ হবে না। ভুল হলে Support-এ যোগাযোগ করুন.",
    "support":f"👤 PERSONAL SUPPORT\\n\\nSupport: {setting('support_username') or 'Admin-এর সাথে Telegram-এ যোগাযোগ করুন।'}"
    }
    await c.message.edit_text(texts[c.data],reply_markup=back_kb()); await c.answer()

# Admin
@dp.message(Command("admin"))
async def admin(m:Message):
    if not is_admin(m.from_user.id): return await m.answer("❌ Access Denied")
    con=db()
    users=con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    deps=con.execute("SELECT COUNT(*) c FROM deposits WHERE status='approved'").fetchone()["c"]
    pdeps=con.execute("SELECT COUNT(*) c FROM deposits WHERE status='pending'").fetchone()["c"]
    orders=con.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    po=con.execute("SELECT COUNT(*) c FROM orders WHERE status='pending'").fetchone()["c"]
    proc=con.execute("SELECT COUNT(*) c FROM orders WHERE status='processing'").fetchone()["c"]
    done=con.execute("SELECT COUNT(*) c FROM orders WHERE status='completed'").fetchone()["c"]
    canc=con.execute("SELECT COUNT(*) c FROM orders WHERE status='cancelled'").fetchone()["c"]
    con.close()
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Applications",callback_data="adm_apps"),InlineKeyboardButton(text="💎 Offers",callback_data="adm_offers")],
        [InlineKeyboardButton(text="📦 Orders",callback_data="adm_orders"),InlineKeyboardButton(text="💰 Deposits",callback_data="adm_deposits")],
        [InlineKeyboardButton(text="👥 Users",callback_data="adm_users"),InlineKeyboardButton(text="💳 Balance",callback_data="adm_balance")],
        [InlineKeyboardButton(text="📢 Broadcast",callback_data="adm_broadcast"),InlineKeyboardButton(text="⚙️ Settings",callback_data="adm_settings")],
        [InlineKeyboardButton(text="📜 Admin Logs",callback_data="adm_logs")]])
    await m.answer(f"""<b>🔐 ADMIN PANEL</b>

👥 Total Users: {users}
💰 Total Deposits: {deps}
⏳ Pending Deposits: {pdeps}
📦 Total Orders: {orders}
🟡 Pending Orders: {po}
🔵 Processing: {proc}
🟢 Completed: {done}
🔴 Cancelled: {canc}""",reply_markup=kb)

@dp.callback_query(F.data=="adm_apps")
async def adm_apps(c:CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("Access Denied",show_alert=True)
    con=db(); apps=con.execute("SELECT * FROM applications ORDER BY id").fetchall(); con.close()
    rows=[[InlineKeyboardButton(text=f"{a['id']}. {a['name']} [{a['status']}]",callback_data=f"toggleapp:{a['id']}")] for a in apps]
    rows.append([InlineKeyboardButton(text="➕ ADD APPLICATION",callback_data="addapp")])
    rows.append([InlineKeyboardButton(text="🔙 ADMIN",callback_data="adminhome")])
    await c.message.edit_text("📱 <b>Applications Management</b>\\n\\nTap an app to activate/deactivate.",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("toggleapp:"))
async def toggleapp(c:CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("Access Denied",show_alert=True)
    aid=int(c.data.split(":")[1]); con=db(); r=con.execute("SELECT status FROM applications WHERE id=?",(aid,)).fetchone(); new="inactive" if r["status"]=="active" else "active"; con.execute("UPDATE applications SET status=? WHERE id=?",(new,aid)); con.commit(); con.close(); add_log(c.from_user.id,"toggle_application",str(aid),new); await adm_apps(c)

@dp.callback_query(F.data=="addapp")
async def addapp(c:CallbackQuery,state:FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("Access Denied",show_alert=True)
    await state.set_state(AdminStates.add_app); await c.message.answer("নতুন Application-এর Name লিখুন:"); await c.answer()

@dp.message(AdminStates.add_app)
async def addapp_save(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    name=m.text.strip(); con=db()
    try: con.execute("INSERT INTO applications(name,logo,category) VALUES(?,?,?)",(name,"💎","Top Up")); con.commit(); msg="✅ Application Added."
    except sqlite3.IntegrityError: msg="❌ এই নামের Application আগে থেকেই আছে."
    con.close(); await state.clear(); add_log(m.from_user.id,"add_application","",name); await m.answer(msg); await admin(m)

@dp.callback_query(F.data=="adm_offers")
async def adm_offers(c:CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("Access Denied",show_alert=True)
    con=db(); apps=con.execute("SELECT * FROM applications ORDER BY id").fetchall(); con.close()
    rows=[[InlineKeyboardButton(text=a["name"],callback_data=f"offerapp:{a['id']}")] for a in apps]
    rows.append([InlineKeyboardButton(text="🔙 ADMIN",callback_data="adminhome")])
    await c.message.edit_text("💎 <b>Offers Management</b>\\n\\nApplication নির্বাচন করুন:",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("offerapp:"))
async def offerapp(c:CallbackQuery):
    aid=int(c.data.split(":")[1]); con=db(); app=con.execute("SELECT name FROM applications WHERE id=?",(aid,)).fetchone(); os_=con.execute("SELECT * FROM offers WHERE app_id=?",(aid,)).fetchall(); con.close()
    text=f"<b>{app['name']}</b>\\n\\n"
    for o in os_: text+=f"#{o['id']} • {o['amount']} • {money(o['price'])} • {o['status']}\\n"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ ADD OFFER",callback_data=f"addoffer:{aid}")],[InlineKeyboardButton(text="🔙 OFFERS",callback_data="adm_offers")]])
    await c.message.edit_text(text,reply_markup=kb); await c.answer()

@dp.callback_query(F.data.startswith("addoffer:"))
async def addoffer(c:CallbackQuery,state:FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("Access Denied",show_alert=True)
    await state.update_data(add_offer_app=int(c.data.split(":")[1])); await state.set_state(AdminStates.add_offer_amount); await c.message.answer("Diamond/Coin/Token Amount লিখুন:"); await c.answer()

@dp.message(AdminStates.add_offer_amount)
async def addoffer_amount(m:Message,state:FSMContext):
    await state.update_data(add_offer_amount=m.text.strip()); await state.set_state(AdminStates.add_offer_price); await m.answer("Price লিখুন (শুধু সংখ্যা):")

@dp.message(AdminStates.add_offer_price)
async def addoffer_price(m:Message,state:FSMContext):
    try: Decimal(m.text.strip())
    except: return await m.answer("❌ সঠিক Price লিখুন।")
    d=await state.get_data(); con=db(); con.execute("INSERT INTO offers(app_id,amount,price) VALUES(?,?,?)",(d["add_offer_app"],d["add_offer_amount"],m.text.strip())); con.commit(); con.close(); await state.clear(); add_log(m.from_user.id,"add_offer",str(d["add_offer_app"]),d["add_offer_amount"]); await m.answer("✅ Offer Added."); await admin(m)

@dp.callback_query(F.data=="adm_orders")
async def adm_orders(c:CallbackQuery):
    con=db(); rows=con.execute("""SELECT o.*,a.name app,u.name uname FROM orders o JOIN applications a ON a.id=o.app_id JOIN users u ON u.id=o.user_id ORDER BY o.id DESC LIMIT 30""").fetchall(); con.close()
    text="<b>📦 ALL ORDERS</b>\\n\\n"
    for r in rows:text+=f"#{r['id']} • {r['app']} • {money(r['price'])} • {r['status']}\\n👤 {r['user_id']} • {r['target']}\\n\\n"
    await c.message.edit_text(text or "No orders.",reply_markup=back_admin_kb()); await c.answer()

@dp.callback_query(F.data=="adm_deposits")
async def adm_deposits(c:CallbackQuery):
    con=db(); rows=con.execute("SELECT * FROM deposits ORDER BY id DESC LIMIT 30").fetchall(); con.close()
    text="<b>💰 DEPOSITS</b>\\n\\n"
    for r in rows:text+=f"#{r['id']} • User {r['user_id']} • {money(r['amount'])}\\nTX: {r['transaction_id']}\\nStatus: {r['status']}\\n\\n"
    await c.message.edit_text(text or "No deposits.",reply_markup=back_admin_kb()); await c.answer()

def back_admin_kb(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 ADMIN",callback_data="adminhome")]])

@dp.callback_query(F.data=="adm_users")
async def adm_users(c:CallbackQuery):
    con=db(); rows=con.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 30").fetchall(); con.close()
    text="<b>👥 USERS</b>\\n\\n"
    for r in rows:text+=f"👤 {r['name']}\\n🆔 {r['id']}\\n💰 {money(r['balance'])}\\nStatus: {r['status']}\\n\\n"
    await c.message.edit_text(text or "No users.",reply_markup=back_admin_kb()); await c.answer()

@dp.callback_query(F.data=="adm_balance")
async def adm_balance(c:CallbackQuery,state:FSMContext):
    await state.set_state(AdminStates.balance_uid); await c.message.answer("User Telegram ID লিখুন:"); await c.answer()

@dp.message(AdminStates.balance_uid)
async def balance_uid(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    if not m.text.isdigit(): return await m.answer("❌ Telegram User ID সংখ্যা হতে হবে।")
    if not user_row(int(m.text)): return await m.answer("❌ User পাওয়া যায়নি।")
    await state.update_data(uid=int(m.text)); await state.set_state(AdminStates.balance_amount); await m.answer("Balance change লিখুন। উদাহরণ: +500 অথবা -200")

@dp.message(AdminStates.balance_amount)
async def balance_amount(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    try: amount=Decimal(m.text.strip())
    except: return await m.answer("❌ সঠিক Amount দিন।")
    d=await state.get_data()
    try: before,after=change_balance(d["uid"],amount,"admin_adjustment",f"ADMIN:{m.from_user.id}", "Admin balance adjustment")
    except ValueError as e: return await m.answer(f"❌ {e}")
    add_log(m.from_user.id,"balance_adjust",str(d["uid"]),str(amount)); await state.clear(); await m.answer(f"✅ Balance updated.\\nBefore: {money(before)}\\nAfter: {money(after)}"); await admin(m)

@dp.callback_query(F.data=="adm_broadcast")
async def adm_broadcast(c:CallbackQuery,state:FSMContext):
    await state.set_state(AdminStates.broadcast); await c.message.answer("সব Active User-এর জন্য Broadcast Message লিখুন:"); await c.answer()

@dp.message(AdminStates.broadcast)
async def broadcast(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    con=db(); users=con.execute("SELECT id FROM users WHERE status='active'").fetchall(); con.close()
    ok=0
    for u in users:
        try: await bot.send_message(u["id"],m.text); ok+=1
        except: pass
    con=db(); con.execute("INSERT INTO broadcasts(admin_id,audience,message,created_at) VALUES(?,?,?,?)",(m.from_user.id,"active",m.text,now())); con.commit(); con.close()
    add_log(m.from_user.id,"broadcast","active",f"sent={ok}"); await state.clear(); await m.answer(f"📢 Broadcast complete. Sent: {ok}"); await admin(m)

@dp.callback_query(F.data=="adm_settings")
async def adm_settings(c:CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("Access Denied",show_alert=True)
    await c.message.edit_text(f"""<b>⚙️ BOT SETTINGS</b>

Bot Name: {setting('bot_name')}
Deposit Number: {setting('deposit_number')}
Minimum Deposit: {money(setting('minimum_deposit'))}
Support: {setting('support_username') or 'Not set'}
Maintenance: {setting('maintenance')}
AI Help: {setting('ai_enabled')}

এই Starter Version-এ Settings Database-এ রাখা হয়েছে। নিরাপত্তার জন্য Secret তথ্য Environment Variables-এ থাকবে.""",reply_markup=back_admin_kb()); await c.answer()

@dp.callback_query(F.data=="adm_logs")
async def adm_logs(c:CallbackQuery):
    con=db(); rows=con.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT 30").fetchall(); con.close()
    text="<b>📜 ADMIN LOGS</b>\\n\\n"
    for r in rows:text+=f"{r['created_at']}\\nAdmin: {r['admin_id']}\\n{r['action']} • {r['target'] or ''}\\n{r['details'] or ''}\\n\\n"
    await c.message.edit_text(text or "No logs.",reply_markup=back_admin_kb()); await c.answer()

@dp.callback_query(F.data=="adminhome")
async def adminhome(c:CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("Access Denied",show_alert=True)
    await c.message.delete()
    fake=type("M",(),{"from_user":c.from_user,"answer":lambda *args,**kwargs:None})()
    # send compact dashboard directly
    con=db(); u=con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]; o=con.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]; p=con.execute("SELECT COUNT(*) c FROM orders WHERE status='pending'").fetchone()["c"]; d=con.execute("SELECT COUNT(*) c FROM deposits WHERE status='pending'").fetchone()["c"]; con.close()
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Applications",callback_data="adm_apps"),InlineKeyboardButton(text="💎 Offers",callback_data="adm_offers")],
        [InlineKeyboardButton(text="📦 Orders",callback_data="adm_orders"),InlineKeyboardButton(text="💰 Deposits",callback_data="adm_deposits")],
        [InlineKeyboardButton(text="👥 Users",callback_data="adm_users"),InlineKeyboardButton(text="💳 Balance",callback_data="adm_balance")],
        [InlineKeyboardButton(text="📢 Broadcast",callback_data="adm_broadcast"),InlineKeyboardButton(text="⚙️ Settings",callback_data="adm_settings")],
        [InlineKeyboardButton(text="📜 Logs",callback_data="adm_logs")]])
    await c.message.answer(f"<b>🔐 ADMIN PANEL</b>\\n\\n👥 Users: {u}\\n📦 Orders: {o}\\n🟡 Pending Orders: {p}\\n⏳ Pending Deposits: {d}",reply_markup=kb); await c.answer()

@dp.callback_query()
async def unknown_callback(c:CallbackQuery):
    await c.answer("এই অপশনটি এখনো available নয়।",show_alert=True)

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
