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

async def progress_callback(current, total, message, start_time, action):
    try:
        now = time.time()
        
        # Only update every 3 seconds to avoid FloodWait
        if hasattr(message, 'last_update') and (now - message.last_update) < 3:
            return
        message.last_update = now

        text = f"⏳ **{action}...**"
        
        try:
            await message.edit_text(text)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            
    except Exception as e:
        print(f"Progress callback error: {str(e)}")

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
        task_id = str(int(time.time()))  # Unique task ID based on timestamp
        
        if compression_tasks.get_user_tasks_count(user_id) >= compression_tasks.max_tasks:
            await message.reply_text(
                f"⚠️ Maximum concurrent tasks ({compression_tasks.max_tasks}) reached.\n"
                "Please wait for some tasks to complete first."
            )
            return
        
        state = CompressionState()
        
        if message.video:
            state.file_id = message.video.file_id
            state.file_name = message.video.file_name or "video.mp4"
            file_size = message.video.file_size
            duration = message.video.duration
            width = message.video.width
            height = message.video.height
        else:
            if not message.document.mime_type or not message.document.mime_type.startswith("video/"):
                await message.reply_text("❌ Please send a valid video file.")
                return
                
            state.file_id = message.document.file_id
            state.file_name = message.document.file_name or "video.mp4"
            file_size = message.document.file_size
            duration = 0
            width = height = 0
        
        if file_size > 2_000_000_000:  # 2GB limit
            await message.reply_text("❌ File too large. Maximum size: 2GB")
            return
        
        state.message = message
        state.task_id = task_id
        
        if compression_tasks.add_task(user_id, task_id, state):
            info_text = (
                f"🎥 **Video Information**\n\n"
                f"📁 **Filename:** `{state.file_name}`\n"
                f"💾 **Size:** {format_size(file_size)}\n"
                f"⏱️ **Duration:** {duration} seconds\n"
                f"📐 **Resolution:** {width}x{height}\n\n"
                "**Choose a Compression Theme:**"
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

@app.on_message(filters.command("cancel"))
async def cancel_command(client, message):
    user_id = message.from_user.id
    if user_id in compression_tasks.tasks:
        for task_id in list(compression_tasks.tasks[user_id].keys()):
            compression_tasks.remove_task(user_id, task_id)
        await message.reply_text(
            "✅ **All Compression Tasks Cancelled**\n\n"
            "Send another video to start again!"
        )
    else:
        await message.reply_text(
            "❌ **No Active Compression**\n\n"
            "Send a video to start compression!"
        )

@app.on_message(filters.text & filters.private)
async def handle_filename(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        
        # Find the user's task that's waiting for filename
        user_tasks = compression_tasks.tasks.get(user_id, {})
        active_task = None
        task_id = None
        
        for tid, task in user_tasks.items():
            if task.waiting_for_filename:
                active_task = task
                task_id = tid
                break
        
        if not active_task:
            return
        
        if message.text == "/skip":
            active_task.custom_name = active_task.file_name
        else:
            active_task.custom_name = message.text
            if not any(active_task.custom_name.lower().endswith(ext) 
                      for ext in ['.mp4', '.mkv', '.avi', '.mov']):
                active_task.custom_name += '.mp4'
        
        await message.reply_text(
            "🎯 **Starting Compression**\n\n"
            "Please wait while I process your video..."
        )
        await start_compression(client, active_task)
        
    except Exception as e:
        error_text = f"❌ Error processing filename: {str(e)}"
        print(error_text)
        await message.reply_text(error_text)
        if task_id:
            compression_tasks.remove_task(user_id, task_id)

@app.on_callback_query()
async def handle_callback(client: Client, callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        data = callback.data
        
        # Extract task_id from callback data
        if ":" not in data:
            await callback.answer("Invalid callback data", show_alert=True)
            return
            
        action, task_id, *params = data.split(":")
        state = compression_tasks.get_task(user_id, task_id)
        
        if not state:
            await callback.answer("Task not found or expired", show_alert=True)
            return
        
        if action == "cancel":
            compression_tasks.remove_task(user_id, task_id)
            await callback.message.edit_text("❌ Operation cancelled.")
            return
        
        elif action == "theme":
            theme_id = params[0]
            if theme_id == "custom":
                await callback.message.edit_text(
                    "⚙️ **Custom Compression Settings**\n\n"
                    "Select what you want to configure:",
                    reply_markup=create_custom_menu(task_id)
                )
            else:
                theme = THEMES[theme_id]
                state.resolution = theme["resolution"]
                state.preset = theme["preset"]
                state.crf = theme["crf"]
                state.codec = theme["codec"]
                state.pixel_format = theme["pixel_format"]
                
                await show_format_selection(callback.message, theme["name"], task_id)
        
        elif action == "custom":
            setting = params[0]
            if setting == "resolution":
                buttons = [[InlineKeyboardButton(name, callback_data=f"res:{task_id}:{value}")] 
                          for name, value in RESOLUTIONS.items()]
                buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"custom:{task_id}:back")])
                await callback.message.edit_text(
                    "📐 **Select Output Resolution:**\n\n"
                    "Lower resolution = Smaller file size\n"
                    "Higher resolution = Better quality",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif setting == "preset":
                buttons = [[InlineKeyboardButton(name, callback_data=f"preset:{task_id}:{value}")] 
                          for name, value in PRESETS.items()]
                buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"custom:{task_id}:back")])
                await callback.message.edit_text(
                    "⚡ **Select Encoding Preset:**\n\n"
                    "Faster = Larger file size\n"
                    "Slower = Better compression",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif setting == "crf":
                buttons = [[InlineKeyboardButton(name, callback_data=f"crf:{task_id}:{value}")] 
                          for name, value in CRF_VALUES.items()]
                buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"custom:{task_id}:back")])
                await callback.message.edit_text(
                    "🎯 **Select Quality (CRF Value):**\n\n"
                    "Lower value = Better quality, larger size\n"
                    "Higher value = Lower quality, smaller size",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif setting == "confirm":
                await show_format_selection(callback.message, "Custom Settings", task_id)
            
            elif setting == "back":
                await callback.message.edit_text(
                    "⚙️ **Custom Compression Settings**\n\n"
                    "Select what you want to configure:",
                    reply_markup=create_custom_menu(task_id)
                )
        
        elif action in ["res", "preset", "crf"]:
            value = params[0]
            if action == "res":
                state.resolution = value
            elif action == "preset":
                state.preset = value
            elif action == "crf":
                state.crf = value
            
            await callback.message.edit_text(
                "⚙️ **Custom Compression Settings**\n\n"
                f"Current Settings:\n"
                f"• Resolution: {state.resolution}\n"
                f"• Preset: {state.preset}\n"
                f"• CRF: {state.crf}\n\n"
                "Select what you want to configure:",
                reply_markup=create_custom_menu(task_id)
            )
        
        elif action == "format":
            state.output_format = params[0]
            await callback.message.edit_text(
                "📝 **Enter Custom Filename**\n\n"
                "• Send new filename\n"
                "• Or send /skip to keep original name\n\n"
                "Note: Include file extension (.mp4, .mkv, etc.)"
            )
            state.waiting_for_filename = True
        
        await callback.answer()
        
    except Exception as e:
        error_text = f"❌ Callback error: {str(e)}"
        print(error_text)
        await callback.answer(error_text, show_alert=True)
        if user_id in compression_tasks.tasks and task_id in compression_tasks.tasks[user_id]:
            compression_tasks.remove_task(user_id, task_id)

async def start_compression(client: Client, state: CompressionState):
    progress_msg = await state.message.reply_text("⚙️ **Initializing...**")
    start_time = time.time()
    input_file = output_file = thumbnail = None
    
    try:
        # Download video
        try:
            await progress_msg.edit_text("📥 **Downloading...**")
            input_file = await client.download_media(
                state.file_id,
                progress=progress_callback,
                progress_args=(progress_msg, start_time, "Downloading")
            )
            
            if not input_file:
                raise Exception("Download failed")
            
        except FloodWait as e:
            await progress_msg.edit_text(f"⚠️ Rate limited. Waiting {e.value} seconds...")
            await asyncio.sleep(e.value)
            raise Exception("Download retry needed")
        except Exception as e:
            raise Exception(f"Download failed: {str(e)}")

        # Get video information and create thumbnail
        await progress_msg.edit_text("🔍 **Analyzing...**")
        
        try:
            # Get video information using FFprobe
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
            await progress_msg.edit_text("🖼️ **Processing thumbnail...**")
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
            
            if not os.path.exists(thumbnail):
                print("Thumbnail extraction failed, continuing without thumbnail")
                thumbnail = None
            
        except Exception as e:
            print(f"Video info/thumbnail error: {str(e)}")
            duration = 0
            thumbnail = None

        # Start compression
        output_file = f"compressed_{state.custom_name}"
        await progress_msg.edit_text("🎯 **Compressing...**")

        # FFmpeg compression command
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

        # Start compression process
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        await process.communicate()

        if not os.path.exists(output_file):
            raise Exception("Compression failed")

        # Get file sizes for comparison
        original_size = os.path.getsize(input_file)
        compressed_size = os.path.getsize(output_file)

        # Upload the compressed video
        await progress_msg.edit_text("📤 **Uploading...**")
        
        try:
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
                    caption=caption,
                    progress=progress_callback,
                    progress_args=(progress_msg, start_time, "Uploading")
                )
            else:
                await client.send_document(
                    state.message.chat.id,
                    output_file,
                    thumb=thumbnail,
                    caption=caption,
                    progress=progress_callback,
                    progress_args=(progress_msg, start_time, "Uploading")
                )

            await progress_msg.edit_text(
                "✅ **Compression Complete!**\n\n"
                f"📊 **Results:**\n"
                f"• Original: {format_size(original_size)}\n"
                f"• Compressed: {format_size(compressed_size)}\n"
                f"• Space Saved: {((original_size - compressed_size) / original_size) * 100:.1f}%\n\n"
                "🔄 Send another video to compress again!"
            )

        except FloodWait as e:
            await progress_msg.edit_text(f"⚠️ Upload rate limited. Waiting {e.value} seconds...")
            await asyncio.sleep(e.value)
            raise Exception("Upload retry needed")
        except Exception as e:
            raise Exception(f"Upload failed: {str(e)}")

    except Exception as main_error:
        error_text = (
            "❌ **Compression Failed**\n\n"
            f"Error: `{str(main_error)}`\n\n"
            "Please try again or contact support."
        )
        await progress_msg.edit_text(error_text)
        
    finally:
        # Cleanup
        try:
            for file in [input_file, output_file, thumbnail]:
                if file and os.path.exists(file):
                    os.remove(file)
        except Exception as e:
            print(f"Cleanup error: {str(e)}")
        
        # Clear task
        if state.message.from_user.id in compression_tasks.tasks:
            compression_tasks.remove_task(state.message.from_user.id, state.task_id)

# Start the bot
print("🤖 Bot is running...")
app.run() 
