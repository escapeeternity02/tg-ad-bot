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

# ==== Fake server to keep Render alive ====
def run_fake_server():
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Telegram bot is running.')

    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('', port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_fake_server).start()

# ==== Configuration ====
SESSION_NAME = "session1"
SESSION_FOLDER = "sessions"
LOG_FILE = "interactions.log"
MAX_DMS_PER_HOUR = 15
DM_DELAY_RANGE = (20, 60)
AD_BOT_TOKEN = os.environ.get("AD_BOT_TOKEN")  # Use environment variable
LOG_GROUP_USERNAME = os.environ.get("LOG_GROUP_USERNAME")  # Also from environment

KEYWORDS = [
    "need netflix", "i need netflix", "netflix need", "nf need",
    "need nf", "netflix screen need", "need netflix screen", "need 1 month"
]

# ==== Prepare paths and logger ====
os.makedirs(SESSION_FOLDER, exist_ok=True)
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(message)s')
dm_timestamps = []

async def send_bot_message(text):
    async with ClientSession() as session:
        url = f"https://api.telegram.org/bot{AD_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": LOG_GROUP_USERNAME,
            "text": text
        }
        await session.post(url, data=payload)

async def get_saved_message(client):
    history = await client(GetHistoryRequest(peer='me', limit=1, offset_date=None, offset_id=0, max_id=0, min_id=0, add_offset=0, hash=0))
    if history.messages:
        return history.messages[0].message
    return None

def matches_keywords(text):
    text = text.lower()
    return any(kw in text for kw in KEYWORDS)

def is_rate_limited():
    now = datetime.now()
    global dm_timestamps
    dm_timestamps = [ts for ts in dm_timestamps if now - ts < timedelta(hours=1)]
    return len(dm_timestamps) >= MAX_DMS_PER_HOUR

def record_dm():
    dm_timestamps.append(datetime.now())

async def handle_reply(event):
    sender = await event.get_sender()
    username = f"@{sender.username}" if sender.username else "Unknown"
    user_id = sender.id
    message_text = event.raw_text.strip()
    formatted = f"📩 New DM Reply\n\n👤 From: {username} (User ID: {user_id})\n\n💬 Message:\n{message_text}"
    await send_bot_message(formatted)

async def main():
    session_path = os.path.join(SESSION_FOLDER, f"{SESSION_NAME}.json")
    if not os.path.exists(session_path):
        print(f"[!] Session file not found: {session_path}")
        return

    with open(session_path, "r") as f:
        credentials = json.load(f)

    client = TelegramClient(os.path.join(SESSION_FOLDER, SESSION_NAME), credentials['api_id'], credentials['api_hash'])
    await client.start()

    print("[+] Bot is running... Monitoring groups.")
    ad_message = await get_saved_message(client)
    if not ad_message:
        print("[!] No saved message found.")
        return

    @client.on(events.NewMessage(chats=lambda dialog: dialog.is_group))
    async def group_message_handler(event):
        try:
            if matches_keywords(event.raw_text):
                sender = await event.get_sender()
                if sender.bot:
                    return

                if is_rate_limited():
                    print("[!] DM limit reached. Skipping...")
                    return

                await event.reply("I Have, DM!")
                await client.send_message(sender.id, ad_message)

                log_msg = f"DM sent to {sender.username or 'Unknown'} (ID: {sender.id}) from group {event.chat.title}"
                logging.info(log_msg)
                print(f"[+] {log_msg}")
                record_dm()

                await asyncio.sleep(random.randint(*DM_DELAY_RANGE))
        except Exception as e:
            print(f"[!] Error in group handler: {e}")

    @client.on(events.NewMessage(incoming=True, chats=None))
    async def private_reply_handler(event):
        try:
            await handle_reply(event)
        except Exception as e:
            print(f"[!] Error in reply handler: {e}")

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
