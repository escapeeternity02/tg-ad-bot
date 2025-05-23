import os
import re
import json
import time
import random
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetHistoryRequest
from aiohttp import ClientSession

# ==== FAKE SERVER TO KEEP RENDER ALIVE ====
def run_fake_server():
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Telegram bot is running.')

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("", port), SimpleHandler)
    print(f"[HTTP SERVER] Running keep-alive on port {port}")
    server.serve_forever()

threading.Thread(target=run_fake_server).start()

# ==== CONFIGURATION ====
SESSION_NAME = "session1"
SESSION_FOLDER = "sessions"
LOG_FILE = "interactions.log"
MAX_DMS_PER_HOUR = 15
DM_DELAY_RANGE = (20, 60)

AD_BOT_TOKEN = os.environ.get("AD_BOT_TOKEN")
LOG_GROUP_USERNAME = os.environ.get("LOG_GROUP_USERNAME")

KEYWORDS = [
    "need netflix", "i need netflix", "netflix need", "nf need",
    "need nf", "netflix screen need", "need netflix screen", "need 1 month"
]

# ==== LOGGING SETUP ====
os.makedirs(SESSION_FOLDER, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

dm_timestamps = []

# ==== SEND TELEGRAM MESSAGE TO LOG GROUP ====
async def send_bot_message(text):
    async with ClientSession() as session:
        url = f"https://api.telegram.org/bot{AD_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": LOG_GROUP_USERNAME, "text": text}
        await session.post(url, data=payload)

# ==== FETCH SAVED AD MESSAGE ====
async def get_saved_message(client):
    history = await client(GetHistoryRequest(peer='me', limit=1, offset_date=None, offset_id=0, max_id=0, min_id=0, add_offset=0, hash=0))
    if history.messages:
        return history.messages[0].message
    return None

# ==== MATCH MESSAGE TO KEYWORDS ====
def matches_keywords(text):
    text = text.lower()
    return any(kw in text for kw in KEYWORDS)

# ==== DM RATE LIMITING ====
def is_rate_limited():
    now = datetime.now()
    global dm_timestamps
    dm_timestamps = [ts for ts in dm_timestamps if now - ts < timedelta(hours=1)]
    return len(dm_timestamps) >= MAX_DMS_PER_HOUR

def record_dm():
    dm_timestamps.append(datetime.now())

# ==== HANDLE USER DM REPLY ====
async def handle_reply(event):
    sender = await event.get_sender()
    username = f"@{sender.username}" if sender.username else "Unknown"
    user_id = sender.id
    message_text = event.raw_text.strip()
    formatted = f"📩 New DM Reply\n\n👤 From: {username} (User ID: {user_id})\n\n💬 Message:\n{message_text}"
    await send_bot_message(formatted)
    print(f"[REPLY] From {username}: {message_text}")

# ==== MAIN FUNCTION ====
async def main():
    print("[INIT] Starting Telegram bot...")
    
    session_path = os.path.join(SESSION_FOLDER, f"{SESSION_NAME}.json")
    if not os.path.exists(session_path):
        print(f"[ERROR] Session file not found: {session_path}")
        return

    if not AD_BOT_TOKEN:
        print("[ERROR] Missing AD_BOT_TOKEN environment variable")
        return
    if not LOG_GROUP_USERNAME:
        print("[ERROR] Missing LOG_GROUP_USERNAME environment variable")
        return

    with open(session_path, "r") as f:
        credentials = json.load(f)

    print("[DEBUG] Credentials loaded. Connecting to Telegram...")

    client = TelegramClient(os.path.join(SESSION_FOLDER, SESSION_NAME), credentials['api_id'], credentials['api_hash'])
    await client.start()

    print("[READY] Logged in and running.")
    ad_message = await get_saved_message(client)

    if not ad_message:
        print("[ERROR] No saved message found in 'Saved Messages'. Please save your ad there.")
        return

    print("[MONITORING] Watching all groups for leads...")

    @client.on(events.NewMessage(chats=lambda dialog: dialog.is_group))
    async def group_message_handler(event):
        try:
            if matches_keywords(event.raw_text):
                sender = await event.get_sender()
                if sender.bot:
                    return

                if is_rate_limited():
                    print("[LIMIT] DM limit reached for this hour. Skipping...")
                    return

                await event.reply("I Have, DM!")
                await client.send_message(sender.id, ad_message)

                log_msg = f"DM sent to {sender.username or 'Unknown'} (ID: {sender.id}) from group {event.chat.title}"
                logging.info(log_msg)
                print(f"[SEND] {log_msg}")
                record_dm()

                await asyncio.sleep(random.randint(*DM_DELAY_RANGE))
        except Exception as e:
            print(f"[ERROR] Group message handler: {e}")

    @client.on(events.NewMessage(incoming=True, chats=None))
    async def private_reply_handler(event):
        try:
            await handle_reply(event)
        except Exception as e:
            print(f"[ERROR] Reply handler: {e}")

    await client.run_until_disconnected()

# ==== START ====
if __name__ == "__main__":
    asyncio.run(main())
