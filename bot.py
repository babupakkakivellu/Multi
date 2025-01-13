import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import ffmpeg
from datetime import datetime

# Bot configuration
app = Client(
    "video_compress_bot",
    api_id="16501053",
    api_hash="d8c9b01c863dabacc484c2c06cdd0f6e",
    bot_token="8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I"
)

# Compression settings
RESOLUTIONS = {
    "144p": "256x144",
    "240p": "426x240",
    "360p": "640x360",
    "480p": "854x480",
    "720p": "1280x720",
    "1080p": "1920x1080",
    "4K": "3840x2160"
}

PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
CRF_RANGE = range(15, 31)
PIXEL_FORMATS = ["yuv420p", "yuv444p"]
CODECS = ["libx264", "libx265"]

# User session storage
user_settings = {}

def create_initial_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Compress", callback_data="start_compress")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])

def create_settings_menu(user_id):
    settings = user_settings.get(user_id, {})
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Resolution: {settings.get('resolution', '1080p')}", callback_data="set_resolution")],
        [InlineKeyboardButton(f"Preset: {settings.get('preset', 'medium')}", callback_data="set_preset")],
        [InlineKeyboardButton(f"CRF: {settings.get('crf', '23')}", callback_data="set_crf")],
        [InlineKeyboardButton(f"Codec: {settings.get('codec', 'libx264')}", callback_data="set_codec")],
        [InlineKeyboardButton(f"Pixel Format: {settings.get('pixel_format', 'yuv420p')}", callback_data="set_pixfmt")],
        [InlineKeyboardButton("Confirm", callback_data="confirm_settings")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])

async def progress(current, total, message, action):
    try:
        percent = current * 100 / total
        progress_bar = "▓" * int(percent/5) + "░" * (20 - int(percent/5))
        await message.edit_text(
            f"{action} Progress:\n"
            f"[{progress_bar}] {percent:.1f}%\n"
            f"{current}/{total} bytes"
        )
    except Exception as e:
        print(f"Progress update error: {e}")

@app.on_message(filters.video | filters.document)
async def handle_video(client: Client, message: Message):
    try:
        # Store video info in user session
        user_settings[message.from_user.id] = {
            "file_id": message.video.file_id if message.video else message.document.file_id,
            "file_name": message.video.file_name if message.video else message.document.file_name
        }
        
        await message.reply_text(
            "Select an action:",
            reply_markup=create_initial_menu()
        )
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")

@app.on_callback_query()
async def handle_callback(client: Client, callback: CallbackQuery):
    try:
        data = callback.data
        user_id = callback.from_user.id

        if data == "start_compress":
            await callback.message.edit_text(
                "Select compression settings:",
                reply_markup=create_settings_menu(user_id)
            )

        elif data.startswith("set_"):
            # Handle settings selection
            setting_type = data.split("_")[1]
            # Show appropriate options based on setting_type
            # Update user_settings[user_id] with selected value
            await callback.message.edit_text(
                "Settings updated",
                reply_markup=create_settings_menu(user_id)
            )

        elif data == "confirm_settings":
            # Show upload format selection
            markup = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Upload as Video", callback_data="upload_video"),
                    InlineKeyboardButton("Upload as Document", callback_data="upload_document")
                ]
            ])
            await callback.message.edit_text("Select upload format:", reply_markup=markup)

        elif data.startswith("upload_"):
            # Start processing
            settings = user_settings[user_id]
            progress_message = await callback.message.edit_text("Starting download...")
            
            # Download file
            file_path = await client.download_media(
                settings["file_id"],
                progress=progress,
                progress_args=(progress_message, "Downloading")
            )

            # Process with FFmpeg
            output_path = f"compressed_{settings['file_name']}"
            await process_video(file_path, output_path, settings, progress_message)

            # Upload processed file
            await upload_file(client, output_path, callback.message, settings, data == "upload_video")

            # Cleanup
            os.remove(file_path)
            os.remove(output_path)
            
    except Exception as e:
        await callback.message.edit_text(f"Error: {str(e)}")

async def process_video(input_path, output_path, settings, message):
    try:
        # Construct FFmpeg command based on settings
        command = [
            "ffmpeg", "-i", input_path,
            "-c:v", settings["codec"],
            "-preset", settings["preset"],
            "-crf", str(settings["crf"]),
            "-pix_fmt", settings["pixel_format"],
            "-vf", f"scale={settings['resolution']}",
            "-c:a", "aac",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await message.edit_text("Processing video...")
        await process.communicate()
        
    except Exception as e:
        await message.edit_text(f"Processing error: {str(e)}")

async def upload_file(client, file_path, message, settings, as_video=True):
    try:
        # Extract video metadata
        probe = ffmpeg.probe(file_path)
        video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        
        # Extract thumbnail
        thumbnail_path = "thumb.jpg"
        await extract_thumbnail(file_path, thumbnail_path)
        
        if as_video:
            await client.send_video(
                message.chat.id,
                file_path,
                thumb=thumbnail_path,
                duration=int(float(probe['format']['duration'])),
                width=int(video_info['width']),
                height=int(video_info['height']),
                caption=settings.get('file_name', 'Compressed video'),
                progress=progress,
                progress_args=(message, "Uploading")
            )
        else:
            await client.send_document(
                message.chat.id,
                file_path,
                thumb=thumbnail_path,
                caption=settings.get('file_name', 'Compressed video'),
                progress=progress,
                progress_args=(message, "Uploading")
            )
            
        os.remove(thumbnail_path)
        
    except Exception as e:
        await message.edit_text(f"Upload error: {str(e)}")

async def extract_thumbnail(video_path, thumb_path):
    try:
        probe = ffmpeg.probe(video_path)
        duration = float(probe['format']['duration']) / 2
        
        command = [
            "ffmpeg", "-i", video_path,
            "-ss", str(duration),
            "-vframes", "1",
            thumb_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        
    except Exception as e:
        print(f"Thumbnail extraction error: {e}")

app.run()
