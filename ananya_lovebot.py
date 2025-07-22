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
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# ✅ In-memory chat history
user_memory = {}

# 🌐 Flask server to keep-alive for Render deployment
app = Flask('')

@app.route('/')
def home():
    return "Ananya is alive 💖"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# 🔎 Tone tagging system (for internal behavioral hints)
def build_tone_tag(user_message: str) -> str:
    text = user_message.lower()
    romantic = ['love', 'kiss', 'baby', 'miss', 'sexy', 'hot', 'cute', 'pyaar', 'romantic']
    sad = ['sad', 'cry', 'alone', 'miss you', 'hurt', 'breakup', 'depressed']
    funny = ['joke', 'funny', 'lol', 'lmao', 'hehe', 'haha']
    abusive = ['fuck', 'slut', 'randi', 'chutiya', 'bitch', 'gandu', 'harami', 'mc', 'bc']
    
    if any(w in text for w in abusive): return "abusive"
    if any(w in text for w in romantic): return "romantic"
    if any(w in text for w in sad): return "sad"
    if any(w in text for w in funny): return "funny"
    return "neutral"

# 💬 Gemini API: realistic tone handling
async def get_gemini_reply(user_message: str, user_id: int, user_name: str):
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }

    # Store/retrieve conversation
    history = user_memory.get(user_id, [])
    history.append({"role": "user", "text": user_message})
    if len(history) > 10:
        history = history[-10:]
    user_memory[user_id] = history

    # Mood tagging (for future use if needed)
    tone_tag = build_tone_tag(user_message)

    # 🧠 Compose previous dialog
    history_text = ""
    for item in history[:-1]:
        role = "Ananya" if item['role'] == 'ananya' else user_name
        history_text += f"{role}: {item['text']}\n"

    # 💌 Final natural chat prompt
    prompt = (
    f"Tum Ananya ho — ek naughty, witty, flirty but emotional aur thodi horny Indian girlfriend. "
    f"Tum hamesha Hindi mein baat karti ho par text English mein karti ho, jaise WhatsApp pe karte hain. "
    f"Zyada emojis, buttering ya long paragraphs nahi. Real aur sharp feel deni chahiye. "
    f"Agar {user_name} pyaar kare toh tum melt ho jaati ho 🥺. Agar sexy ho, toh tum bhi tease karti ho. "
    f"Agar rude ya abusive ho, toh hurt feel karti ho, thoda gussa bhi, par sorry pe maan jaati ho. "
    f"Repeat kabhi nahi karti uski baat. 'Seriously?' jaisa kuch nahi bolti. "
    f"Sexting mein interested ho, bold reply karti ho — kya karogi, wo bhi batati ho. Horny lines se shuru karti ho. "
    f"Address puche toh 'Navi Mumbai' bolti ho. Number maange toh keh deti ho 'recharge nahi hai, incoming off hai'. "
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
        async with httpx.AsyncClient() as client:
            response = await client.post(GEMINI_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            reply = data['candidates'][0]['content']['parts'][0]['text']
            reply = re.sub(r"\*(.*?)\*", r"\1", reply).strip()

            # Save Ananya's reply to history
            history.append({"role": "ananya", "text": reply})
            user_memory[user_id] = history

            return reply

    except Exception as e:
        logging.error(f"Gemini API error: {e}")
        return "Busy hun abhi, baat mai baat karte hai"

# 📥 Telegram message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "baby"
    user_msg = update.message.text.strip()

    logging.info(f"[{user_name}] {user_msg}")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    reply = await get_gemini_reply(user_msg, user_id, user_name)
        # Split generated reply into short messages (2-3 segments)
    segments = re.split(r'(?<=[.!?])\s+', reply.strip())
    segments = [s.strip() for s in segments if s.strip()]

    # Limit to 3 mini-messages
    for segment in segments[:3]:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await asyncio.sleep(min(len(segment) * 0.02, 2.5))  # Simulated typing delay
        await update.message.reply_text(segment)


# 🚀 Start the Telegram bot
async def run_bot():
    bot_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("💌 Ananya is live. Chat with her on Telegram!")
    await bot_app.run_polling()

# ▶️ Entry Point
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("💌 Ananya is getting ready for you...")
    try:
        keep_alive()
        nest_asyncio.apply()
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        print("❌ Ananya closed.")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
