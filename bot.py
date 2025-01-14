import os
import time
import json
import asyncio
import subprocess
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, RPCError, BadRequest, Forbidden

# Bot configuration from environment variables
API_ID = os.getenv("API_ID", "16501053")
API_HASH = os.getenv("API_HASH", "d8c9b01c863dabacc484c2c06cdd0f6e")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I")

# Compression settings
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

class ProgressTracker:
    def __init__(self):
        self.start_time = time.time()
        self.last_update_time = 0
        self.last_current = 0
        self.total = 0
        self.speed_history = []
        self.update_interval = 2

    def calculate_speed(self, current):
        now = time.time()
        elapsed = now - self.last_update_time
        if elapsed > 0:
            speed = (current - self.last_current) / elapsed
            self.speed_history.append(speed)
            if len(self.speed_history) > 5:
                self.speed_history.pop(0)
        return sum(self.speed_history) / len(self.speed_history) if self.speed_history else 0

    def should_update(self):
        return (time.time() - self.last_update_time) >= self.update_interval

    def update(self, current, total):
        self.total = total
        now = time.time()
        
        if self.should_update():
            speed = self.calculate_speed(current)
            self.last_current = current
            self.last_update_time = now
            
            elapsed_time = now - self.start_time
            eta = (total - current) / speed if speed > 0 else 0
            progress = (current / total * 100) if total > 0 else 0
            
            return {
                'progress': min(100, progress),
                'speed': speed,
                'elapsed': elapsed_time,
                'eta': eta,
                'current_size': format_size(current),
                'total_size': format_size(total),
                'should_update': True
            }
        return {'should_update': False}

class CompressionState:
    def __init__(self):
        self.file_id = None
        self.file_name = None
        self.message = None
        self.resolution = "720x480"
        self.preset = "medium"
        self.crf = "23"
        self.codec = "libx264"
        self.pixel_format = "yuv420p"
        self.custom_name = None
        self.output_format = "video"
        self.waiting_for_filename = False
        self.start_time = None
        self.progress_tracker = ProgressTracker()

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def create_progress_bar(progress, length=20):
    filled_length = int(length * progress / 100)
    bar = '█' * filled_length + '░' * (length - filled_length)
    return bar

app = Client("video_compress_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start_command(client, message):
    welcome_text = (
        "🎥 **Welcome to Video Compression Bot!**\n\n"
        "Send me any video to start compression.\n\n"
        "Available commands:\n"
        "/start - Show this message\n"
        "/help - Show help message\n"
        "/cancel - Cancel current operation"
    )
    await message.reply_text(welcome_text)

@app.on_message(filters.video | filters.document)
async def handle_video(client, message):
    try:
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
        
        # Create resolution selection buttons
        buttons = []
        for name, value in RESOLUTIONS.items():
            buttons.append([InlineKeyboardButton(name, callback_data=f"res:{value}")])
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
        
        await message.reply_text(
            f"🎥 **Select Output Resolution**\n\n"
            f"Current file size: {format_size(file_size)}\n"
            f"Filename: {state.file_name}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_callback_query()
async def handle_callback(client, callback_query):
    try:
        data = callback_query.data
        message = callback_query.message
        
        if data == "cancel":
            await message.edit_text("❌ Operation cancelled")
            return
            
        if data.startswith("res:"):
            resolution = data.split(":")[1]
            # Create preset selection buttons
            buttons = []
            for name, value in PRESETS.items():
                buttons.append([InlineKeyboardButton(name, callback_data=f"preset:{value}")])
            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
            
            await message.edit_text(
                "⚙️ **Select Encoding Preset**\n\n"
                "Faster = Larger file size\n"
                "Slower = Better compression",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
        elif data.startswith("preset:"):
            preset = data.split(":")[1]
            # Create CRF selection buttons
            buttons = []
            for name, value in CRF_VALUES.items():
                buttons.append([InlineKeyboardButton(name, callback_data=f"crf:{value}")])
            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
            
            await message.edit_text(
                "🎯 **Select Quality (CRF Value)**\n\n"
                "Lower value = Better quality, larger size\n"
                "Higher value = Lower quality, smaller size",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
        elif data.startswith("crf:"):
            crf = data.split(":")[1]
            # Start compression
            await message.edit_text(
                "🎯 **Starting Compression**\n\n"
                "Please wait while I process your video..."
            )
            # Start the compression process
            await start_compression(client, message, crf)
            
    except Exception as e:
        await message.edit_text(f"❌ Error: {str(e)}")

async def start_compression(client, message, crf):
    try:
        # Download video
        progress_msg = await message.reply_text("📥 **Downloading video...**")
        
        input_file = f"downloads/input_{int(time.time())}.mp4"
        output_file = f"downloads/output_{int(time.time())}.mp4"
        
        await client.download_media(
            message.reply_to_message,
            input_file,
            progress=progress_callback,
            progress_args=(progress_msg, "Downloading")
        )
        
        # Start compression
        await progress_msg.edit_text("🎯 **Compressing video...**")
        
        ffmpeg_cmd = [
            "ffmpeg", "-i", input_file,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", crf,
            "-c:a", "aac",
            "-b:a", "128k",
            output_file
        ]
        
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        
        # Upload compressed video
        await progress_msg.edit_text("📤 **Uploading compressed video...**")
        
        await client.send_video(
            message.chat.id,
            output_file,
            progress=progress_callback,
            progress_args=(progress_msg, "Uploading")
        )
        
        await progress_msg.edit_text("✅ **Compression complete!**")
        
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
    finally:
        # Cleanup
        try:
            os.remove(input_file)
            os.remove(output_file)
        except:
            pass

async def progress_callback(current, total, message, action):
    try:
        progress = (current * 100) / total
        progress_bar = create_progress_bar(progress)
        
        status_text = (
            f"**{action} Video**\n\n"
            f"💫 **Progress:** {progress:.1f}%\n"
            f"{progress_bar}\n"
            f"📊 **Size:** {format_size(current)} / {format_size(total)}"
        )
        
        try:
            await message.edit_text(status_text)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            pass
            
    except Exception as e:
        print(f"Progress callback error: {str(e)}")

@app.on_message(filters.command("help"))
async def help_command(client, message):
    help_text = (
        "📖 **Video Compression Bot Help**\n\n"
        "This bot helps you compress videos with custom settings.\n\n"
        "**How to use:**\n"
        "1. Send any video file\n"
        "2. Select resolution\n"
        "3. Choose encoding preset\n"
        "4. Select quality (CRF value)\n"
        "5. Wait for compression to complete\n\n"
        "**Commands:**\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/cancel - Cancel current operation\n\n"
        "**Notes:**\n"
        "• Maximum file size: 2GB\n"
        "• Supported formats: MP4, AVI, MKV, MOV\n"
        "• Higher CRF = Smaller size but lower quality\n"
        "• Slower preset = Better compression but takes longer"
    )
    await message.reply_text(help_text)

@app.on_message(filters.command("cancel"))
async def cancel_command(client, message):
    # Implementation depends on how you want to handle cancellation
    await message.reply_text("❌ Operation cancelled")

def create_custom_menu(task_id):
    buttons = [
        [
            InlineKeyboardButton("📐 Resolution", callback_data=f"custom:{task_id}:resolution"),
            InlineKeyboardButton("⚡ Preset", callback_data=f"custom:{task_id}:preset")
        ],
        [
            InlineKeyboardButton("🎯 Quality", callback_data=f"custom:{task_id}:crf"),
            InlineKeyboardButton("✅ Confirm", callback_data=f"custom:{task_id}:confirm")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{task_id}")]
    ]
    return InlineKeyboardMarkup(buttons)

async def get_video_duration(file_path):
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            file_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        data = json.loads(stdout.decode())
        return float(data['format']['duration'])
    except Exception as e:
        print(f"Error getting video duration: {str(e)}")
        return 0

async def create_video_thumbnail(input_file, duration):
    try:
        thumbnail_path = f"downloads/thumb_{int(time.time())}.jpg"
        cmd = [
            "ffmpeg",
            "-ss", str(duration/2),
            "-i", input_file,
            "-vframes", "1",
            "-vf", "scale=320:-1",
            "-y",
            thumbnail_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        
        if os.path.exists(thumbnail_path):
            return thumbnail_path
        return None
    except Exception as e:
        print(f"Error creating thumbnail: {str(e)}")
        return None

class CompressionQueue:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.processing = False
        
    async def add_task(self, task):
        await self.queue.put(task)
        if not self.processing:
            asyncio.create_task(self.process_queue())
    
    async def process_queue(self):
        self.processing = True
        while not self.queue.empty():
            task = await self.queue.get()
            try:
                await task
            except Exception as e:
                print(f"Task error: {str(e)}")
            finally:
                self.queue.task_done()
        self.processing = False

compression_queue = CompressionQueue()

def main():
    print("🤖 Bot is starting...")
    try:
        # Create downloads directory if it doesn't exist
        os.makedirs("downloads", exist_ok=True)
        
        # Start the bot
        app.run()
    except Exception as e:
        print(f"❌ Error starting bot: {str(e)}")

if __name__ == "__main__":
    main()
