import os
import time
import json
import threading
from flask import Flask
import telebot
from telebot import types
import requests

# --- RENDER WEB SERVICE HEALTH CHECK SETUP ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running successfully!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- BOT CONFIGURATION & STATE ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8920803418:AAGKDvOJJSJJwvEhPxRGfk5gsV1PjiH3zPM")
bot = telebot.TeleBot(BOT_TOKEN)

CONFIG_FILE = "config.json"
OUTPUT_FILE = "files_name.txt"

# Default settings
DEFAULT_CONFIG = {
    "source_channel": "-1003771375085",
    "destination_channel": "@your_destination_channel",
    "start_id": 1,
    "end_id": 800
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

# Global states for user interactive inputs
user_states = {}

# --- MAIN MENU KEYBOARD ---
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📂 Fetch File Names"),
        types.KeyboardButton("✍️ Add Caption & Send"),
        types.KeyboardButton("⚙️ Settings")
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    config = load_config()
    welcome_text = (
        "🤖 *Telegram Media Manager Bot*\n\n"
        f"• *Source Channel:* `{config['source_channel']}`\n"
        f"• *Destination Channel:* `{config['destination_channel']}`\n"
        f"• *Range:* `{config['start_id']} to {config['end_id']}`\n\n"
        "Choose an option below to begin:"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- SETTINGS HANDLER ---
@bot.message_handler(func=lambda msg: msg.text == "⚙️ Settings")
def settings_menu(message):
    config = load_config()
    text = (
        "⚙️ *Current Settings:*\n"
        f"1. Source: `{config['source_channel']}`\n"
        f"2. Destination: `{config['destination_channel']}`\n"
        f"3. Start ID: `{config['start_id']}`\n"
        f"4. End ID: `{config['end_id']}`\n\n"
        "To update settings, use commands:\n"
        "• `/setsource <channel_id>`\n"
        "• `/setdest <channel_id>`\n"
        "• `/setrange <start> <end>`"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['setsource'])
def set_source(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /setsource -100xxxxxxxxxx or @channel")
        return
    config = load_config()
    config['source_channel'] = parts[1].strip()
    save_config(config)
    bot.reply_to(message, f"✅ Source channel updated to: {config['source_channel']}")

@bot.message_handler(commands=['setdest'])
def set_dest(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /setdest -100xxxxxxxxxx or @channel")
        return
    config = load_config()
    config['destination_channel'] = parts[1].strip()
    save_config(config)
    bot.reply_to(message, f"✅ Destination channel updated to: {config['destination_channel']}")

@bot.message_handler(commands=['setrange'])
def set_range(message):
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /setrange <start_id> <end_id>")
        return
    try:
        start = int(parts[1])
        end = int(parts[2])
        config = load_config()
        config['start_id'] = start
        config['end_id'] = end
        save_config(config)
        bot.reply_to(message, f"✅ Range updated to: {start} - {end}")
    except ValueError:
        bot.reply_to(message, "❌ Error: Start and End IDs must be valid numbers.")

# --- FUNCTION 1: FETCH FILE NAMES (WITH AUTO-DELETE & PERCENTAGE) ---
@bot.message_handler(func=lambda msg: msg.text == "📂 Fetch File Names")
def start_fetching(message):
    config = load_config()
    chat_id = message.chat.id
    
    bot.send_message(chat_id, "🚀 Starting background file name scan...", reply_markup=get_main_keyboard())
    threading.Thread(target=run_fetch_process, args=(chat_id, config)).start()

def run_fetch_process(chat_id, config):
    base_url = f"https://api.telegram.org/bot{BOT_TOKEN}"
    start_id = config['start_id']
    end_id = config['end_id']
    source_ch = config['source_channel']
    
    total_items = (end_id - start_id) + 1
    
    # Initialize output file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# Format: ID X: Filename\n")

    progress_msg = bot.send_message(chat_id, "📊 Initializing progress scan...")
    
    for index, msg_id in enumerate(range(start_id, end_id + 1), start=1):
        url = f"{base_url}/forwardMessage"
        payload = {
            "chat_id": chat_id,
            "from_chat_id": source_ch,
            "message_id": msg_id
        }
        response = requests.post(url, json=payload).json()
        
        if response.get("ok"):
            res_msg = response.get("result", {})
            forwarded_msg_id = res_msg.get("message_id")
            
            # Automatically delete the forwarded message from PM immediately
            if forwarded_msg_id:
                try:
                    requests.post(f"{base_url}/deleteMessage", json={
                        "chat_id": chat_id,
                        "message_id": forwarded_msg_id
                    })
                except:
                    pass
            
            file_name = extract_file_name_from_msg(res_msg)
            if file_name:
                with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                    f.write(f"ID {msg_id}: {file_name}\n")
        
        # Calculate live percentage
        percentage = (index / total_items) * 100
        if index % 3 == 0 or index == total_items:
            try:
                bot.edit_message_text(
                    f"📊 Scanning Progress: {percentage:.1f}% ({index}/{total_items} items processed)", 
                    chat_id, 
                    progress_msg.message_id
                )
            except:
                pass
        
        time.sleep(0.4)

    bot.edit_message_text(f"✅ Scan Complete! Range {start_id} to {end_id} processed successfully.", chat_id, progress_msg.message_id)
    
    # Send generated file
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "rb") as f:
            bot.send_document(chat_id, f, caption="📁 Here is your complete `files_name.txt` list.")

def extract_file_name_from_msg(msg):
    if "audio" in msg:
        return msg["audio"].get("file_name") or f"{msg['audio'].get('title', 'audio')}.mp3"
    elif "document" in msg:
        return msg["document"].get("file_name", "document")
    elif "voice" in msg:
        return f"voice_note_{msg['voice'].get('file_unique_id')}.ogg"
    elif "video" in msg:
        return msg["video"].get("file_name", "video.mp4")
    return None

# --- FUNCTION 2: ADD CAPTION & SEND (WITH HTML & PERCENTAGE) ---
@bot.message_handler(func=lambda msg: msg.text == "✍️ Add Caption & Send")
def prompt_caption_file(message):
    user_states[message.chat.id] = "WAITING_FOR_CAPTION_FILE"
    bot.send_message(
        message.chat.id, 
        "📥 Please upload your edited text file (`files_name.txt`) containing IDs and captions.\n"
        "• Supports `\\n` for new lines.\n"
        "• Supports HTML formatting like `<blockquote>text</blockquote>`.",
        parse_mode="Markdown"
    )

@bot.message_handler(content_types=['document'])
def handle_document_upload(message):
    chat_id = message.chat.id
    if user_states.get(chat_id) == "WAITING_FOR_CAPTION_FILE":
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        local_path = "uploaded_captions.txt"
        with open(local_path, "wb") as f:
            f.write(downloaded_file)
            
        user_states[chat_id] = None
        bot.send_message(chat_id, "⚙️ Caption file received! Processing and sending to destination channel...")
        
        threading.Thread(target=run_caption_process, args=(chat_id, local_path)).start()

def run_caption_process(chat_id, txt_path):
    config = load_config()
    source_ch = config['source_channel']
    dest_ch = config['destination_channel']
    base_url = f"https://api.telegram.org/bot{BOT_TOKEN}"
    
    mapping = {}
    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()
            entries = content.split("ID ")
            for entry in entries:
                if ":" in entry:
                    parts = entry.split(":", 1)
                    try:
                        msg_id_str = parts[0].strip()
                        msg_id = int(msg_id_str)
                        # Replace literal \n with real newlines for multi-line formatting
                        caption = parts[1].strip().replace("\\n", "\n")
                        mapping[msg_id] = caption
                    except ValueError:
                        continue
    except Exception as e:
        bot.send_message(chat_id, f"❌ Failed to parse text file: {e}")
        return

    total_items = len(mapping)
    if total_items == 0:
        bot.send_message(chat_id, "❌ No valid ID mappings found in the uploaded file.")
        return

    progress_msg = bot.send_message(chat_id, f"📊 Initializing send process... Total items: {total_items}")
    count = 0

    for msg_id, caption in mapping.items():
        count += 1
        percentage = (count / total_items) * 100
        
        url = f"{base_url}/copyMessage"
        payload = {
            "chat_id": dest_ch,
            "from_chat_id": source_ch,
            "message_id": msg_id,
            "caption": caption,
            "parse_mode": "HTML"  # Enables HTML tags like <blockquote> and bold/italic elements
        }
        requests.post(url, json=payload)
            
        if count % 3 == 0 or count == total_items:
            try:
                bot.edit_message_text(
                    f"📊 Sending Progress: {percentage:.1f}% ({count}/{total_items} files sent)", 
                    chat_id, 
                    progress_msg.message_id
                )
            except:
                pass
        time.sleep(0.5)

    bot.send_message(chat_id, "🎉 All files with custom captions and HTML formatting have been sent!", reply_markup=get_main_keyboard())

# --- RUN BOT & FLASK SIMULTANEOUSLY ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("Bot starting polling...")
    bot.infinity_polling()
