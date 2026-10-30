# ==========================================================
#   SHADOW EMIS BOT  |  Flask + Telegram Bot
#   Run (dev):    python bot.py
#   Run (prod):   gunicorn -w 1 -b 0.0.0.0:8080 bot:app
# ==========================================================

import json
import logging
import os
import threading
import urllib3

import requests
import telebot
from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from flask import Flask, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================================
#                   ⚙️  CONFIG  ⚙️
# ==========================================================
BOT_TOKEN       = os.getenv("BOT_TOKEN", "9136606066:AAFsVTCnzU7BymxzpEMItl8U8AMK49Xj8Sc")
OWNER_USERNAME  = os.getenv("@King_X_vau", "ShadowOwner")
BOT_NAME        = os.getenv("BOT_NAME", "Shadow")

HEAD_URL  = "https://apps.emis.gov.bd:9701/api/public/hrm/emp-info/get-head-by-institute-id/0/{eiin}/0"
LIST_URL  = "https://apps.emis.gov.bd:9701/api/public/hrm/emp-info/get-pageable-emp-list-by-institute"
IMAGE_URL = "https://apps.emis.gov.bd:9701/api/public/hrm/file/view/{emp_id}/{file_name}/10"
REQUEST_TIMEOUT = 30

PORT = int(os.getenv("PORT", 8080))

# ==========================================================
#                   🪵  LOGGING
# ==========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(BOT_NAME)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==========================================================
#                   🌐  FLASK APP
# ==========================================================
app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({
        "status": True,
        "bot": BOT_NAME,
        "owner": f"@{OWNER_USERNAME}",
        "message": f"{BOT_NAME} EMIS Bot is running ✅",
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

# ==========================================================
#                   🌐  HEADERS
# ==========================================================
COMMON_HEADERS = {
    "Host": "apps.emis.gov.bd:9701",
    "Connection": "keep-alive",
    "sec-ch-ua-platform": '"Android"',
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "sec-ch-ua": '"Chromium";v="154", "Android WebView";v="154", "Not A(Brand";v="99"',
    "sec-ch-ua-mobile": "?1",
    "Origin": "https://apps.emis.gov.bd",
    "X-Requested-With": "com.xbrowser.play",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://apps.emis.gov.bd/",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
}

# ==========================================================
#                   🛠️  HELPERS
# ==========================================================
def build_image_url(old_path: str, emp_id) -> str:
    if not old_path or not emp_id:
        return old_path or ""
    file_name = old_path.split("/")[-1]
    return IMAGE_URL.format(emp_id=emp_id, file_name=file_name)


def fix_images(items: list):
    for it in items:
        img = it.get("image")
        if img:
            emp_id = it.get("id") or it.get("empRefId")
            it["image"] = build_image_url(img, emp_id)
    return items


def esc(s) -> str:
    if s is None:
        return "N/A"
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ==========================================================
#                   📡  EMIS FETCH
# ==========================================================
def fetch_head(eiin: str) -> dict:
    r = requests.get(
        HEAD_URL.format(eiin=eiin),
        headers=COMMON_HEADERS, timeout=REQUEST_TIMEOUT, verify=False,
    )
    r.raise_for_status()
    data = r.json()
    if isinstance(data.get("data"), list):
        fix_images(data["data"])
    return data


def fetch_employees(eiin: str) -> dict:
    body = {
        "listIntParam1": [],
        "page": 0,
        "size": 1000,
        "searchValue": "",
        "intParam1": None,
        "intParam2": 1,
        "stringParam1": eiin,
    }
    headers = {**COMMON_HEADERS, "Content-Type": "application/json"}
    r = requests.put(
        LIST_URL, headers=headers, data=json.dumps(body),
        timeout=REQUEST_TIMEOUT, verify=False,
    )
    r.raise_for_status()
    data = r.json()
    content = data.get("data", {}).get("content")
    if isinstance(content, list):
        fix_images(content)
    return data


# ==========================================================
#                   ⌨️  KEYBOARDS
# ==========================================================
def main_reply_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("🔍 EIIN দিয়ে সার্চ"),
        KeyboardButton("ℹ️ Help"),
    )
    kb.add(
        KeyboardButton("👤 Owner"),
        KeyboardButton("📊 Bot Status"),
    )
    return kb


def inline_after_search(eiin: str):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("👨‍🏫 শুধু হেড লিস্ট", callback_data=f"head|{eiin}"),
        InlineKeyboardButton("👥 শুধু এমপ্লয়ি লিস্ট", callback_data=f"emp|{eiin}"),
    )
    kb.add(
        InlineKeyboardButton("🔄 আবার সব দেখাও", callback_data=f"all|{eiin}"),
        InlineKeyboardButton("❌ বন্ধ করো", callback_data="close"),
    )
    return kb


def owner_inline():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        f"💬 {OWNER_USERNAME}",
        url=f"https://t.me/{OWNER_USERNAME}"
    ))
    return kb


# ==========================================================
#                   🧾  FORMATTERS
# ==========================================================
def format_head(data: dict) -> str:
    arr = data.get("data") or []
    if not arr:
        return "❌ <b>কোনো হেড তথ্য পাওয়া যায়নি।</b>"
    out = [f"👨‍🏫 <b>হেড / ভাইস-প্রিন্সিপাল তথ্য</b> (মোট: {len(arr)})\n"]
    for i, h in enumerate(arr, 1):
        out.append(
            f"<b>{i}. {esc(h.get('name'))}</b>\n"
            f"   🆔 ID: <code>{esc(h.get('id') or h.get('empRefId'))}</code>\n"
            f"   🏷️ পদ: {esc(h.get('designationName') or h.get('designation'))}\n"
            f"   📱 মোবাইল: {esc(h.get('mobile') or h.get('phone'))}\n"
            f"   🖼️ ছবি: {esc(h.get('image'))}\n"
        )
    return "\n".join(out)


def format_employees(data: dict) -> str:
    content = (data.get("data") or {}).get("content") or []
    total   = (data.get("data") or {}).get("totalElements", len(content))
    if not content:
        return "❌ <b>কোনো এমপ্লয়ি পাওয়া যায়নি।</b>"

    out = [f"👥 <b>কর্মচারী তালিকা</b> (দেখানো: {len(content)} / মোট: {total})\n"]
    for i, e in enumerate(content, 1):
        out.append(
            f"<b>{i}. {esc(e.get('name'))}</b>\n"
            f"   🆔 ID: <code>{esc(e.get('id') or e.get('empRefId'))}</code>\n"
            f"   🏷️ পদ: {esc(e.get('designationName') or e.get('designation'))}\n"
            f"   📱 মোবাইল: {esc(e.get('mobile') or e.get('phone'))}\n"
            f"   🖼️ ছবি: {esc(e.get('image'))}\n"
        )
    text = "\n".join(out)
    if len(text) > 3900:
        text = text[:3900] + "\n\n⚠️ <i>তালিকা বড় — শুধু প্রথম অংশ দেখানো হচ্ছে।</i>"
    return text


# ==========================================================
#                   🎬  HANDLERS
# ==========================================================
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    text = (
        f"👋 <b>স্বাগতম {BOT_NAME} EMIS Bot</b>\n\n"
        "🏫 যেকোনো শিক্ষা প্রতিষ্ঠানের <b>EIIN</b> পাঠালে "
        "হেড ও কর্মচারী তালিকা দেখতে পারবে।\n\n"
        "📝 উদাহরণ: <code>104532</code>\n\n"
        f"👤 Owner: @{OWNER_USERNAME}"
    )
    bot.send_message(msg.chat.id, text, reply_markup=main_reply_keyboard())


@bot.message_handler(commands=["help"])
def cmd_help(msg):
    text = (
        f"<b>📖 {BOT_NAME} EMIS Bot – Help</b>\n\n"
        "1️⃣ EIIN পাঠাও (যেমন <code>104532</code>)\n"
        "2️⃣ বট হেড ও এমপ্লয়ি লিস্ট দেবে\n"
        "3️⃣ Inline বাটন দিয়ে ফিল্টার করতে পারবে\n\n"
        "⚠️ ডেটা সোর্স: <i>apps.emis.gov.bd</i>\n"
        f"👤 Owner: @{OWNER_USERNAME}"
    )
    bot.send_message(msg.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "ℹ️ Help")
def btn_help(msg):
    cmd_help(msg)


@bot.message_handler(func=lambda m: m.text == "👤 Owner")
def btn_owner(msg):
    text = (
        f"👤 <b>Bot Owner</b>\n\n"
        f"Username: @{OWNER_USERNAME}\n"
        f"Bot Name: <b>{BOT_NAME}</b>"
    )
    bot.send_message(msg.chat.id, text, reply_markup=owner_inline())


@bot.message_handler(func=lambda m: m.text == "📊 Bot Status")
def btn_status(msg):
    text = (
        f"✅ <b>{BOT_NAME} Bot চলছে</b>\n\n"
        f"🌐 Data source: apps.emis.gov.bd\n"
        f"🐍 Python + Flask + pyTelegramBotAPI\n"
        f"👤 Owner: @{OWNER_USERNAME}"
    )
    bot.send_message(msg.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "🔍 EIIN দিয়ে সার্চ")
def btn_search(msg):
    bot.send_message(msg.chat.id, "📝 EIIN পাঠাও (শুধু সংখ্যা)। উদাহরণ: <code>104532</code>")


@bot.message_handler(func=lambda m: m.text and m.text.strip().isdigit())
def handle_eiin(msg):
    eiin = msg.text.strip()
    if len(eiin) < 4:
        bot.reply_to(msg, "❌ EIIN কমপক্ষে ৪ ডিজিটের হতে হবে।")
        return

    m = bot.reply_to(msg, "⏳ ডেটা লোড হচ্ছে...")
    try:
        head = fetch_head(eiin)
        emp  = fetch_employees(eiin)
    except requests.HTTPError as e:
        bot.edit_message_text(
            f"❌ API Error: <code>{esc(e)}</code>",
            chat_id=m.chat.id, message_id=m.message_id,
        )
        return
    except Exception as e:
        bot.edit_message_text(
            f"❌ ত্রুটি: <code>{esc(e)}</code>",
            chat_id=m.chat.id, message_id=m.message_id,
        )
        return

    bot.edit_message_text(
        format_head(head),
        chat_id=m.chat.id, message_id=m.message_id,
    )

    emp_txt = format_employees(emp)
    bot.send_message(
        msg.chat.id, emp_txt,
        reply_markup=inline_after_search(eiin),
    )
    if len(emp_txt) >= 3900:
        bot.send_message(
            msg.chat.id,
            "⚠️ <i>উপরের তালিকা কাটা পড়েছে। নিচের বাটনে ক্লিক করে নির্দিষ্ট অংশ দেখো।</i>",
            reply_markup=inline_after_search(eiin),
        )


@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    bot.answer_callback_query(call.id)
    data = call.data

    if data == "close":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        return

    try:
        action, eiin = data.split("|", 1)
    except ValueError:
        return

    try:
        if action == "head":
            bot.send_message(call.message.chat.id, format_head(fetch_head(eiin)))
        elif action == "emp":
            bot.send_message(call.message.chat.id, format_employees(fetch_employees(eiin)))
        elif action == "all":
            bot.send_message(call.message.chat.id, format_head(fetch_head(eiin)))
            bot.send_message(call.message.chat.id, format_employees(fetch_employees(eiin)))
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: <code>{esc(e)}</code>")


@bot.message_handler(func=lambda m: True)
def fallback(msg):
    bot.reply_to(
        msg,
        f"❓ বুঝিনি। EIIN পাঠাও (যেমন <code>104532</code>) অথবা /help দাও।\n"
        f"👤 Owner: @{OWNER_USERNAME}",
    )


# ==========================================================
#                   🚀  BOT POLLING THREAD
# ==========================================================
def start_bot():
    log.info(f"🤖 {BOT_NAME} Bot polling started... Owner: @{OWNER_USERNAME}")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60)
        except Exception as e:
            log.error(f"Bot polling crashed: {e} — restarting in 5s")
            import time
            time.sleep(5)


# ==========================================================
#                   🚀  ENTRYPOINT
# ==========================================================
# Bot thread শুধু একবার শুরু হবে (gunicorn-এ duplicate এড়াতে)
if not os.environ.get("BOT_THREAD_STARTED"):
    os.environ["BOT_THREAD_STARTED"] = "1"
    threading.Thread(target=start_bot, daemon=True).start()


if __name__ == "__main__":
    # Local run: bot + flask একসাথে
    log.info(f"🌐 Flask server starting on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)