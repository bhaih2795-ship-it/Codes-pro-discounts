import os
import logging
import asyncio
import qrcode
import io
import sqlite3
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
)
from dotenv import load_dotenv

# Load environment
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@rcsupportbot")
DB_PATH = os.getenv("DB_PATH", "shop.db")

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database helpers
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(\"\"\"
    CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, created_at TIMESTAMP);
    CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, title TEXT, type TEXT, price REAL, quantity INTEGER, codes TEXT, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, item_id INTEGER, quantity INTEGER, total REAL, status TEXT, txn TEXT, recharge_details TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT);
    \"\"\")
    # ensure owner is admin
    cur.execute("INSERT OR IGNORE INTO admins (id) VALUES (?)", (OWNER_ID,))
    conn.commit()
    conn.close()

def db_execute(query, params=(), fetch=False, commit=False):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall() if fetch else None
    if commit:
        conn.commit()
    conn.close()
    return rows

def get_setting(k):
    r = db_execute("SELECT v FROM settings WHERE k=?", (k,), fetch=True)
    return r[0][0] if r else None

def set_setting(k, v):
    db_execute("INSERT OR REPLACE INTO settings (k,v) VALUES (?,?)", (k,v), commit=True)

# Utilities
def generate_upi_qr(upi_id: str, amount: float = None):
    uri = f"upi://pay?pa={upi_id}&pn=CodesProDiscounts&cu=INR"
    if amount:
        uri += f"&am={amount:.2f}"
    qr = qrcode.QRCode(border=2)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image().convert("RGB")
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def is_admin(uid):
    r = db_execute("SELECT id FROM admins WHERE id=?", (uid,), fetch=True)
    return bool(r)

WELCOME_TEXT = (
    "*✨ Welcome to 💎 Codes Pro Discounts ✨*\n\n"
    "Where savings meet speed — shop smarter every day 💫\n\n"
    "🎁 Explore vouchers, redeem codes, gift cards, and mobile recharges — all at discounted prices.\n\n"
    "💳 *Fast & Secure Payments*  |  🧾 *Instant Delivery*  |  💥 *Trusted by 10,000+ users*\n\n"
    "👇 Tap below to begin your shopping journey 👇"
)

def welcome_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(\"🛍️ Start Shopping\", callback_data=\"open_shop\")],
        [InlineKeyboardButton(\"💬 Support\", url=f\"https://t.me/{SUPPORT_USERNAME.lstrip('@')}\")]
    ])

# Handlers
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        db_execute("INSERT OR IGNORE INTO users (id, username, created_at) VALUES (?,?,datetime('now'))", (user.id, user.username), commit=True)
    await update.message.reply_markdown(WELCOME_TEXT, reply_markup=welcome_keyboard())

# Simple shop opener (categories)
async def open_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query if update.callback_query else None
    cats = db_execute("SELECT id, name FROM categories ORDER BY name", fetch=True)
    if not cats:
        text = \"Shop is empty. Admins can add categories using /admin_addcat\"\n        if q:\n            await q.edit_message_text(text)\n        else:\n            await update.message.reply_text(text)\n        return\n    kb = [[InlineKeyboardButton(name, callback_data=f\"cat_{cid}\")] for cid, name in cats]
    kb.append([InlineKeyboardButton(\"🔄 Refresh\", callback_data=\"open_shop\")])
    if q:\n        await q.edit_message_text(\"*Categories*:\\nChoose one:\", reply_markup=InlineKeyboardMarkup(kb), parse_mode=\"Markdown\")\n    else:\n        await update.message.reply_markdown(\"*Categories*:\\nChoose one:\", reply_markup=InlineKeyboardMarkup(kb))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == \"open_shop\" or data == \"refresh_shop\":\n        await open_shop(update, context)\n        return

    if data.startswith(\"cat_\"):\n        cid = int(data.split(\"_\")[1])\n        items = db_execute(\"SELECT id, title, price, quantity, type FROM items WHERE category_id=? AND active=1\", (cid,), fetch=True)\n        if not items:\n            await q.edit_message_text(\"No items in this category.\")\n            return\n        lines = []\n        kb = []\n        for iid, title, price, qty, itype in items:\n            lines.append(f\"*{title}* — ₹{price:.0f} — _{qty} available_ — `{itype}`\")\n            kb.append([InlineKeyboardButton(f\"Buy {title}\", callback_data=f\"item_{iid}\")])\n        kb.append([InlineKeyboardButton(\"⬅️ Back\", callback_data=\"open_shop\")])\n        await q.edit_message_text(\"\\n\\n\".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode=\"Markdown\")\n        return\n\n    if data.startswith(\"item_\"):\n        iid = int(data.split(\"_\")[1])\n        r = db_execute(\"SELECT title, price, quantity, type FROM items WHERE id=?\", (iid,), fetch=True)\n        if not r:\n            await q.edit_message_text(\"Item not found.\")\n            return\n        title, price, avail, itype = r[0]\n        text = f\"*{title}*\\nPrice: ₹{price:.0f}\\nAvailable: {avail}\\nType: `{itype}`\\n\\nSelect quantity and pay.\"
        kb = [\n            [InlineKeyboardButton(\"➖\", callback_data=f\"dec_{iid}_1\"), InlineKeyboardButton(\"Qty: 1\", callback_data=f\"qty_{iid}_1\"), InlineKeyboardButton(\"➕\", callback_data=f\"inc_{iid}_1\")],\n            [InlineKeyboardButton(\"💳 Confirm & Pay\", callback_data=f\"pay_{iid}_1\")],\n            [InlineKeyboardButton(\"⬅️ Back\", callback_data=\"open_shop\")]\n        ]\n        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=\"Markdown\")\n        return\n\n    if data.startswith((\"inc_\",\"dec_\",\"qty_\",\"pay_\")):\n        parts = data.split(\"_\")\n        action = parts[0]; iid = int(parts[1]); cur_qty = int(parts[2])\n        r = db_execute(\"SELECT title, price, quantity, type FROM items WHERE id=?\", (iid,), fetch=True)\n        if not r:\n            await q.edit_message_text(\"Item not found.\")\n            return\n        title, price, avail, itype = r[0]\n        if action == \"inc\": new_q = min(avail, cur_qty+1)\n        elif action == \"dec\": new_q = max(1, cur_qty-1)\n        elif action == \"qty\": new_q = cur_qty\n        elif action == \"pay\":\n            total = price * cur_qty\n            upi = get_setting(\"payment_upi\") or \"\"\n            text = f\"*PAYMENT DETAILS*\\n\\n*Item:* {title}\\n*Qty:* {cur_qty}\\n*Price/unit:* ₹{price:.0f}\\n*Total:* ₹{total:.0f}\\n\\n*UPI:* `{upi}`\\n\\nScan QR or click Verify to contact support for screenshot verification.\"\n            kb = [[InlineKeyboardButton(\"🔍 Verify Payment (Contact Support)\", url=f\"https://t.me/{SUPPORT_USERNAME.lstrip('@')}\")],[InlineKeyboardButton(\"✅ I Paid\", callback_data=f\"paid_{iid}_{cur_qty}\")],[InlineKeyboardButton(\"❌ Cancel\", callback_data=\"open_shop\")]]\n            qr_bio = None\n            if upi:\n                qr_bio = generate_upi_qr(upi, amount=total)\n            if qr_bio:\n                await q.edit_message_text(\"Preparing payment page...\")\n                await context.bot.send_photo(q.from_user.id, photo=InputFile(qr_bio, filename=\"qr.png\"), caption=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=\"Markdown\")\n                return\n            else:\n                await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=\"Markdown\")\n                return\n        # update qty display\n        text = f\"*{title}*\\nPrice: ₹{price:.0f}\\nAvailable: {avail}\\nType: `{itype}`\\n\\nSelect quantity and pay.\"\n        kb = [[InlineKeyboardButton(\"➖\", callback_data=f\"dec_{iid}_{new_q}\"), InlineKeyboardButton(f\"Qty: {new_q}\", callback_data=f\"qty_{iid}_{new_q}\"), InlineKeyboardButton(\"➕\", callback_data=f\"inc_{iid}_{new_q}\")],[InlineKeyboardButton(\"💳 Confirm & Pay\", callback_data=f\"pay_{iid}_{new_q}\" )],[InlineKeyboardButton(\"⬅️ Back\", callback_data=\"open_shop\")]]\n        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=\"Markdown\")\n        return\n\n    if data.startswith(\"paid_\"):\n        _, iid_s, qty_s = data.split(\"_\")\n        iid = int(iid_s); qty = int(qty_s)\n        # ask for txn id\n        await q.edit_message_text(\"Please send the UPI transaction reference (TXN ID), then send a screenshot of the payment for verification.\")\n        context.user_data['pending_order'] = {'item_id': iid, 'quantity': qty, 'txn': None}\n        return\n\n    if data.startswith((\"admin_confirm_\",\"admin_reject_\",\"admin_done_\")):\n        parts = data.split(\"_\")\n        action = parts[1]; order_id = int(parts[2])\n        uid = update.effective_user.id\n        if not is_admin(uid):\n            await q.answer(\"Not authorized.\", show_alert=True)\n            return\n        order = db_execute(\"SELECT id, user_id, item_id, quantity, total, status FROM orders WHERE id=?\", (order_id,), fetch=True)\n        if not order:\n            await q.answer(\"Order not found.\")\n            return\n        oid, user_id, item_id, qty, total, status = order[0]\n        if action == \"confirm\":\n            # deliver code if voucher\n            item = db_execute(\"SELECT codes, title, type, quantity FROM items WHERE id=?\", (item_id,), fetch=True)[0]\n            codes_field, title, itype, avail = item\n            if itype == 'voucher':\n                codes = [c for c in (codes_field or '').split('||') if c.strip()]\n                if not codes:\n                    await q.answer(\"No codes left.\")\n                    return\n                code = codes.pop(0)\n                new_codes = '||'.join(codes)\n                new_q = max(0, avail-1)\n                db_execute(\"UPDATE items SET codes=?, quantity=? WHERE id=?\", (new_codes, new_q, item_id), commit=True)\n                db_execute(\"UPDATE orders SET status=? WHERE id=?\", (\"delivered\", order_id), commit=True)\n                try:\n                    await context.bot.send_message(user_id, f\"🎉 Your Order #{oid} is confirmed.\\nItem: {title}\\nCode:\\n`{code}`\\nThanks for shopping!\", parse_mode=\"Markdown\")\n                    await q.answer(\"Delivered to user.\")\n                except Exception as e:\n                    await q.answer(f\"Delivery failed: {e}\")\n                return\n            else:\n                db_execute(\"UPDATE orders SET status=? WHERE id=?\", (\"paid\", order_id), commit=True)\n                await context.bot.send_message(user_id, f\"✅ Your recharge Order #{oid} is marked as paid and will be processed by admin.\")\n                await q.answer(\"Marked as paid.\")\n                return\n        if action == \"reject\":\n            db_execute(\"UPDATE orders SET status=? WHERE id=?\", (\"rejected\", order_id), commit=True)\n            await context.bot.send_message(user_id, f\"❌ Your Order #{oid} was rejected. Contact support: https://t.me/{SUPPORT_USERNAME.lstrip('@')}\")\n            await q.answer(\"Rejected and user notified.\")\n            return\n        if action == \"done\":\n            db_execute(\"UPDATE orders SET status=? WHERE id=?\", (\"delivered\", order_id), commit=True)\n            await context.bot.send_message(user_id, f\"✅ Admin has successfully processed your Order #{oid}. Thanks for purchasing at Codes Pro Discounts.\")\n            await q.answer(\"User notified of completion.\")\n            return

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # forward any photo/screenshot to all admins (owner included)
    user = update.effective_user
    file = await update.message.photo[-1].get_file()\n    bio = io.BytesIO()\n    await file.download_to_memory(out=bio)\n    bio.seek(0)\n    admins = db_execute(\"SELECT id FROM admins\", fetch=True)\n    caption = f\"📸 Screenshot from @{user.username or user.full_name} (id: {user.id})\\nTime: {datetime.utcnow().isoformat()}\"\n    for (aid,) in admins:\n        try:\n            await context.bot.send_photo(aid, photo=InputFile(bio, filename=\"screenshot.jpg\"), caption=caption)\n            bio.seek(0)\n        except Exception:\n            pass\n    await update.message.reply_text(\"📸 Screenshot received and sent to admin for verification.\")\n\nasync def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    user = update.effective_user\n    text = update.message.text.strip()\n    pending = context.user_data.get('pending_order')\n    if pending and not pending.get('txn'):\n        # first expected message after I Paid -> treat as TXN\n        pending['txn'] = text\n        # ask for screenshot (user will send photo which gets forwarded)\n        await update.message.reply_text(\"Thanks — TXN recorded. Now please send a screenshot of the payment (or type /cancel to cancel). We will notify admin for verification.\")\n        return\n    # fallback\n    await update.message.reply_text(\"Send /start to open the shop or /help for commands.\")\n\n# Admin commands\nasync def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    if not is_admin(update.effective_user.id):\n        return await update.message.reply_text(\"🚫 You are not an admin.\")\n    kb = [\n        [InlineKeyboardButton(\"➕ Add Category\", callback_data=\"adm_addcat\"), InlineKeyboardButton(\"➕ Add Item (cmd)\", callback_data=\"adm_additem_cmd\")],\n        [InlineKeyboardButton(\"💳 Set UPI (cmd)\", callback_data=\"adm_setupi_cmd\"), InlineKeyboardButton(\"📊 Orders\", callback_data=\"adm_orders\")],\n    ]\n    await update.message.reply_text(\"Admin Panel:\", reply_markup=InlineKeyboardMarkup(kb))\n\nasync def cmd_set_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    if not is_admin(update.effective_user.id):\n        return await update.message.reply_text(\"Not authorized.\")\n    if not context.args:\n        return await update.message.reply_text(\"Usage: /set_payment yourupi@bank\")\n    upi = context.args[0]\n    set_setting('payment_upi', upi)\n    # generate and send QR\n    bio = generate_upi_qr(upi)\n    await update.message.reply_photo(photo=InputFile(bio, filename='upi_qr.png'), caption=f\"✅ UPI set to: <code>{upi}</code>\", parse_mode='HTML')\n\nasync def cmd_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    if not is_admin(update.effective_user.id):\n        return await update.message.reply_text(\"Not authorized.\")\n    name = \" \".join(context.args).strip()\n    if not name:\n        return await update.message.reply_text(\"Usage: /admin_addcat <name>\")\n    db_execute(\"INSERT INTO categories (name) VALUES (?)\", (name,), commit=True)\n    await update.message.reply_text(f\"Category '{name}' added.\")\n\nasync def cmd_add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    # usage: /admin_additem Title | category | type | price | qty | code1||code2\n    if not is_admin(update.effective_user.id):\n        return await update.message.reply_text(\"Not authorized.\")\n    text = update.message.text.partition(' ')[2]\n    parts = [p.strip() for p in text.split('|')]\n    if len(parts) < 5:\n        return await update.message.reply_text(\"Usage: /admin_additem Title | category | type(recharge/voucher) | price | qty | codes(optional)\")\n    title, category_name, itype, price, qty = parts[:5]\n    codes = parts[5] if len(parts)>5 else ''\n    cat = db_execute(\"SELECT id FROM categories WHERE name=?\", (category_name,), fetch=True)\n    if not cat:\n        return await update.message.reply_text(\"Category not found. Add it with /admin_addcat\")\n    cid = cat[0][0]\n    db_execute(\"INSERT INTO items (category_id, title, type, price, quantity, codes) VALUES (?,?,?,?,?,?)\", (cid, title, itype.lower(), float(price), int(qty), codes), commit=True)\n    await update.message.reply_text(f\"Item '{title}' added under '{category_name}'.\")\n\n# Setup and run\ndef main():\n    init_db()\n    app = Application.builder().token(BOT_TOKEN).build()\n\n    app.add_handler(CommandHandler('start', start_cmd))\n    app.add_handler(CallbackQueryHandler(callback_handler))\n    app.add_handler(CommandHandler('admin', cmd_admin))\n    app.add_handler(CommandHandler('set_payment', cmd_set_payment))\n    app.add_handler(CommandHandler('admin_addcat', cmd_add_category))\n    app.add_handler(CommandHandler('admin_additem', cmd_add_item))\n\n    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))\n    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))\n\n    logger.info('Bot starting...')\n    app.run_polling()\n\nif __name__ == '__main__':\n    main()\n