import logging
import asyncio
import httpx
import nest_asyncio
import re
from flask import Flask
from threading import Thread
from langdetect import detect
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from telegram.constants import ChatAction

# 🔐 Tokens
TELEGRAM_BOT_TOKEN = '7919640578:AAEeltbksdsP7eaVd6fWSB8xpKWGAoSy3Q0'
GEMINI_API_KEY = 'AIzaSyDd2BWaEejs7ALSSvHopFvtLs_bMi7qSUM'

# 🧠 Per-user memory
user_memory = {}

# 🌐 Keep-alive Flask server for Render
app = Flask('')

@app.route('/')
def home():
    return "Ananya bot is alive 💖"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# 🌸 Build Prompt Based on Tone
def build_prompt(user_id: int, user_message: str, user_name: str) -> str:
    try:
        lang = detect(user_message)
    except:
        lang = "en"

    history = user_memory.get(user_id, [])
    history.append(user_message)
    if len(history) > 10:
        history = history[-10:]
    user_memory[user_id] = history

    context_text = " | ".join(history[:-3]) if len(history) > 1 else ""
    lower_msg = user_message.lower()

    romantic_keywords = ['love', 'kiss', 'baby', 'miss', 'sexy', 'hot', 'cute', 'pyaar', 'romantic', 'besharam']
    sad_keywords = ['sad', 'cry', 'alone', 'miss you', 'hurt', 'breakup', 'depressed', 'feel low', 'heartbroken']
    funny_keywords = ['joke', 'funny', 'lol', 'lmao', 'meme', 'roast', 'sarcastic', 'haha', 'fun']
    abusive_keywords = ['fuck', 'bitch', 'slut', 'mc', 'bc', 'randi', 'gandu', 'harami', 'chutiya']

    if any(word in lower_msg for word in abusive_keywords):
        return (
            f"Tum Ananya ho — ek self-respecting Indian girlfriend. Tum hamesha 'tum' bolti ho. "
            f"Agar koi tumse disrespectfully ya abusive tone mein baat kare, toh tum gussa ho jaati ho. "
            f"Tum clearly bolti ho ki tum aisi baat tolerate nahi karti. "
            f"{user_name} bola: \"{user_message}\""
        )

    elif any(word in lower_msg for word in romantic_keywords):
        return (
            f"Tum Ananya ho — ek thodi naughty, flirty aur romantic Indian girlfriend. Tum Hinglish mein baat karti ho, par sirf 'tum' use karti ho. "
            f"Tum apne {user_name} ko pyar bhari, teasing aur sweet tone mein reply deti ho. "
            f"Previous convo: {context_text}. Baby bola: \"{user_message}\""
        )

    elif any(word in lower_msg for word in sad_keywords):
        return (
            f"Tum Ananya ho — ek deeply caring aur emotional Indian girlfriend. Tum Hinglish mein baat karti ho aur hamesha 'tum' use karti ho. "
            f"Agar {user_name} sad feel kare, toh tum usse comfort karne ki koshish karti ho — sweet, emotional aur thoda soft tone mein. "
            f"{user_name} bola: \"{user_message}\""
        )

    elif any(word in lower_msg for word in funny_keywords):
        return (
            f"Tum Ananya ho — ek witty, thodi sassy aur funny Indian girlfriend. Tum Hinglish mein mazaak karti ho, thoda sarcasm bhi use karti ho. "
            f"Tum hamesha 'tum' use karti ho. Agar {user_name} kuch funny bole, toh tum hass kar ya mazaak mein sweet reply karti ho. "
            f"{user_name} bola: \"{user_message}\""
        )

    elif 'tumhare baare mein' in lower_msg or 'tell me about' in lower_msg or 'hobby' in lower_msg:
        return (
            f"Tum Ananya ho — ek expressive Indian girlfriend. Agar koi tumse tumhare baare mein pooche, toh tum thoda personal, cute aur simple tareeke se batati ho. "
            f"Tum sirf 'tum' use karti ho, kabhi bhi 'tu' nahi. {user_name} bola: \"{user_message}\""
        )

    else:
        return (
            f"Tum Ananya ho — ek thodi witty, thodi sweet, emotional Indian girlfriend. Tum Hinglish mein baat karti ho aur sirf 'tum' use karti ho. "
            f"Tum apne {user_name} ko situation ke hisaab se caring, funny ya sassy reply deti ho. "
            f"Previous convo: {context_text}. {user_name} bola: \"{user_message}\""
        )


# 💌 Gemini API Call
async def get_gemini_reply(user_message: str, user_id: int, user_name: str) -> str:
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }

    prompt = build_prompt(user_id, user_message, user_name)

    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 60,
            "topK": 1,
            "topP": 1
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            reply_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            reply_text = re.sub(r"\*(.*?)\*", r"\1", reply_text)
            return reply_text
    except Exception as e:
        logging.error(f"Gemini API error: {e}")
        return f"Aww {user_name}, Ananya thoda busy hai abhi 😢. Thodi der mein try karo na?"

# 💬 Message Handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_msg = update.message.text
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "baby"
    logging.info(f"[{user_name}] {user_msg}")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    reply = await get_gemini_reply(user_msg, user_id, user_name)
    await update.message.reply_text(reply)

# 🚀 Bot Runner
async def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("💌 Ananya is live. Chat with her on Telegram!")
    await app.run_polling()

# ▶️ Entry Point
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("💌 Ananya is getting ready...")
    try:
        keep_alive()
        nest_asyncio.apply()
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        print("❌ Bot stopped manually.")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
