import os
import time
import json
import asyncio
import subprocess
import re
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    Message, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery
)
from pyrogram.errors import FloodWait, RPCError, BadRequest, Forbidden

# Bot configuration
API_ID = "16501053" 
API_HASH = "d8c9b01c863dabacc484c2c06cdd0f6e" 
BOT_TOKEN = "8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I"

# Compression Settings
RESOLUTIONS = {
    "144p 📱": "256x144",
    "240p 📱": "426x240",
    "360p 📱": "640x360",
    "480p 💻": "854x480",
    "720p 💻": "1280x720",
    "1080p 🖥️": "1920x1080",
    "4K 🎯": "3840x2160"
}

PRESETS = {
    "Ultrafast ⚡": "ultrafast",
    "Superfast 🚀": "superfast",
    "Veryfast 🏃": "veryfast",
    "Faster 🏃‍♂️": "faster",
    "Fast ⚡": "fast",
    "Medium 🚶": "medium",
    "Slow 🐢": "slow"
}

CRF_VALUES = {
    "15 - Visually Lossless 🎯": "15",
    "18 - High Quality 🎥": "18",
    "23 - Medium Quality 📺": "23",
    "28 - Low Quality 📱": "28"
}

THEMES = {
    "mobile": {
        "name": "📱 Mobile Data Saver",
        "resolution": "480x360",
        "preset": "veryfast",
        "crf": "28",
        "codec": "libx264",
        "pixel_format": "yuv420p",
        "description": "Smallest size, good for mobile data"
    },
    "telegram": {
        "name": "📬 Telegram Optimized",
        "resolution": "720x480",
        "preset": "medium",
        "crf": "23",
        "codec": "libx264",
        "pixel_format": "yuv420p",
        "description": "Balanced for Telegram sharing"
    },
    "high": {
        "name": "🎯 High Quality",
        "resolution": "1280x720",
        "preset": "slow",
        "crf": "18",
        "codec": "libx264",
        "pixel_format": "yuv420p",
        "description": "Best quality, larger size"
    }
}

class CompressionState:
    def __init__(self):
        self.file_id = None
        self.file_name = None
        self.message = None
        self.task_id = None
        self.resolution = "720x480"
        self.preset = "medium"
        self.crf = "23"
        self.codec = "libx264"
        self.pixel_format = "yuv420p"
        self.custom_name = None
        self.output_format = "video"
        self.waiting_for_filename = False
        self.start_time = None

class CompressionTasks:
    def __init__(self):
        self.tasks = {}
        self.max_tasks = 3

    def add_task(self, user_id, task_id, state):
        if user_id not in self.tasks:
            self.tasks[user_id] = {}
        if len(self.tasks[user_id]) >= self.max_tasks:
            return False
        self.tasks[user_id][task_id] = state
        return True

    def remove_task(self, user_id, task_id):
        if user_id in self.tasks and task_id in self.tasks[user_id]:
            del self.tasks[user_id][task_id]
            if not self.tasks[user_id]:
                del self.tasks[user_id]

    def get_task(self, user_id, task_id):
        return self.tasks.get(user_id, {}).get(task_id)

    def get_user_tasks_count(self, user_id):
        return len(self.tasks.get(user_id, {}))

compression_tasks = CompressionTasks()

app = Client("video_compress_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def format_size(size):
    try:
        size = float(abs(size))
        if size == 0:
            return "0B"
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        i = 0
        while size >= 1024.0 and i < len(units)-1:
            size /= 1024.0
            i += 1
        return f"{size:.2f} {units[i]}"
    except Exception as e:
        print(f"Size format error: {str(e)}")
        return "0B"

def create_theme_menu(task_id):
    buttons = [
        [
            InlineKeyboardButton("📱 Mobile Saver", callback_data=f"theme:{task_id}:mobile"),
            InlineKeyboardButton("📬 Telegram", callback_data=f"theme:{task_id}:telegram")
        ],
        [
            InlineKeyboardButton("🎯 High Quality", callback_data=f"theme:{task_id}:high"),
            InlineKeyboardButton("⚙️ Custom", callback_data=f"theme:{task_id}:custom")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{task_id}")]
    ]
    return InlineKeyboardMarkup(buttons)

def create_custom_menu(task_id):
    buttons = [
        [InlineKeyboardButton("📐 Resolution", callback_data=f"custom:{task_id}:resolution")],
        [InlineKeyboardButton("⚡ Preset", callback_data=f"custom:{task_id}:preset")],
        [InlineKeyboardButton("🎯 Quality (CRF)", callback_data=f"custom:{task_id}:crf")],
        [InlineKeyboardButton("✅ Confirm Settings", callback_data=f"custom:{task_id}:confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{task_id}")]
    ]
    return InlineKeyboardMarkup(buttons)

async def show_format_selection(message, theme_name, task_id):
    buttons = [
        [
            InlineKeyboardButton("📹 Video", callback_data=f"format:{task_id}:video"),
            InlineKeyboardButton("📄 Document", callback_data=f"format:{task_id}:document")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{task_id}")]
    ]
    await message.edit_text(
        f"🎯 **Selected: {theme_name}**\n\n"
        "Choose output format:\n\n"
        "📹 **Video** - Send as video message\n"
        "📄 **Document** - Send as file",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_message(filters.command("start"))
async def start_command(client, message):
    try:
        welcome_text = (
            "🎥 **Welcome to Video Compression Bot!**\n\n"
            "I can help you compress videos with various settings:\n\n"
            "📱 **Mobile Data Saver**\n"
            "• Smallest file size\n"
            "• Good for mobile data\n\n"
            "📬 **Telegram Optimized**\n"
            "• Balanced quality\n"
            "• Perfect for sharing\n\n"
            "🎯 **High Quality**\n"
            "• Best quality\n"
            "• Larger file size\n\n"
            "⚙️ **Custom Settings**\n"
            "• Choose your own settings\n\n"
            "Send me any video to start! 🚀"
        )
        await message.reply_text(welcome_text)
    except Exception as e:
        print(f"Start command error: {str(e)}")
        await message.reply_text("❌ An error occurred. Please try again.")

@app.on_message(filters.video | filters.document)
async def handle_video(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        task_id = str(int(time.time()))
        
        if compression_tasks.get_user_tasks_count(user_id) >= compression_tasks.max_tasks:
            await message.reply_text(
                "⚠️ Maximum concurrent tasks reached.\n"
                "Please wait for current task to complete."
            )
            return
        
        state = CompressionState()
        
        if message.video:
            state.file_id = message.video.file_id
            state.file_name = message.video.file_name or "video.mp4"
            file_size = message.video.file_size
        else:
            if not message.document.mime_type or not message.document.mime_type.startswith("video/"):
                await message.reply_text("❌ Please send a valid video file.")
                return
                
            state.file_id = message.document.file_id
            state.file_name = message.document.file_name or "video.mp4"
            file_size = message.document.file_size
        
        if file_size > 2_000_000_000:  # 2GB limit
            await message.reply_text("❌ File too large. Maximum size: 2GB")
            return
        
        state.message = message
        state.task_id = task_id
        
        if compression_tasks.add_task(user_id, task_id, state):
            info_text = (
                "🎥 **Video Received!**\n\n"
                f"📁 **Filename:** `{state.file_name}`\n"
                f"💾 **Size:** {format_size(file_size)}\n\n"
                "**Choose Compression Settings:**"
            )
            
            await message.reply_text(
                info_text,
                reply_markup=create_theme_menu(task_id)
            )
        else:
            await message.reply_text("❌ Failed to start compression task. Please try again.")
    
    except Exception as e:
        error_text = f"❌ Error processing video: {str(e)}"
        print(error_text)
        await message.reply_text(error_text)

async def start_compression(client: Client, state: CompressionState):
    progress_msg = await state.message.reply_text("⚙️ **Starting Process...**")
    input_file = output_file = thumbnail = None
    
    try:
        # Download video
        await progress_msg.edit_text("📥 **Downloading...**")
        input_file = await client.download_media(state.file_id)
        
        if not input_file:
            raise Exception("Download failed")

        # Get video information and create thumbnail
        await progress_msg.edit_text("🔍 **Analyzing Video...**")
        
        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=width,height,codec_name",
            "-of", "json",
            input_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await probe.communicate()
        video_info = json.loads(stdout.decode('utf-8'))
        duration = float(video_info['format']['duration'])

        # Extract thumbnail
        thumbnail = f"thumb_{os.path.basename(input_file)}.jpg"
        thumb_cmd = [
            "ffmpeg", "-ss", str(duration/2),
            "-i", input_file,
            "-vframes", "1",
            "-vf", "scale=320:-1",
            "-q:v", "2",
            thumbnail
        ]
        
        process = await asyncio.create_subprocess_exec(
            *thumb_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        # Start compression
        output_file = f"compressed_{state.custom_name}"
        await progress_msg.edit_text("🎯 **Compressing...**")

        ffmpeg_cmd = [
            "ffmpeg", "-i", input_file,
            "-c:v", state.codec,
            "-preset", state.preset,
            "-crf", str(state.crf),
            "-vf", f"scale={state.resolution}",
            "-pix_fmt", state.pixel_format,
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y",
            output_file
        ]

        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        # Get file sizes
        original_size = os.path.getsize(input_file)
        compressed_size = os.path.getsize(output_file)

        # Upload
        await progress_msg.edit_text("📤 **Uploading...**")
        
        caption = (
            f"🎥 **{state.custom_name}**\n\n"
            f"📊 **Compression Results:**\n"
            f"• Original: {format_size(original_size)}\n"
            f"• Compressed: {format_size(compressed_size)}\n"
            f"• Saved: {((original_size - compressed_size) / original_size) * 100:.1f}%"
        )

        if state.output_format == "video":
            await client.send_video(
                state.message.chat.id,
                output_file,
                thumb=thumbnail,
                duration=int(duration),
                caption=caption
            )
        else:
            await client.send_document(
                state.message.chat.id,
                output_file,
                thumb=thumbnail,
                caption=caption
            )

        await progress_msg.edit_text("✅ **Compression Complete!**")

    except Exception as e:
        await progress_msg.edit_text(f"❌ **Error:** {str(e)}")
    
    finally:
        # Cleanup
        for file in [input_file, output_file, thumbnail]:
            if file and os.path.exists(file):
                os.remove(file)
        
        if state.message.from_user.id in compression_tasks.tasks:
            compression_tasks.remove_task(state.message.from_user.id, state.task_id)

# Start the bot
print("🤖 Bot is running...")
app.run()
