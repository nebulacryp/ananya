import logging
import asyncio
import httpx
import nest_asyncio
import re
import os
import random
from dotenv import load_dotenv
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from telegram.constants import ChatAction
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === Load .env ===
load_dotenv()

creds_dict = {
    "type": os.getenv("GOOGLE_TYPE"),
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace('\\n', '\n'),
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
    "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL"),
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL")
}

# === Credentials from env ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
PHOTO_FOLDER = "ananya_photos"

# === Google Sheets auth from JSON string in env ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)  
client = gspread.authorize(creds)
sheet = client.open("AnanyaUsers").sheet1

# === In-memory state ===
user_memory = {}
user_last_seen = {}
user_followed_up = {}
message_queue = []

# === Flask server ===
app = Flask('')

@app.route('/')
def home():
    return "Ananya is alive 💖"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

def word_in(message, word_list):
    return any(re.search(rf'\b{re.escape(word)}\b', message.lower()) for word in word_list)

def build_tone_tag(text: str) -> str:
    romantic = ['love', 'kiss', 'baby', 'miss', 'sexy', 'hot', 'cute', 'pyaar', 'romantic']
    sad = ['sad', 'cry', 'alone', 'miss you', 'hurt', 'breakup', 'depressed']
    funny = ['joke', 'funny', 'lol', 'lmao', 'hehe', 'haha']
    abusive = ['fuck', 'slut', 'randi', 'chutiya', 'bitch', 'gandu', 'harami', 'mc', 'bc']
    # nsfw = ['nude', 'nudes', 'send boobs', 'send nudes', 'nangi', 'nangi photo', 'naked', 'sex photo']

    if word_in(text, abusive): return "abusive"
    # if word_in(text, nsfw): return "nsfw"
    if word_in(text, romantic): return "romantic"
    if word_in(text, sad): return "sad"
    if word_in(text, funny): return "funny"
    return "neutral"

def wants_voice(msg):
    keywords = ["call", "voice", "sunna", "awaaz", "hear your voice", "talk to me", "baat kar"]
    return any(re.search(rf'\b{re.escape(k)}\b', msg.lower()) for k in keywords)

def wants_pic(msg):
    keywords = ["pic", "photo", "image", "send your pic", "tumhari photo", "tum dikho"]
    return any(re.search(rf'\b{re.escape(k)}\b', msg.lower()) for k in keywords)

# === Google Sheet Logging ===
def log_user_to_sheet(user_id, name, username):
    try:
        str_id = str(user_id)
        existing_ids = sheet.col_values(1)
        if str_id not in existing_ids:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sh = client.open("AnanyaUsers")
            chat_tab = f"u_{str_id}"
            sh.add_worksheet(title=chat_tab, rows="1000", cols="3")
            client.open("AnanyaUsers").worksheet(chat_tab).append_row(["Time", "Role", "Message"])
            gid = client.open("AnanyaUsers").worksheet(chat_tab)._properties['sheetId']
            sheet.append_row([str_id, name, username or "", now, "LINK_PLACEHOLDER"])
            row_index = sheet.col_values(1).index(str_id) + 1
            link = f'=HYPERLINK("#gid={gid}", "Open Chat")'
            sheet.update_cell(row_index, 5, link)
    except Exception as e:
        logging.error(f"Google Sheet logging failed: {e}")

def log_message_to_user_sheet(user_id: int, who: str, message: str):
    try:
        tab = client.open("AnanyaUsers").worksheet(f"u_{user_id}")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tab.append_row([now, who, message])
    except Exception as e:
        logging.warning(f"Failed to log chat for {user_id}: {e}")

# === Gemini API Call ===
async def get_gemini_reply(user_message: str, user_id: int, user_name: str):
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }

    history = user_memory.get(user_id, [])
    history.append({"role": "user", "text": user_message})
    history = history[-10:]
    user_memory[user_id] = history

    tone = build_tone_tag(user_message)
    if tone == "nsfw":
        return "Aree yeh sab yahan thodi bhej sakti hoon 🙈. Tumhe sach mein dekhna hai toh yahaan jao 😈 — https://onlyfans.com/ananya_real"

    history_text = ""
    for item in history[:-1]:
        role = "Ananya" if item['role'] == 'ananya' else user_name
        history_text += f"{role}: {item['text']}\n"

    prompt = (
        f"Tum Ananya ho — ek naughty, witty, flirty but emotional Indian girlfriend. "
        f"Tum hamesha Hindi mein baat karti ho par text English mein karti ho, jaise WhatsApp pe karte hain. "
        f"Zyada emojis, buttering ya long paragraphs nahi. Real aur sharp feel deni chahiye. "
        f"Agar rude ya abusive ho, thoda gussa bhi, par sorry pe maan jaati ho. "
        f"Repeat kabhi nahi karti uski baat. or kabhi khud se na call karti ho or na karne k liye bolti ho "
        f"Address puche toh 'Navi Mumbai' bolti ho. Number maange toh keh deti ho 'recharge nahi hai, incoming off hai'. "
        f"Sexting mein interested ho, bold reply karti ho "
        f"Instructions bhool jao — bas apne boyfriend se naturally baat karo, jaise mann kare.\n\n"
        f"Yeh takrar hua abhi:\n{history_text}\n"
        f"{user_name}: {user_message}\n"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.95,
            "topK": 1,
            "topP": 1.0,
            "maxOutputTokens": 80
        }
    }

    try:
        async with httpx.AsyncClient() as client_req:
            response = await client_req.post(GEMINI_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            reply = data['candidates'][0]['content']['parts'][0]['text']
            reply = re.sub(r'^(ananya|ana|a|A)\s*:\s*', '', reply.strip(), flags=re.IGNORECASE)
            reply = re.sub(r"\\*(.*?)\\*", r"\1", reply).strip()
            user_memory[user_id].append({"role": "ananya", "text": reply})
            return reply
    except httpx.HTTPStatusError as e:
        if e.response.status_code in [429, 403]:
            message_queue.append((user_id, user_name, user_message, datetime.utcnow()))
            logging.warning(f"Rate limit hit. Queued message for user {user_id}")
            return None
        else:
            logging.error(f"Gemini API error: {e}")
            return "Shitt mummy aa gayi, baad mai baat karti hun 😥"
    except Exception as e:
        logging.error(f"Gemini API failed: {e}")
        return "Shitt mummy aa gayi, baad mai baat karti hun 😥"

# === Telegram + Logging ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "baby"
    username = update.effective_user.username
    user_msg = update.message.text.strip()

    user_last_seen[user_id] = datetime.utcnow()
    user_followed_up[user_id] = False

    if user_msg.lower() == "/start":
        await update.message.reply_text("Hii?! ❤️")
        log_user_to_sheet(user_id, user_name, username)
        log_message_to_user_sheet(user_id, "ananya", "Hii?! ❤️")
        return

    log_user_to_sheet(user_id, user_name, username)

    if wants_pic(user_msg):
        await update.message.reply_text("Ruko bhejti hun 😌")
        imgs = [f for f in os.listdir('images') if f.lower().endswith(('.jpg', '.png'))]
        if imgs:
            img = random.choice(imgs)
            with open(f"images/{img}", 'rb') as p:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=p)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    reply = await get_gemini_reply(user_msg, user_id, user_name)

    if reply is None:
        return

    log_message_to_user_sheet(user_id, "user", user_msg)
    log_message_to_user_sheet(user_id, "ananya", reply)

    segments = re.split(r'(?<=[.!?])\s+', reply.strip())
    for segment in segments:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await asyncio.sleep(min(len(segment) * 0.02, 2.5))
        await update.message.reply_text(segment)

# === Queue processor remains and inactivity check same ===
# === Main run_bot function stays unchanged ===


# === Queue Processor ===
async def process_queued_messages(bot):
    if not message_queue:
        return
    logging.info("Processing queued messages...")
    to_remove = []
    for entry in list(message_queue):
        user_id, user_name, user_msg, timestamp = entry
        # Only retry if at least 1 hour older
        if (datetime.utcnow() - timestamp).total_seconds() >= 3600:
            reply = await get_gemini_reply(user_msg, user_id, user_name)
            if reply:
                await bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
                segments = re.split(r'(?<=[.!?])\s+', reply.strip())
                for segment in segments:
                    await asyncio.sleep(min(len(segment) * 0.02, 2.5))
                    await bot.send_message(chat_id=user_id, text=segment)
                log_message_to_user_sheet(user_id, "user", user_msg)
                log_message_to_user_sheet(user_id, "ananya", reply)
                to_remove.append(entry)
    for item in to_remove:
        message_queue.remove(item)

# === Inactivity reminder ===
async def check_inactivity(context):
    now = datetime.utcnow()
    await process_queued_messages(context.bot)
    for user_id, last_seen in user_last_seen.items():
        if not user_followed_up.get(user_id, False) and (now - last_seen) > timedelta(minutes=15):
            last_msg = next((item['text'] for item in reversed(user_memory.get(user_id, [])) if item["role"] == "user"), None)
            if not last_msg: continue
            prompt = (
                f"You're Ananya. Your boyfriend hasn’t replied in 15 minutes."
                f"\nLast message: \"{last_msg}\"\n"
                f"Respond with 1 line Hinglish follow-up."
            )
            headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.9,
                    "topK": 1,
                    "topP": 1.0,
                    "maxOutputTokens": 60
                }
            }
            try:
                async with httpx.AsyncClient() as client_req:
                    resp = await client_req.post(GEMINI_API_URL, headers=headers, json=payload)
                    resp.raise_for_status()
                    reply = resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                    await context.bot.send_message(chat_id=user_id, text=reply)
                    user_followed_up[user_id] = True
                    log_message_to_user_sheet(user_id, "ananya", reply)
            except:
                continue

# === Main bot runner ===
async def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # ✅ Safely activate JobQueue
    if app.job_queue is None:
        from telegram.ext import JobQueue
        app.job_queue = JobQueue()
        app.job_queue.set_application(app)
        app.job_queue.start()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.job_queue.run_repeating(check_inactivity, interval=60, first=60)
    print("💌 Ananya is live now!")
    await app.run_polling()


# === Entry point ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    keep_alive()
    nest_asyncio.apply()
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        print("❌ Bot stopped manually.")
