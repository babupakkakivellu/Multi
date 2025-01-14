import os
import time
import asyncio
import subprocess
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    Message, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery
)
from pyrogram.errors import FloodWait

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
        self.resolution = "720x480"
        self.preset = "medium"
        self.crf = "23"
        self.codec = "libx264"
        self.pixel_format = "yuv420p"
        self.custom_name = None
        self.output_format = "video"
        self.waiting_for_filename = False
        self.start_time = None
        self.progress_message = None

user_states = {}

app = Client("video_compress_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def create_progress_bar(current, total, length=20):
    filled_length = int(length * current // total)
    bar = '█' * filled_length + '░' * (length - filled_length)
    return bar

def create_theme_menu():
    buttons = [
        [
            InlineKeyboardButton("📱 Mobile Saver", callback_data="theme:mobile"),
            InlineKeyboardButton("📬 Telegram", callback_data="theme:telegram")
        ],
        [
            InlineKeyboardButton("🎯 High Quality", callback_data="theme:high"),
            InlineKeyboardButton("⚙️ Custom", callback_data="theme:custom")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(buttons)

def create_custom_menu():
    buttons = [
        [InlineKeyboardButton("📐 Resolution", callback_data="custom:resolution")],
        [InlineKeyboardButton("⚡ Preset", callback_data="custom:preset")],
        [InlineKeyboardButton("🎯 Quality (CRF)", callback_data="custom:crf")],
        [InlineKeyboardButton("✅ Confirm Settings", callback_data="custom:confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.command("start"))
async def start_command(client, message):
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

@app.on_message(filters.video | filters.document)
async def handle_video(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id in user_states:
        await message.reply_text(
            "⚠️ You have an ongoing compression task.\n"
            "Please wait for it to complete or cancel it."
        )
        return
    
    user_states[user_id] = CompressionState()
    state = user_states[user_id]
    
    try:
        if message.video:
            state.file_id = message.video.file_id
            state.file_name = message.video.file_name
            file_size = message.video.file_size
            duration = message.video.duration
            width = message.video.width
            height = message.video.height
        else:
            if not message.document.mime_type.startswith("video/"):
                await message.reply_text("❌ Please send a video file.")
                del user_states[user_id]
                return
                
            state.file_id = message.document.file_id
            state.file_name = message.document.file_name
            file_size = message.document.file_size
            duration = 0
            width = height = 0
        
        if file_size > 2_000_000_000:  # 2GB limit
            await message.reply_text("❌ File too large. Maximum size: 2GB")
            del user_states[user_id]
            return
        
        state.message = message
        
        info_text = (
            "📽️ **Video Information**\n\n"
            f"📁 **Filename:** `{state.file_name}`\n"
            f"💾 **Size:** {format_size(file_size)}\n"
            f"⏱️ **Duration:** {duration} seconds\n"
            f"📐 **Resolution:** {width}x{height}\n\n"
            "**Choose a Compression Theme:**"
        )
        
        await message.reply_text(
            info_text,
            reply_markup=create_theme_menu()
        )
    
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
        if user_id in user_states:
            del user_states[user_id]

@app.on_callback_query()
async def handle_callback(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    if user_id not in user_states:
        await callback.answer("⚠️ Session expired. Please send the video again.", show_alert=True)
        return
    
    state = user_states[user_id]
    
    try:
        if data == "cancel":
            await callback.message.edit_text("❌ Operation cancelled.")
            del user_states[user_id]
            return
        
        elif data.startswith("theme:"):
            theme_id = data.split(":")[1]
            if theme_id == "custom":
                await callback.message.edit_text(
                    "⚙️ **Custom Compression Settings**\n\n"
                    "Select what you want to configure:",
                    reply_markup=create_custom_menu()
                )
            else:
                theme = THEMES[theme_id]
                state.resolution = theme["resolution"]
                state.preset = theme["preset"]
                state.crf = theme["crf"]
                state.codec = theme["codec"]
                state.pixel_format = theme["pixel_format"]
                
                await show_format_selection(callback.message, theme["name"])
        
        elif data.startswith("custom:"):
            action = data.split(":")[1]
            if action == "resolution":
                buttons = [[InlineKeyboardButton(name, callback_data=f"res:{value}")] 
                          for name, value in RESOLUTIONS.items()]
                buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="custom:back")])
                await callback.message.edit_text(
                    "📐 **Select Output Resolution:**\n\n"
                    "Lower resolution = Smaller file size\n"
                    "Higher resolution = Better quality",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif action == "preset":
                buttons = [[InlineKeyboardButton(name, callback_data=f"preset:{value}")] 
                          for name, value in PRESETS.items()]
                buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="custom:back")])
                await callback.message.edit_text(
                    "⚡ **Select Encoding Preset:**\n\n"
                    "Faster = Larger file size\n"
                    "Slower = Better compression",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif action == "crf":
                buttons = [[InlineKeyboardButton(name, callback_data=f"crf:{value}")] 
                          for name, value in CRF_VALUES.items()]
                buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="custom:back")])
                await callback.message.edit_text(
                    "🎯 **Select Quality (CRF Value):**\n\n"
                    "Lower value = Better quality, larger size\n"
                    "Higher value = Lower quality, smaller size",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif action == "confirm":
                await show_format_selection(callback.message, "Custom Settings")
            
            elif action == "back":
                await callback.message.edit_text(
                    "⚙️ **Custom Compression Settings**\n\n"
                    "Select what you want to configure:",
                    reply_markup=create_custom_menu()
                )
        
        elif data.startswith(("res:", "preset:", "crf:")):
            setting_type, value = data.split(":")
            if setting_type == "res":
                state.resolution = value
            elif setting_type == "preset":
                state.preset = value
            elif setting_type == "crf":
                state.crf = value
            
            await callback.message.edit_text(
                "⚙️ **Custom Compression Settings**\n\n"
                f"Current Settings:\n"
                f"• Resolution: {state.resolution}\n"
                f"• Preset: {state.preset}\n"
                f"• CRF: {state.crf}\n\n"
                "Select what you want to configure:",
                reply_markup=create_custom_menu()
            )
        
        elif data.startswith("format:"):
            state.output_format = data.split(":")[1]
            await callback.message.edit_text(
                "📝 **Enter Custom Filename**\n\n"
                "• Send new filename\n"
                "• Or send /skip to keep original name\n\n"
                "Note: Include file extension (.mp4, .mkv, etc.)"
            )
            state.waiting_for_filename = True
        
        await callback.answer()
    
    except Exception as e:
        await callback.answer(f"Error: {str(e)}", show_alert=True)
        if user_id in user_states:
            del user_states[user_id]

async def show_format_selection(message, theme_name):
    buttons = [
        [
            InlineKeyboardButton("📹 Video", callback_data="format:video"),
            InlineKeyboardButton("📄 Document", callback_data="format:document")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    await message.edit_text(
        f"🎯 **Selected: {theme_name}**\n\n"
        "Choose output format:\n\n"
        "📹 **Video** - Send as video message\n"
        "📄 **Document** - Send as file",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_message(filters.text & filters.private)
async def handle_filename(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_states or not user_states[user_id].waiting_for_filename:
        return
    
    state = user_states[user_id]
    
    try:
        if message.text == "/skip":
            state.custom_name = state.file_name
        else:
            state.custom_name = message.text
            if not any(state.custom_name.lower().endswith(ext) 
                      for ext in ['.mp4', '.mkv', '.avi', '.mov']):
                state.custom_name += '.mp4'
        
        await message.reply_text(
            "🎯 **Starting Compression Process**\n\n"
            "Please wait while I process your video..."
        )
        await start_compression(client, state)
    
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
        if user_id in user_states:
            del user_states[user_id]

async def progress_callback(current, total, message, start_time, action):
    try:
        now = time.time()
        elapsed_time = now - start_time
        speed = current / elapsed_time if elapsed_time > 0 else 0
        progress = (current / total) * 100
        eta = (total - current) / speed if speed > 0 else 0
        
        progress_bar = create_progress_bar(current, total)
        
        text = (
            f"**{action}**\n\n"
            f"💫 **Progress:** {progress:.1f}%\n"
            f"{progress_bar}\n"
            f"⚡ **Speed:** {format_size(speed)}/s\n"
            f"⏱️ **Elapsed:** {time.strftime('%H:%M:%S', time.gmtime(elapsed_time))}\n"
            f"⏳ **ETA:** {time.strftime('%H:%M:%S', time.gmtime(eta))}\n"
            f"📊 **Size:** {format_size(current)} / {format_size(total)}"
        )
        
        await message.edit_text(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        print(f"Progress callback error: {str(e)}")

async def start_compression(client: Client, state: CompressionState):
    progress_msg = await state.message.reply_text("⚙️ **Initializing compression...**")
    start_time = time.time()
    
    try:
        # Download video
        await progress_msg.edit_text("📥 **Starting download...**")
        input_file = await client.download_media(
            state.file_id,
            progress=progress_callback,
            progress_args=(progress_msg, start_time, "Downloading")
        )
        
        # Extract thumbnail
        await progress_msg.edit_text("🖼️ **Extracting thumbnail...**")
        thumbnail = f"thumb_{os.path.basename(input_file)}.jpg"
        
        try:
            duration = float(subprocess.check_output([
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", input_file
            ]).decode('utf-8').strip())
            
            subprocess.run([
                "ffmpeg", "-ss", str(duration/2), "-i", input_file,
                "-vframes", "1", "-f", "image2", thumbnail
            ], check=True)
        except Exception as e:
            print(f"Thumbnail extraction error: {str(e)}")
            thumbnail = None
        
        # Start compression
        output_file = f"compressed_{state.custom_name}"
        
        compression_text = (
            "🎯 **Compressing Video**\n\n"
            f"⚙️ **Settings:**\n"
            f"• Resolution: {state.resolution}\n"
            f"• Preset: {state.preset}\n"
            f"• CRF: {state.crf}\n"
            f"• Codec: {state.codec}\n"
            f"• Format: {state.pixel_format}\n\n"
            "Please wait..."
        )
        await progress_msg.edit_text(compression_text)
        
        ffmpeg_cmd = [
            "ffmpeg", "-i", input_file,
            "-c:v", state.codec,
            "-preset", state.preset,
            "-crf", str(state.crf),
            "-vf", f"scale={state.resolution}",
            "-pix_fmt", state.pixel_format,
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
        
        if process.returncode != 0:
            raise Exception("FFmpeg compression failed")
        
        # Upload compressed video
        await progress_msg.edit_text("📤 **Starting upload...**")
        
        upload_start_time = time.time()
        if state.output_format == "video":
            await client.send_video(
                state.message.chat.id,
                output_file,
                thumb=thumbnail,
                duration=int(duration) if 'duration' in locals() else 0,
                caption = (
            f"🎥 **{state.custom_name}**\n\n"
            f"🎯 **Compression Info:**\n"
            f"• Resolution: {state.resolution}\n"
            f"• Preset: {state.preset}\n"
            f"• CRF: {state.crf}\n"
            f"• Codec: {state.codec}\n\n"
            f"🤖 @YourBotUsername"
        )

        try:
            if state.output_format == "video":
                await client.send_video(
                    state.message.chat.id,
                    output_file,
                    thumb=thumbnail,
                    duration=int(duration) if 'duration' in locals() else 0,
                    caption=caption,
                    progress=progress_callback,
                    progress_args=(progress_msg, upload_start_time, "Uploading")
                )
            else:
                await client.send_document(
                    state.message.chat.id,
                    output_file,
                    thumb=thumbnail,
                    caption=caption,
                    progress=progress_callback,
                    progress_args=(progress_msg, upload_start_time, "Uploading")
                )

            # Show completion statistics
            original_size = os.path.getsize(input_file)
            compressed_size = os.path.getsize(output_file)
            compression_ratio = ((original_size - compressed_size) / original_size) * 100
            time_taken = time.time() - start_time

            completion_text = (
                "✅ **Compression Complete!**\n\n"
                f"📊 **Statistics:**\n"
                f"• Original Size: {format_size(original_size)}\n"
                f"• Compressed Size: {format_size(compressed_size)}\n"
                f"• Space Saved: {compression_ratio:.1f}%\n"
                f"• Time Taken: {time.strftime('%H:%M:%S', time.gmtime(time_taken))}\n\n"
                "🔄 Send another video to compress again!"
            )
            await progress_msg.edit_text(completion_text)

        except FloodWait as e:
            await asyncio.sleep(e.value)
            raise Exception("Upload failed due to Telegram flood wait")
        
        except Exception as e:
            raise Exception(f"Upload failed: {str(e)}")

    except Exception as e:
        error_text = (
            "❌ **Compression Failed**\n\n"
            f"Error: `{str(e)}`\n\n"
            "Please try again or contact support."
        )
        await progress_msg.edit_text(error_text)

    finally:
        # Cleanup
        try:
            if 'input_file' in locals():
                os.remove(input_file)
            if 'output_file' in locals():
                os.remove(output_file)
            if 'thumbnail' in locals() and thumbnail and os.path.exists(thumbnail):
                os.remove(thumbnail)
        except Exception as e:
            print(f"Cleanup error: {str(e)}")
        
        # Clear user state
        if state.message.from_user.id in user_states:
            del user_states[state.message.from_user.id]

# Add error handler
@app.on_error()
async def error_handler(client: Client, e: Exception):
    print(f"Bot error: {str(e)}")

# Add help command
@app.on_message(filters.command("help"))
async def help_command(client, message):
    help_text = (
        "📖 **Video Compression Bot Help**\n\n"
        "Here's how to use me:\n\n"
        "1️⃣ Send me any video\n\n"
        "2️⃣ Choose compression theme:\n"
        "• 📱 Mobile Data Saver\n"
        "• 📬 Telegram Optimized\n"
        "• 🎯 High Quality\n"
        "• ⚙️ Custom Settings\n\n"
        "3️⃣ For custom settings, you can configure:\n"
        "• 📐 Resolution\n"
        "• ⚡ Encoding Speed\n"
        "• 🎯 Quality Level\n\n"
        "4️⃣ Choose output format:\n"
        "• 📹 Video Message\n"
        "• 📄 Document\n\n"
        "5️⃣ Optional: Set custom filename\n\n"
        "Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/cancel - Cancel ongoing compression\n\n"
        "💡 Tips:\n"
        "• Lower resolution = Smaller file size\n"
        "• Higher CRF = Lower quality but smaller size\n"
        "• Slower preset = Better compression\n\n"
        "For support, contact @YourUsername"
    )
    await message.reply_text(help_text)

# Add cancel command
@app.on_message(filters.command("cancel"))
async def cancel_command(client, message):
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
        await message.reply_text(
            "✅ **Compression Cancelled**\n\n"
            "Send another video to start again!"
        )
    else:
        await message.reply_text(
            "❌ **No Active Compression**\n\n"
            "Send a video to start compression!"
        )

# Add status command
@app.on_message(filters.command("status"))
async def status_command(client, message):
    active_tasks = len(user_states)
    status_text = (
        "🤖 **Bot Status**\n\n"
        f"• Active Tasks: {active_tasks}\n"
        f"• Bot Uptime: {time.strftime('%H:%M:%S', time.gmtime(time.time() - bot_start_time))}\n"
        "• Status: Operational ✅"
    )
    await message.reply_text(status_text)

# Initialize bot start time
bot_start_time = time.time()

print("🤖 Bot is running...")
app.run()
