import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
import subprocess
from tqdm import tqdm
API_ID = "16501053" 
API_HASH = "d8c9b01c863dabacc484c2c06cdd0f6e" 
BOT_TOKEN = "8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I"
# Initialize bot
app = Client("compression_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Compression settings
COMPRESSION_SETTINGS = {
    "resolutions": {
        "144p": "256x144", "240p": "426x240", "360p": "640x360",
        "480p": "854x480", "720p": "1280x720", "1080p": "1920x1080",
        "4K": "3840x2160"
    },
    "presets": ["ultrafast", "superfast", "fast", "medium", "slow"],
    "crf": range(15, 31),
    "pixel_formats": ["yuv420p", "yuv422p", "yuv444p"],
    "codecs": ["libx264", "libx265"]
}

# Progress callback
async def progress(current, total, message, operation):
    try:
        percent = (current * 100) / total
        progress_bar = "".join("█" for _ in range(int(percent/5)))
        await message.edit_text(
            f"{operation} Progress:\n"
            f"[{progress_bar:<20}] {percent:.1f}%"
        )
    except Exception:
        pass

# Extract thumbnail from video
def extract_thumbnail(video_path):
    output_path = f"{video_path}_thumb.jpg"
    duration = float(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', video_path
    ]).decode('utf-8'))
    
    middle_time = duration / 2
    subprocess.call([
        'ffmpeg', '-ss', str(middle_time), '-i', video_path,
        '-vframes', '1', '-s', '320x320', '-f', 'image2', output_path
    ])
    return output_path

# Compress video using FFmpeg
async def compress_video(input_path, output_path, settings):
    command = [
        'ffmpeg', '-i', input_path,
        '-c:v', settings['codec'],
        '-preset', settings['preset'],
        '-crf', str(settings['crf']),
        '-vf', f'scale={settings["resolution"]}',
        '-pix_fmt', settings['pixel_format'],
        '-c:a', 'aac',
        output_path
    ]
    process = await asyncio.create_subprocess_exec(*command)
    await process.wait()

@app.on_message(filters.video | filters.document)
async def handle_video(client, message):
    # Initial compression menu
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Compress", callback_data="compress")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])
    await message.reply_text("Choose an action:", reply_markup=keyboard)

@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    
    if data == "compress":
        # Show compression settings menu
        settings_keyboard = create_settings_menu()
        await callback_query.message.edit_text(
            "Select compression settings:",
            reply_markup=settings_keyboard
        )
    elif data == "confirm_settings":
        # Handle video processing
        status_message = await callback_query.message.reply_text("Processing started...")
        
        # Download video
        video_path = await client.download_media(
            callback_query.message.reply_to_message,
            progress=progress,
            progress_args=(status_message, "Downloading")
        )
        
        # Extract thumbnail
        thumb_path = extract_thumbnail(video_path)
        
        # Compress video
        output_path = f"compressed_{os.path.basename(video_path)}"
        await compress_video(video_path, output_path, callback_query.message.settings)
        
        # Upload processed video
        await client.send_video(
            callback_query.message.chat.id,
            output_path,
            thumb=thumb_path,
            caption=f"Compressed video\nSettings: {str(callback_query.message.settings)}",
            progress=progress,
            progress_args=(status_message, "Uploading")
        )
        
        # Cleanup
        os.remove(video_path)
        os.remove(output_path)
        os.remove(thumb_path)
        await status_message.delete()

def create_settings_menu():
    # Create inline keyboard for compression settings
    keyboard = []
    for setting, options in COMPRESSION_SETTINGS.items():
        keyboard.append([InlineKeyboardButton(
            f"Select {setting}",
            callback_data=f"setting_{setting}"
        )])
    keyboard.append([InlineKeyboardButton("Confirm", callback_data="confirm_settings")])
    return InlineKeyboardMarkup(keyboard)

# Run the bot
app.run()
