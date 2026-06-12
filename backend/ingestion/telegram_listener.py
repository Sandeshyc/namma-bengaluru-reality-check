import os
import asyncio
import logging
import random
import httpx
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("TELEGRAM_PHONE")
BACKEND_URL = "http://localhost:8000/api/analyze"

# List of known public Bengaluru rental broker channels
TARGET_CHANNELS = [
    "bengaluru_rentals",
    "flatmates_bengaluru",
    "bengaluru_flats"
]

client = TelegramClient('reality_check_session', API_ID, API_HASH)

async def send_to_backend(text: str, msg_id: str):
    """Push raw listing to the backend API."""
    try:
        async with httpx.AsyncClient() as http_client:
            payload = {
                "raw_text": text,
                "source_platform": "telegram",
                "source_msg_id": msg_id
            }
            resp = await http_client.post(BACKEND_URL, json=payload, timeout=10.0)
            if resp.status_code == 200:
                logger.info(f"Successfully pushed message {msg_id} to backend.")
            else:
                logger.error(f"Backend returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Failed to reach backend: {e}")

@client.on(events.NewMessage(chats=TARGET_CHANNELS))
async def handler(event):
    """Handle new incoming messages from target channels."""
    text = event.message.text
    if not text:
        return
        
    # Filter out very short messages (likely just chatter or "DM me")
    word_count = len(text.split())
    if word_count < 15:
        logger.debug(f"Skipping short message ({word_count} words)")
        return
        
    msg_id = f"{event.chat_id}_{event.id}"
    logger.info(f"New potential listing detected! ID: {msg_id}")
    
    # Random sleep to avoid anti-spam triggers
    await asyncio.sleep(random.uniform(2, 5))
    
    await send_to_backend(text, msg_id)

async def main():
    logger.info("Starting Telegram ingestion listener...")
    
    if not API_ID or not API_HASH:
        logger.error("Telegram API credentials missing. Cannot start listener.")
        return
        
    try:
        await client.start(phone=PHONE)
        logger.info(f"Listening on channels: {TARGET_CHANNELS}")
        await client.run_until_disconnected()
    except FloodWaitError as e:
        logger.error(f"FloodWaitError: Must wait {e.seconds} seconds before connecting.")
        # DO NOT bypass this wait!
    except Exception as e:
        logger.error(f"Telegram client error: {e}")

if __name__ == '__main__':
    asyncio.run(main())
