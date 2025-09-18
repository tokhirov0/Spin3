import os
import random
import logging
from datetime import datetime, timedelta
from threading import Thread
import sqlite3
from telebot import TeleBot, types
from flask import Flask
from dotenv import load_dotenv

# --- Logging sozlamalari ---
logging.basicConfig(
    filename='bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Muhit o‘zgaruvchilari ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- SQLite bazasi ---
DB_FILE = "bot.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Foydalanuvchilar
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            chat_id TEXT PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            spins INTEGER DEFAULT 1,
            last_bonus_time TEXT,
            referrals INTEGER DEFAULT 0
        )
    ''')
    # Kanallar
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            channel TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- Foydalanuvchi funksiyalari ---
def get_user(chat_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE chat_id=?", (str(chat_id),))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (chat_id) VALUES (?)", (str(chat_id),))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE chat_id=?", (str(chat_id),))
        row = cursor.fetchone()
    conn.close()
    return {
        "chat_id": row[0],
        "balance": row[1],
        "spins": row[2],
        "last_bonus_time": row[3],
        "referrals": row[4]
    }

def update_user(user):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET balance=?, spins=?, last_bonus_time=?, referrals=? WHERE chat_id=?
    ''', (user["balance"], user["spins"], user["last_bonus_time"], user["referrals"], str(user["chat_id"])))
    conn.commit()
    conn.close()

# --- Kanal funksiyalari ---
def get_channels():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT channel FROM channels")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def add_channel_to_db(channel):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO channels (channel) VALUES (?)", (channel,))
    conn.commit()
    conn.close()

def remove_channel_from_db(channel):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE channel=?", (channel,))
    conn.commit()
    conn.close()

# --- Kanal a’zoligi tekshirish ---
def check_channel_membership(chat_id):
    channels = get_channels()
    for channel in channels:
        try:
            member = bot.get_chat_member(channel, chat_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

# --- Klaviaturalar ---
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🎰 Spin", "💰 Pul yechish")
    kb.add("🎁 Kunlik bonus", "👥 Referal")
    return kb

def admin_panel():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📊 Statistika", "➕ Kanal qo‘shish", "❌ Kanal o‘chirish")
    kb.add("🔙 Orqaga")
    return kb

# --- Bot handlerlari ---
@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id
    user = get_user(chat_id)

    # Kanal a’zoligi tekshirish
    if not check_channel_membership(chat_id):
        channels = get_channels()
        if channels:
            bot.send_message(chat_id, "Botdan foydalanish uchun quyidagi kanallarga a’zo bo‘ling:\n" + "\n".join(channels))
            return

    bot.send_message(chat_id, "Assalomu alaykum! Tanlang:", reply_markup=main_menu())

# --- Spin ---
@bot.message_handler(func=lambda m: m.text=="🎰 Spin")
def spin(message):
    chat_id = message.chat.id
    if not check_channel_membership(chat_id):
        bot.send_message(chat_id, "Iltimos, avval kanallarga a’zo bo‘ling!")
        return
    user = get_user(chat_id)
    if user["spins"] < 1:
        bot.send_message(chat_id, "Spinlar tugagan!")
        return
    user["spins"] -= 1
    win = random.randint(1000, 10000)
    user["balance"] += win
    update_user(user)
    bot.send_message(chat_id, f"🎉 Ajoyib! {win} so‘m yutdingiz!\nBalans: {user['balance']} so‘m")

# --- Kunlik bonus ---
@bot.message_handler(func=lambda m: m.text=="🎁 Kunlik bonus")
def daily_bonus(message):
    chat_id = message.chat.id
    if not check_channel_membership(chat_id):
        bot.send_message(chat_id, "Iltimos, avval kanallarga a’zo bo‘ling!")
        return
    user = get_user(chat_id)
    now = datetime.now()
    if user["last_bonus_time"]:
        last_bonus = datetime.fromisoformat(user["last_bonus_time"])
        if now - datetime.fromisoformat(user["last_bonus_time"]) < timedelta(days=1):
            bot.send_message(chat_id, "Bugun bonus olgansiz! Ertaga urinib ko‘ring.")
            return
    user["spins"] += 1
    user["last_bonus_time"] = now.isoformat()
    update_user(user)
    bot.send_message(chat_id, "Kunlik bonus: 1 ta spin qo‘shildi!")

# --- Pul yechish ---
@bot.message_handler(func=lambda m: m.text=="💰 Pul yechish")
def withdraw(message):
    chat_id = message.chat.id
    if not check_channel_membership(chat_id):
        bot.send_message(chat_id, "Iltimos, avval kanallarga a’zo bo‘ling!")
        return
    user = get_user(chat_id)
    if user["balance"] < 100000:
        bot.send_message(chat_id, "❌ Minimal pul yechish 100000 so‘m!")
        return
    msg = bot.send_message(chat_id, "Nech so‘m yechmoqchisiz?", reply_markup=types.ForceReply(selective=False))
    bot.register_next_step_handler(msg, process_withdraw)

def process_withdraw(message):
    chat_id = message.chat.id
    try:
        amount = int(message.text)
        user = get_user(chat_id)
        if amount < 100000 or amount > user["balance"]:
            bot.send_message(chat_id, "❌ Noto‘g‘ri miqdor!")
            return
        user["balance"] -= amount
        update_user(user)
        bot.send_message(chat_id, f"Pul yechish: {amount} so‘m qabul qilindi!")
    except:
        bot.send_message(chat_id, "❌ Faqat son kiriting!")

# --- Referal ---
@bot.message_handler(func=lambda m: m.text=="👥 Referal")
def referal(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, f"Sizning referal linkingiz: https://t.me/Spinomat_bot?start={chat_id}")

# --- Admin panel ---
@bot.message_handler(func=lambda m: m.chat.id==ADMIN_ID)
def admin(message):
    if message.text=="/admin":
        bot.send_message(message.chat.id, "Admin panel:", reply_markup=admin_panel())
    elif message.text=="📊 Statistika":
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        rows = cursor.fetchall()
        conn.close()
        stats = "\n".join([f"ID {row[0]}: {row[4]} referal, {row[1]} so‘m" for row in rows])
        bot.send_message(message.chat.id, stats or "Foydalanuvchi yo‘q")
    elif message.text=="➕ Kanal qo‘shish":
        msg = bot.send_message(message.chat.id, "Kanal username kiriting (@ bilan):", reply_markup=types.ForceReply(selective=False))
        bot.register_next_step_handler(msg, admin_add_channel)
    elif message.text=="❌ Kanal o‘chirish":
        msg = bot.send_message(message.chat.id, "O‘chiriladigan kanal username (@ bilan):", reply_markup=types.ForceReply(selective=False))
        bot.register_next_step_handler(msg, admin_remove_channel)
    elif message.text=="🔙 Orqaga":
        bot.send_message(message.chat.id, "Asosiy menyuga qaytildi", reply_markup=main_menu())

def admin_add_channel(message):
    channel = message.text
    if not channel.startswith("@"):
        bot.send_message(message.chat.id, "Kanal @ bilan boshlanishi kerak!")
        return
    add_channel_to_db(channel)
    bot.send_message(message.chat.id, f"Kanal qo‘shildi: {channel}")

def admin_remove_channel(message):
    channel = message.text
    remove_channel_from_db(channel)
    bot.send_message(message.chat.id, f"Kanal o‘chirildi: {channel}")

# --- Flask endpoint ---
@app.route("/")
def index():
    return "Bot ishlayapti!"

# --- Polling thread ---
def polling():
    bot.infinity_polling(skip_pending=True)

if __name__=="__main__":
    t = Thread(target=polling)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
