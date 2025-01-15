from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import os
import time
import re
import asyncio
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot Configuration
API_ID = "16501053"
API_HASH = "d8c9b01c863dabacc484c2c06cdd0f6e"
BOT_TOKEN = "8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I"

# Initialize your Telegram bot
app = Client(
    "video_compression_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Store user states and settings
user_states = {}
compression_settings = {}

# Compression options
RESOLUTIONS = {
    "144p": "256x144",
    "240p": "426x240",
    "360p": "640x360",
    "480p": "854x480",
    "720p": "1280x720",
    "1080p": "1920x1080",
    "2K": "2560x1440",
    "4K": "3840x2160"
}

PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
PIXEL_FORMATS = ["yuv420p", "yuv444p", "yuv422p"]
CODECS = {
    "H.264": "libx264",
    "H.265": "libx265"
}

class ProgressTracker:
    def __init__(self, message, filename, operation):
        self.message = message
        self.filename = filename
        self.operation = operation
        self.start_time = time.time()
        self.last_update_time = 0

    def create_progress_bar(self, percentage):
        filled_length = int(percentage * 20 // 100)
        bar = "█" * filled_length + "░" * (20 - filled_length)
        return f"[{bar}]"

    async def update_progress(self, current, total):
        try:
            current_time = time.time()
            if current_time - self.last_update_time < 2:  # Update every 2 seconds
                return

            percentage = (current * 100) / total
            elapsed_time = current_time - self.start_time
            speed = current / elapsed_time if elapsed_time > 0 else 0
            speed_mb = speed / (1024 * 1024)

            remaining_bytes = total - current
            eta_seconds = remaining_bytes / speed if speed > 0 else 0
            eta = str(timedelta(seconds=int(eta_seconds)))

            current_gb = current / (1024**3)
            total_gb = total / (1024**3)

            progress_text = (
                f"[+] {self.operation}\n"
                f"{self.filename}\n\n"
                f"{self.create_progress_bar(percentage)}\n"
                f"Process: {percentage:.1f}%\n"
                f"{current_gb:.2f} GB of {total_gb:.2f} GB\n"
                f"Speed: {speed_mb:.2f} MB/s\n"
                f"ETA: {eta}"
            )

            await self.message.edit_text(progress_text)
            self.last_update_time = current_time

        except Exception as e:
            logger.error(f"Progress update error: {e}")

class FFmpegProgress:
    def __init__(self, message, filename):
        self.message = message
        self.filename = filename
        self.start_time = time.time()
        self.last_update_time = 0
        self.duration = 0

    def create_progress_bar(self, percentage):
        filled_length = int(percentage * 20 // 100)
        bar = "█" * filled_length + "░" * (20 - filled_length)
        return f"[{bar}]"

    async def parse_progress(self, line):
        duration_pattern = re.compile(r"Duration: (?P<duration>\d{2}:\d{2}:\d{2}.\d{2})")
        time_pattern = re.compile(r"time=(?P<time>\d{2}:\d{2}:\d{2}.\d{2})")
        speed_pattern = re.compile(r"speed=(?P<speed>[\d.]+)x")

        try:
            current_time = time.time()
            if current_time - self.last_update_time < 2:
                return

            if "Duration" in line:
                match = duration_pattern.search(line)
                if match:
                    self.duration = self.time_to_seconds(match.group("duration"))

            if "time=" in line:
                time_match = time_pattern.search(line)
                speed_match = speed_pattern.search(line)

                if time_match and speed_match:
                    current_time = self.time_to_seconds(time_match.group("time"))
                    speed = float(speed_match.group("speed"))

                    progress = (current_time / self.duration) * 100 if self.duration else 0
                    time_left = (self.duration - current_time) / speed if speed > 0 else 0
                    eta = str(timedelta(seconds=int(time_left)))

                    progress_text = (
                        f"[+] Compressing\n"
                        f"{self.filename}\n\n"
                        f"{self.create_progress_bar(progress)}\n"
                        f"Process: {progress:.1f}%\n"
                        f"Speed: {speed:.2f}x\n"
                        f"ETA: {eta}"
                    )

                    await self.message.edit_text(progress_text)
                    self.last_update_time = current_time

        except Exception as e:
            logger.error(f"Progress parsing error: {e}")

    @staticmethod
    def time_to_seconds(time_str):
        h, m, s = time_str.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)

def create_initial_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Compress", callback_data="compress")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])

def create_settings_menu(setting_type):
    if setting_type == "resolution":
        buttons = [[InlineKeyboardButton(res, callback_data=f"res_{res}")] for res in RESOLUTIONS.keys()]
    elif setting_type == "preset":
        buttons = [[InlineKeyboardButton(preset, callback_data=f"preset_{preset}")] for preset in PRESETS]
    elif setting_type == "codec":
        buttons = [[InlineKeyboardButton(codec, callback_data=f"codec_{codec}")] for codec in CODECS.keys()]
    elif setting_type == "pixel_format":
        buttons = [[InlineKeyboardButton(fmt, callback_data=f"pixfmt_{fmt}")] for fmt in PIXEL_FORMATS]
    
    buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)

def create_crf_menu():
    buttons = []
    row = []
    for crf in range(15, 31):
        row.append(InlineKeyboardButton(str(crf), callback_data=f"crf_{crf}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)

def create_upload_format_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Video", callback_data="upload_video")],
        [InlineKeyboardButton("Document", callback_data="upload_document")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])

@app.on_message(filters.video | filters.document)
async def handle_video(client, message):
    try:
        user_id = message.from_user.id
        
        # Check if it's a video file
        if message.document and not message.document.mime_type.startswith('video/'):
            await message.reply_text("Please send a video file.")
            return

        file_info = message.video or message.document
        
        # Check file size (limit to 2GB for example)
        if file_info.file_size > 2147483648:  # 2GB in bytes
            await message.reply_text("File size too large. Please send a file smaller than 2GB.")
            return

        user_states[user_id] = {
            "file_id": file_info.file_id,
            "original_name": file_info.file_name,
            "file_size": file_info.file_size
        }
        
        await message.reply_text(
            "Would you like to compress this file?",
            reply_markup=create_initial_menu()
        )
    except Exception as e:
        logger.error(f"Error handling video: {e}")
        await message.reply_text("An error occurred while processing your video.")

@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    try:
        user_id = callback_query.from_user.id
        data = callback_query.data

        if data == "compress":
            compression_settings[user_id] =" {}"
            await callback_query.edit_message_text(
                "Select resolution:",
                reply_markup=create_settings_menu("resolution")
            )
        
        elif data.startswith("res_"):
            compression_settings[user_id]["resolution"] = data.split("_")[1]
            await callback_query.edit_message_text(
                "Select preset:",
                reply_markup=create_settings_menu("preset")
            )
        
        elif data.startswith("preset_"):
            compression_settings[user_id]["preset"] = data.split("_")[1]
            await callback_query.edit_message_text(
                "Select CRF value (lower = better quality, higher = smaller size):",
                reply_markup=create_crf_menu()
            )
        
        elif data.startswith("crf_"):
            compression_settings[user_id]["crf"] = int(data.split("_")[1])
            await callback_query.edit_message_text(
                "Select codec:",
                reply_markup=create_settings_menu("codec")
            )
        
        elif data.startswith("codec_"):
            compression_settings[user_id]["codec"] = CODECS[data.split("_")[1]]
            await callback_query.edit_message_text(
                "Select pixel format:",
                reply_markup=create_settings_menu("pixel_format")
            )
        
        elif data.startswith("pixfmt_"):
            compression_settings[user_id]["pixel_format"] = data.split("_")[1]
            await callback_query.edit_message_text(
                "Select upload format:",
                reply_markup=create_upload_format_menu()
            )
        
        elif data.startswith("upload_"):
            compression_settings[user_id]["upload_format"] = data.split("_")[1]
            await process_video(client, callback_query, user_id)
        
        elif data == "cancel":
            if user_id in user_states:
                del user_states[user_id]
            if user_id in compression_settings:
                del compression_settings[user_id]
            await callback_query.edit_message_text("Operation cancelled.")
            
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await callback_query.edit_message_text("An error occurred. Please try again.")

async def process_video(client, callback_query, user_id):
    input_file = None
    output_file = None
    try:
        status_message = await callback_query.edit_message_text("Starting download...")
        
        # Create download directory if it doesn't exist
        os.makedirs("downloads", exist_ok=True)
        
        # Download with progress
        download_tracker = ProgressTracker(
            status_message, 
            user_states[user_id]["original_name"], 
            "Downloading"
        )
        
        input_file = f"downloads/{user_id}_{int(time.time())}"
        await client.download_media(
            user_states[user_id]["file_id"],
            file_name=input_file,
            progress=download_tracker.update_progress
        )

        # Get video resolution
        resolution = RESOLUTIONS[compression_settings[user_id]["resolution"]]
        width, height = map(int, resolution.split("x"))
        
        # Prepare output filename
        output_file = f"downloads/compressed_{os.path.basename(input_file)}"
        
        # Compression with progress
        ffmpeg_progress = FFmpegProgress(status_message, user_states[user_id]["original_name"])
        
        ffmpeg_cmd = [
            'ffmpeg', '-i', input_file,
            '-c:v', compression_settings[user_id]["codec"],
            '-preset', compression_settings[user_id]["preset"],
            '-crf', str(compression_settings[user_id]["crf"]),
            '-pix_fmt', compression_settings[user_id]["pixel_format"],
            '-vf', f'scale={width}:{height}',
            '-c:a', 'copy',
            '-progress', 'pipe:1',
            output_file
        ]

        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            line = line.decode('utf-8', errors='ignore')
            await ffmpeg_progress.parse_progress(line)

        await process.wait()

        # Upload with progress
        upload_tracker = ProgressTracker(
            status_message, 
            user_states[user_id]["original_name"], 
            "Uploading"
        )
        
        if compression_settings[user_id]["upload_format"] == "video":
            await client.send_video(
                callback_query.message.chat.id,
                output_file,
                width=width,
                height=height,
                caption=f"Compressed: {user_states[user_id]['original_name']}",
                progress=upload_tracker.update_progress
            )
        else:
            await client.send_document(
                callback_query.message.chat.id,
                output_file,
                caption=f"Compressed: {user_states[user_id]['original_name']}",
                progress=upload_tracker.update_progress
            )

        await status_message.edit_text("Process completed successfully!")

    except Exception as e:
        logger.error(f"Processing error: {e}")
        await status_message.edit_text(f"An error occurred: {str(e)}")
    
    finally:
        # Cleanup
        try:
            if input_file and os.path.exists(input_file):
                os.remove(input_file)
            if output_file and os.path.exists(output_file):
                os.remove(output_file)
            if user_id in user_states:
                del user_states[user_id]
            if user_id in compression_settings:
                del compression_settings[user_id]
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

# Start the bot
app.run()
