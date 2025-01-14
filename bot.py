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
OWNER_ID = 5422016608
AUTHORIZED_USERS = {
    OWNER_ID,  # Owner ID
    5422016608, # Other authorized user IDs
}

# Initialize and start the bot
app = Client(
    "video_compress_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Global progress lock
progress_lock = asyncio.Lock()
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
    "15": "15",
    "16": "16",
    "17": "17",
    "18": "18",
    "19": "19",
    "20": "20",
    "21": "21",
    "22": "22",
    "23": "23",
    "24": "24",
    "25": "25",
    "26": "26",
    "27": "27"
}

THEMES = {
    "480p": {
        "name": "Low Quality",
        "resolution": "480x360",
        "preset": "fast",
        "crf": "24",
        "codec": "libx265",
        "pixel_format": "yuv420p10le",
        "description": "Good But 480p"
    },
    "720p": {
        "name": "Medium Quality",
        "resolution": "720x480",
        "preset": "fast",
        "crf": "24",
        "codec": "libx265",
        "pixel_format": "yuv420p10le",
        "description": "Better"
    },
    "1080p": {
        "name": "High Quality",
        "resolution": "1920x1080",
        "preset": "fast",
        "crf": "14",
        "codec": "libx265",
        "pixel_format": "yuv420p10le",
        "description": "High Quality"
    }
}

# Helper Classes
class CompressionState:
    def __init__(self):
        self.file_id = None
        self.file_name = None
        self.message = None
        self.task_id = None
        self.resolution = "1280x720"
        self.preset = "fast"
        self.crf = "24"
        self.codec = "libx265"
        self.pixel_format = "yuv420p10le"
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

# Helper Functions
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
        elapsed_time = now - start_time

        # Calculate percentage
        percentage = (current / total) * 100 if total else 0
        percentage = round(percentage, 1)

        # Calculate speed and ETA
        speed = current / elapsed_time if elapsed_time > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0

        # Progress bar
        progress_bar = f"[{'█' * int(percentage // 5):<20}]"

        # Create status message
        status_text = (
            f"⏳ **{action}**\n"
            f"{progress_bar} {percentage:.1f}%\n"
            f"🔄 **Speed:** {format_size(speed)}/s\n"
            f"⏱️ **Elapsed:** {elapsed_time:.1f}s | **ETA:** {eta:.1f}s\n"
            f"📊 **Total:** {format_size(total)} | **Done:** {format_size(current)}"
        )

        # Update message only if significant change (avoid spamming)
        if not hasattr(message, 'last_percentage') or abs(message.last_percentage - percentage) >= 1:
            message.last_percentage = percentage
            await message.edit_text(status_text)

    except Exception as e:
        print(f"Progress callback error: {str(e)}")

# UI Components
def create_theme_menu(task_id):
    buttons = [
        [
            InlineKeyboardButton("480p 10bit", callback_data=f"theme:{task_id}:480p"),
            InlineKeyboardButton("720p 10bit", callback_data=f"theme:{task_id}:720p")
        ],
        [
            InlineKeyboardButton("1080p 10bit", callback_data=f"theme:{task_id}:1080p"),
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

def create_resolution_menu(task_id):
    buttons = [[InlineKeyboardButton(name, callback_data=f"res:{task_id}:{value}")] 
              for name, value in RESOLUTIONS.items()]
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"custom:{task_id}:back")])
    return InlineKeyboardMarkup(buttons)

def create_preset_menu(task_id):
    buttons = [[InlineKeyboardButton(name, callback_data=f"preset:{task_id}:{value}")] 
              for name, value in PRESETS.items()]
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"custom:{task_id}:back")])
    return InlineKeyboardMarkup(buttons)

def create_crf_menu(task_id):
    buttons = [[InlineKeyboardButton(name, callback_data=f"crf:{task_id}:{value}")] 
              for name, value in CRF_VALUES.items()]
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"custom:{task_id}:back")])
    return InlineKeyboardMarkup(buttons)

async def show_settings_summary(message, state, task_id):
    text = (
        "⚙️ **Current Settings**\n\n"
        f"📐 Resolution: `{state.resolution}`\n"
        f"⚡ Preset: `{state.preset}`\n"
        f"🎯 CRF Value: `{state.crf}`\n"
        f"🎬 Codec: `{state.codec}`\n"
        f"🎨 Pixel Format: `{state.pixel_format}`\n\n"
        "Select an option to modify:"
    )
    await message.edit_text(text, reply_markup=create_custom_menu(task_id))

def authorized_users_only(func):
    async def wrapper(client, message):
        user_id = message.from_user.id
        if user_id not in AUTHORIZED_USERS:
            await message.reply_text(
                "⚠️ **Unauthorized Access**\n\n"
                "You are not authorized to use this bot."
                "Contact :- @Blaster_ONFR For Access."
            )
            return
        return await func(client, message)
    return wrapper

# Message Handlers
@app.on_message(filters.command("start"))
@authorized_users_only
async def start_command(client, message):
    try:
        welcome_text = (
            "🎥 **Welcome to Video Compression Bot!**\n\n"
            "I can help you compress videos with various settings:\n\n"
            "📱 **480p 10bit**\n"
            "• Smallest file size\n"
            "• Good for mobile data\n\n"
            "📬 **720p 10bit**\n"
            "• Balanced quality\n"
            "• Perfect for sharing\n\n"
            "🎯 **1080p 10bit**\n"
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
@authorized_users_only
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

@app.on_callback_query()
async def handle_callback(client: Client, callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        data = callback.data
        
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
                await callback.message.edit_text(
                    "📐 **Select Output Resolution:**\n\n"
                    "Lower resolution = Smaller file size\n"
                    "Higher resolution = Better quality",
                    reply_markup=create_resolution_menu(task_id)
                )
            
            elif setting == "preset":
                await callback.message.edit_text(
                    "⚡ **Select Encoding Preset:**\n\n"
                    "Faster = Larger file size\n"
                    "Slower = Better compression",
                    reply_markup=create_preset_menu(task_id)
                )
            
            elif setting == "crf":
                await callback.message.edit_text(
                    "🎯 **Select Quality (CRF Value):**\n\n"
                    "Lower value = Better quality, larger size\n"
                    "Higher value = Lower quality, smaller size",
                    reply_markup=create_crf_menu(task_id)
                )
            
            elif setting == "confirm":
                await show_format_selection(callback.message, "Custom Settings", task_id)
            
            elif setting == "back":
                await show_settings_summary(callback.message, state, task_id)
        
        elif action in ["res", "preset", "crf"]:
            value = params[0]
            if action == "res":
                state.resolution = value
            elif action == "preset":
                state.preset = value
            elif action == "crf":
                state.crf = value
            
            await show_settings_summary(callback.message, state, task_id)
        
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


@app.on_message(filters.text & filters.private)
async def handle_filename(client: Client, message: Message):
    try:
        user_id = message.from_user.id
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

async def start_compression(client: Client, state: CompressionState):
    progress_msg = await state.message.reply_text("⚙️ **Initializing...**")
    start_time = time.time()
    input_file = output_file = thumbnail = None
    
    try:
        # Download video
        try:
            await progress_msg.edit_text("📥 **Downloading: 0%**")
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
        await progress_msg.edit_text("🔍 **Analyzing Video...**")
        
        try:
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
            
            if not os.path.exists(thumbnail):
                print("Thumbnail extraction failed, continuing without thumbnail")
                thumbnail = None
            
        except Exception as e:
            print(f"Video info/thumbnail error: {str(e)}")
            duration = 0
            thumbnail = None

        # Start compression
        output_file = f"compressed_{state.custom_name}"
        await progress_msg.edit_text("🎯 **Compressing: 0%**")

        ffmpeg_cmd = [
            "ffmpeg", "-i", input_file,
            "-hide_banner", "-ignore_unknown",
            "-c:v", state.codec,
            "-preset", state.preset,
            "-crf", str(state.crf),
            "-vf", f"scale={state.resolution}",
            "-pix_fmt", state.pixel_format,
            "-c:a", "copy",
            "-c:s", "copy",
            "-map", "0:v",
            "-map", "0:a",
            "-map", "0:s?",
            "-y",
            output_file
        ]

        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        await process.communicate()

        if not os.path.exists(output_file):
            raise Exception("Compression failed")

        original_size = os.path.getsize(input_file)
        compressed_size = os.path.getsize(output_file)

        await progress_msg.edit_text("📤 **Uploading: 0%**")
        
        try:
            caption = f"**{state.custom_name}**\n"

            if state.output_format == "video":
                await client.send_video(
                    state.message.chat.id,
                    output_file,
                    thumb=thumbnail,
                    duration=int(duration),
                    caption=caption,
                    progress=progress_callback,
                    progress_args=(progress_msg, time.time(), "Uploading")
                )
            else:
                await client.send_document(
                    state.message.chat.id,
                    output_file,
                    thumb=thumbnail,
                    caption=caption,
                    progress=progress_callback,
                    progress_args=(progress_msg, time.time(), "Uploading")
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

@app.on_message(filters.command("cancel"))
@authorized_users_only
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

# Clear task after compression
        if state.message.from_user.id in compression_tasks.tasks:
            compression_tasks.remove_task(state.message.from_user.id, state.task_id)

print("🤖 Bot is running...")
app.run()
