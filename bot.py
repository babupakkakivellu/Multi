import os
import logging
import asyncio
from typing import Dict, Optional
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import RPCError
from ffmpeg import FFmpeg, Progress
from ffmpeg.probe import Probe

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration
API_ID = "YOUR_API_ID"
API_HASH = "YOUR_API_HASH"
BOT_TOKEN = "YOUR_BOT_TOKEN"

# Constants
MAX_CONCURRENT_JOBS = 5  # Limit simultaneous processing
RESOLUTIONS = ["144p", "240p", "360p", "480p", "720p", "1080p", "2K", "4K"]
PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
CRF_VALUES = list(range(15, 31))
PIXEL_FORMATS = ["yuv420p", "yuv444p", "rgb24"]
CODECS = ["libx264", "libx265", "vp9"]

# Initialize Pyrogram client
app = Client("video_compress_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# User session management
class UserSession:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
        self.sessions: Dict[int, dict] = {}

    async def create_session(self, user_id: int):
        async with self.semaphore:
            self.sessions[user_id] = {
                "step": "start",
                "compression_settings": {
                    "resolution": "720p",
                    "preset": "medium",
                    "crf": 23,
                    "pixel_format": "yuv420p",
                    "codec": "libx264"
                },
                "file_info": None,
                "upload_format": None,
                "filename": None,
                "message_stack": []
            }

    def get_session(self, user_id: int) -> Optional[dict]:
        return self.sessions.get(user_id)

    async def clear_session(self, user_id: int):
        if user_id in self.sessions:
            # Cleanup temporary files if any
            session = self.sessions[user_id]
            for file in [session.get('file_path'), session.get('output_path'), session.get('thumbnail_path')]:
                if file and os.path.exists(file):
                    os.remove(file)
            del self.sessions[user_id]

user_sessions = UserSession()

# Menu builders
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Compress File", callback_data="compress")],
        [InlineKeyboardButton("🛠 Settings", callback_data="settings")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def settings_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📏 Resolution", callback_data="set_resolution")],
        [InlineKeyboardButton("⚙️ Preset", callback_data="set_preset")],
        [InlineKeyboardButton("🎚 CRF", callback_data="set_crf")],
        [InlineKeyboardButton("🎨 Pixel Format", callback_data="set_pixel_format")],
        [InlineKeyboardButton("🔌 Codec", callback_data="set_codec")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ])

def paginated_menu(items, page=0, items_per_page=8, prefix=""):
    start = page * items_per_page
    end = start + items_per_page
    buttons = []
    
    for item in items[start:end]:
        buttons.append([InlineKeyboardButton(str(item), callback_data=f"{prefix}_{item}")])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"page_{page-1}_{prefix}"))
    if end < len(items):
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"page_{page+1}_{prefix}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="settings")])
    return InlineKeyboardMarkup(buttons)

# Progress handlers
async def progress_callback(progress: Progress, status: str, message: Message):
    try:
        await message.edit_text(
            f"**{status}**\n"
            f"Progress: {progress.percent:.2f}%\n"
            f"Speed: {progress.speed}x\n"
            f"ETA: {progress.eta}"
        )
    except RPCError:
        pass

# Handle /start command
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await user_sessions.create_session(message.from_user.id)
    await message.reply_text(
        "🎥 **Video Compression Bot**\n\n"
        "Send me a video/document or choose an option:",
        reply_markup=main_menu()
    )

# Handle media messages
@app.on_message(filters.video | filters.document)
async def handle_media(client, message: Message):
    user_id = message.from_user.id
    session = user_sessions.get_session(user_id)
    
    if not session:
        await message.reply_text("❗ Please start the bot with /start first")
        return
    
    file_info = {
        "file_id": message.video.file_id if message.video else message.document.file_id,
        "file_name": message.video.file_name if message.video else message.document.file_name,
        "mime_type": message.video.mime_type if message.video else message.document.mime_type
    }
    
    session["file_info"] = file_info
    session["step"] = "compress"
    
    await message.reply_text(
        f"📁 **File Received**: {file_info['file_name']}\n"
        "Choose an action:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠 Compression Settings", callback_data="settings")],
            [InlineKeyboardButton("⚡ Start Compression", callback_data="start_compress")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
    )

# Callback query handler
@app.on_callback_query()
async def handle_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    session = user_sessions.get_session(user_id)
    
    if not session:
        await callback_query.answer("Session expired! Please start over with /start")
        return
    
    try:
        if data == "main_menu":
            await callback_query.message.edit_text(
                "🎥 **Main Menu**\nChoose an option:",
                reply_markup=main_menu()
            )
        elif data == "settings":
            await callback_query.message.edit_text(
                "⚙️ **Compression Settings**\nCurrent settings:\n"
                f"Resolution: {session['compression_settings']['resolution']}\n"
                f"Preset: {session['compression_settings']['preset']}\n"
                f"CRF: {session['compression_settings']['crf']}\n"
                f"Pixel Format: {session['compression_settings']['pixel_format']}\n"
                f"Codec: {session['compression_settings']['codec']}",
                reply_markup=settings_menu()
            )
        elif data.startswith("set_"):
            setting_type = data.split("_")[1]
            await show_setting_menu(callback_query, setting_type)
        elif data.startswith("page_"):
            _, page, prefix = data.split("_")
            await handle_pagination(callback_query, int(page), prefix)
        elif data.startswith(("res_", "preset_", "crf_", "pix_", "codec_")):
            await handle_setting_selection(callback_query, data)
        elif data == "start_compress":
            await handle_compress_start(callback_query)
        elif data == "cancel":
            await user_sessions.clear_session(user_id)
            await callback_query.message.edit_text("❌ Operation cancelled")
        else:
            await callback_query.answer("⚠️ Invalid option selected")

    except Exception as e:
        logger.error(f"Error handling callback: {str(e)}")
        await callback_query.answer("❌ An error occurred. Please try again.")

async def show_setting_menu(callback_query, setting_type):
    user_id = callback_query.from_user.id
    session = user_sessions.get_session(user_id)
    
    items = {
        "resolution": RESOLUTIONS,
        "preset": PRESETS,
        "crf": CRF_VALUES,
        "pixel": PIXEL_FORMATS,
        "codec": CODECS
    }[setting_type]
    
    prefix = {
        "resolution": "res",
        "preset": "preset",
        "crf": "crf",
        "pixel": "pix",
        "codec": "codec"
    }[setting_type]
    
    await callback_query.message.edit_text(
        f"⚙️ Select {setting_type.replace('_', ' ').title()}:",
        reply_markup=paginated_menu(items, prefix=prefix)
    )

async def handle_pagination(callback_query, page, prefix):
    items = {
        "res": RESOLUTIONS,
        "preset": PRESETS,
        "crf": CRF_VALUES,
        "pix": PIXEL_FORMATS,
        "codec": CODECS
    }[prefix]
    
    await callback_query.message.edit_text(
        f"⚙️ Select {prefix.replace('_', ' ').title()}:",
        reply_markup=paginated_menu(items, page=page, prefix=prefix)
    )

async def handle_setting_selection(callback_query, data):
    user_id = callback_query.from_user.id
    session = user_sessions.get_session(user_id)
    setting_type, value = data.split("_", 1)
    
    setting_map = {
        "res": ("resolution", value),
        "preset": ("preset", value),
        "crf": ("crf", int(value)),
        "pix": ("pixel_format", value),
        "codec": ("codec", value)
    }
    
    setting_key, setting_value = setting_map[setting_type]
    session["compression_settings"][setting_key] = setting_value
    
    await callback_query.answer(f"✅ {setting_key.title()} set to {value}")
    await callback_query.message.edit_text(
        f"⚙️ Updated {setting_key.replace('_', ' ').title()} to {value}",
        reply_markup=settings_menu()
    )

async def handle_compress_start(callback_query):
    user_id = callback_query.from_user.id
    session = user_sessions.get_session(user_id)
    
    await callback_query.message.edit_text("📤 Downloading file...")
    
    try:
        # Download file
        file_path = await callback_query.message._client.download_media(
            session["file_info"]["file_id"],
            progress=progress_callback,
            progress_args=("📥 Downloading", callback_query.message)
        )
        
        # Extract thumbnail
        thumbnail_path = f"thumb_{user_id}.jpg"
        ffmpeg_thumbnail = (
            FFmpeg()
            .input(file_path)
            .output(thumbnail_path, ss="00:00:05", vframes=1)
            .overwrite_output()
        )
        await ffmpeg_thumbnail.execute()
        
        # Process file
        output_path = f"compressed_{session['file_info']['file_name']}"
        await process_video(file_path, output_path, session, callback_query.message)
        
        # Upload file
        await upload_file(
            callback_query.message,
            output_path,
            thumbnail_path,
            session["file_info"]["file_name"],
            session.get("upload_format", "video")
        )
        
    except Exception as e:
        logger.error(f"Compression error: {str(e)}")
        await callback_query.message.edit_text(f"❌ Error during processing: {str(e)}")
    finally:
        # Cleanup
        for path in [file_path, output_path, thumbnail_path]:
            if path and os.path.exists(path):
                os.remove(path)
        await user_sessions.clear_session(user_id)

async def process_video(input_path, output_path, session, message):
    settings = session["compression_settings"]
    
    ffmpeg = (
        FFmpeg()
        .input(input_path)
        .output(
            output_path,
            vcodec=settings["codec"],
            crf=settings["crf"],
            preset=settings["preset"],
            pix_fmt=settings["pixel_format"],
            **get_resolution_args(settings["resolution"])
        )
        .overwrite_output()
    )
    
    await ffmpeg.execute(
        progress=progress_callback,
        progress_args=("🔧 Compressing", message)
    )

async def upload_file(message, file_path, thumb_path, filename, upload_format):
    probe = Probe(file_path)
    video_stream = next((s for s in probe.streams if s.type == "video"), None)
    
    upload_args = {
        "thumb": thumb_path,
        "caption": filename,
        "duration": int(float(video_stream.duration)) if video_stream else 0,
        "width": video_stream.width if video_stream else 0,
        "height": video_stream.height if video_stream else 0
    }
    
    if upload_format == "video":
        await message.reply_video(file_path, **upload_args)
    else:
        await message.reply_document(file_path, **upload_args)

def get_resolution_args(resolution):
    resolutions = {
        "144p": (256, 144),
        "240p": (426, 240),
        "360p": (640, 360),
        "480p": (854, 480),
        "720p": (1280, 720),
        "1080p": (1920, 1080),
        "2K": (2560, 1440),
        "4K": (3840, 2160)
    }
    w, h = resolutions.get(resolution, (1280, 720))
    return {"vf": f"scale={w}:{h}"}

if __name__ == "__main__":
    app.run()
