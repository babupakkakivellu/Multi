# bot.py
from pyrogram import Client
from config import Config

# Initialize the bot
app = Client(
    "video_compress_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)
