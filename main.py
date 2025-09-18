import os
import json
import random
import logging
from datetime import datetime, timedelta
from threading import Thread, Lock
from flask import Flask
from telebot import TeleBot, types
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
ADMIN_ID = os.getenv("ADMIN_ID")

if not all([BOT_TOKEN, ADMIN_ID]):
    logging.error("Muhit o‘zgaruvchilari yetishmayapti!")
    raise ValueError("BOT_TOKEN yoki ADMIN_ID aniqlanmagan!")

try:
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    logging.error("ADMIN_ID butun son bo‘lishi kerak!")
    raise ValueError("ADMIN_ID butun son bo‘lishi kerak!")

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- Fayllar va sinxronizatsiya ---
USERS_FILE = "users.json"
CHANNELS_FILE = "channels.json"
file_lock = Lock()

# --- JSON fayl funksiyalari ---
def load_json(file):
    with file_lock:
        try:
            if not os.path.exists(file):
                default_data = {} if "users" in file else []
                with open(file, "w") as f:
                    json.dump(default_data, f)
            with open(file, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Faylni o‘qishda xato: {file}, {str(e)}")
            return {} if "users" in file else []

def save_json(file, data):
    with file_lock:
        try:
            with open(file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logging.error(f"Faylni saqlashda xato: {file}, {str(e)}")

# --- Foydalanuvchi ma’lumotlari ---
def get_user(chat_id):
    users = load_json(USERS_FILE)
    chat_id_str = str(chat_id)
    if chat_id_str not in users:
        users[chat_id_str] = {
            "balance": 0,
            "spins": 1,
            "daily_bonus": False,
            "last_bonus_time": None,
            "referrals": 0
        }
        save_json(USERS_FILE, users)
    return users[chat_id_str]

def update_user(chat_id, user_data):
    users = load_json(USERS_FILE)
    users[str(chat_id)] = user_data
    save_json(USERS_FILE, users)

# --- Kanal tekshiruvi ---
def check_channel_membership(chat_id):
    channels = load_json(CHANNELS_FILE)
    for channel in channels:
        try:
            member = bot.get_chat_member(channel, chat_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception as e:
            logging.error(f"Kanal a’zoligini tekshirishda xato: {channel}, {str(e)}")
            return False
    return True

# --- Klaviaturalar ---
def main_menu(user):
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
    args = message.text.split()
    chat_id = message.chat.id
    user = get_user(chat_id)
    
    # Referal logikasi
    if len(args) > 1:
        referrer_id = args[1]
        if referrer_id != str(chat_id):
            referrer = get_user(referrer_id)
            referrer["referrals"] += 1
            referrer["balance"] += 5000  # Referal uchun bonus
            update_user(referrer_id, referrer)
            logging.info(f"Referal qo‘shildi: {referrer_id} uchun {chat_id}")
    
    # Kanal a’zoligini tekshirish
    if not check_channel_membership(chat_id):
        channels = load_json(CHANNELS_FILE)
        if channels:
            bot.send_message(chat_id, "Botdan foydalanish uchun quyidagi kanallarga a’zo bo‘ling:\n" + "\n".join(channels))
            return
    
    bot.send_message(chat_id, "Assalomu alaykum! Tanlang:", reply_markup=main_menu(user))

@bot.message_handler(func=lambda m: m.text == "🎰 Spin")
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
    update_user(chat_id, user)
    bot.send_message(chat_id, f"🎉 Ajoyib! {win} so‘m yutdingiz!")
    bot.send_message(chat_id, f"Hozirgi balans: {user['balance']} so‘m")

@bot.message_handler(func=lambda m: m.text == "🎁 Kunlik bonus")
def daily_bonus(message):
    chat_id = message.chat.id
    if not check_channel_membership(chat_id):
        bot.send_message(chat_id, "Iltimos, avval kanallarga a’zo bo‘ling!")
        return
    
    user = get_user(chat_id)
    now = datetime.now()
    
    if user["last_bonus_time"]:
        last_bonus = datetime.fromisoformat(user["last_bonus_time"])
        if now - last_bonus < timedelta(days=1):
            bot.send_message(chat_id, "Bugun bonus olgansiz! Ertaga urinib ko‘ring.")
            return
    
    user["spins"] += 1
    user["last_bonus_time"] = now.isoformat()
    update_user(chat_id, user)
    bot.send_message(chat_id, "Kunlik bonus: 1 ta spin qo‘shildi!")

@bot.message_handler(func=lambda m: m.text == "💰 Pul yechish")
def withdraw(message):
    chat_id = message.chat.id
    if not check_channel_membership(chat_id):
        bot.send_message(chat_id, "Iltimos, avval kanallarga a’zo bo‘ling!")
        return
    
    user = get_user(chat_id)
    if user["balance"] < 100000:
        bot.send_message(chat_id, "❌ Minimal pul yechish 100000 so‘m!")
        return
    markup = types.ForceReply(selective=False)
    msg = bot.send_message(chat_id, "Nech so‘m yechmoqchisiz?", reply_markup=markup)
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
        update_user(chat_id, user)
        bot.send_message(chat_id, f"Pul yechish: {amount} so‘m qabul qilindi!")
        logging.info(f"Pul yechish so‘rovi: {chat_id} uchun {amount} so‘m")
    except ValueError:
        bot.send_message(chat_id, "❌ Faqat son kiriting!")
        logging.warning(f"Noto‘g‘ri pul yechish miqdori: {chat_id}, {message.text}")

@bot.message_handler(func=lambda m: m.text == "👥 Referal")
def referal(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, f"Sizning referal linkingiz: https://t.me/Spinomad1_bot?start={chat_id}")

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID)
def admin(message):
    if message.text == "/admin":
        bot.send_message(message.chat.id, "Admin panel:", reply_markup=admin_panel())
    elif message.text == "📊 Statistika":
        users = load_json(USERS_FILE)
        stats = "\n".join([f"ID {uid}: {data['referrals']} referal, {data['balance']} so‘m" for uid, data in users.items()])
        bot.send_message(message.chat.id, stats or "Foydalanuvchi yo‘q")
    elif message.text == "➕ Kanal qo‘shish":
        markup = types.ForceReply(selective=False)
        msg = bot.send_message(message.chat.id, "Kanal username kiriting (@ bilan):", reply_markup=markup)
        bot.register_next_step_handler(msg, add_channel)
    elif message.text == "❌ Kanal o‘chirish":
        markup = types.ForceReply(selective=False)
        msg = bot.send_message(message.chat.id, "O‘chiriladigan kanal username (@ bilan):", reply_markup=markup)
        bot.register_next_step_handler(msg, remove_channel)
    elif message.text == "🔙 Orqaga":
        user = get_user(message.chat.id)
        bot.send_message(message.chat.id, "Asosiy menyuga qaytildi", reply_markup=main_menu(user))

def add_channel(message):
    channel = message.text
    if not channel.startswith("@"):
        bot.send_message(message.chat.id, "Kanal username @ bilan boshlanishi kerak!")
        return
    channels = load_json(CHANNELS_FILE)
    if channel not in channels:
        channels.append(channel)
        save_json(CHANNELS_FILE, channels)
        bot.send_message(message.chat.id, f"Kanal qo‘shildi: {channel}")
        logging.info(f"Yangi kanal qo‘shildi: {channel}")
    else:
        bot.send_message(message.chat.id, "Kanal allaqachon mavjud!")

def remove_channel(message):
    channel = message.text
    channels = load_json(CHANNELS_FILE)
    if channel in channels:
        channels.remove(channel)
        save_json(CHANNELS_FILE, channels)
        bot.send_message(message.chat.id, f"Kanal o‘chirildi: {channel}")
        logging.info(f"Kanal o‘chirildi: {channel}")
    else:
        bot.send_message(message.chat.id, "Bunday kanal yo‘q!")

# --- Flask health check ---
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot ishlayapti!"

# --- Bot polling thread ---
def run_bot():
    logging.info("Bot polling bilan ishga tushdi...")
    bot.infinity_polling(skip_pending=True)

# --- Main ---
if __name__ == "__main__":
    from threading import Thread
    Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
