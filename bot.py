from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import os
import asyncio
import time
import ffmpeg
from datetime import datetime

# Initialize your bot
app = Client(
    "compression_bot",
    api_id="16501053",
    api_hash="d8c9b01c863dabacc484c2c06cdd0f6e",
    bot_token="8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I"
)

# Store user settings in a dictionary
user_settings = {}

# Compression settings
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
CRF_VALUES = list(range(15, 31))
PIXEL_FORMATS = ["yuv420p", "yuv422p", "yuv444p"]
CODECS = ["libx264", "libx265"]

def create_settings_menu(user_id):
    settings = user_settings.get(user_id, {})
    
    keyboard = [
        [InlineKeyboardButton("Resolution: " + settings.get("resolution", "Not Set"), 
                            callback_data="resolution")],
        [InlineKeyboardButton("Preset: " + settings.get("preset", "Not Set"), 
                            callback_data="preset")],
        [InlineKeyboardButton("CRF: " + str(settings.get("crf", "Not Set")), 
                            callback_data="crf")],
        [InlineKeyboardButton("Pixel Format: " + settings.get("pixel_format", "Not Set"), 
                            callback_data="pixel_format")],
        [InlineKeyboardButton("Codec: " + settings.get("codec", "Not Set"), 
                            callback_data="codec")],
        [InlineKeyboardButton("✅ Confirm", callback_data="confirm_settings"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_upload_menu():
    keyboard = [
        [InlineKeyboardButton("📄 Document", callback_data="upload_document"),
         InlineKeyboardButton("🎥 Video", callback_data="upload_video")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def progress(current, total, message, action):
    try:
        percentage = current * 100 / total
        progress_text = f"{action}: {percentage:.1f}%\n" + \
                       f"[{'=' * int(percentage/5)}{'.' * (20-int(percentage/5))}]"
        await message.edit_text(progress_text)
    except Exception as e:
        print(e)

async def extract_thumbnail(video_path):
    thumbnail_path = f"{video_path}_thumb.jpg"
    probe = await asyncio.create_subprocess_exec(
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
        'default=noprint_wrappers=1:nokey=1', video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _ = await probe.communicate()
    duration = float(stdout.decode('utf-8').strip())
    
    # Extract thumbnail from middle of video
    time_pos = duration / 2
    command = [
        'ffmpeg', '-ss', str(time_pos), '-i', video_path,
        '-vframes', '1', '-q:v', '2', thumbnail_path
    ]
    process = await asyncio.create_subprocess_exec(*command)
    await process.communicate()
    
    return thumbnail_path

@app.on_message(filters.video | filters.document)
async def handle_video(client, message):
    keyboard = [
        [InlineKeyboardButton("🎯 Compress", callback_data="compress"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    await message.reply_text(
        "Would you like to compress this video?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if data == "compress":
        user_settings[user_id] = {}
        await callback_query.message.edit_text(
            "Select compression settings:",
            reply_markup=create_settings_menu(user_id)
        )
    
    elif data == "confirm_settings":
        await callback_query.message.edit_text(
            "Select upload format:",
            reply_markup=create_upload_menu()
        )
    
    elif data in ["upload_document", "upload_video"]:
        user_settings[user_id]["upload_type"] = data
        await callback_query.message.edit_text(
            "Please send the new filename for the compressed video (or /skip to keep original):"
        )
    
    # Handle other callback queries (resolution, preset, etc.)
    # Implementation for other settings menus...

async def process_video(message, input_file, output_file, settings):
    status_msg = await message.reply_text("Starting process...")
    
    # Download
    await message.download(
        file_name=input_file,
        progress=progress,
        progress_args=(status_msg, "Downloading")
    )
    
    # Extract thumbnail
    thumbnail = await extract_thumbnail(input_file)
    
    # Get video information
    probe = ffmpeg.probe(input_file)
    video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    
    # Prepare FFmpeg command
    stream = ffmpeg.input(input_file)
    stream = ffmpeg.output(stream, output_file,
        vcodec=settings['codec'],
        preset=settings['preset'],
        crf=settings['crf'],
        pix_fmt=settings['pixel_format'],
        **{'s': RESOLUTIONS[settings['resolution']]}
    )
    
    # Run FFmpeg
    await status_msg.edit_text("Compressing...")
    process = await asyncio.create_subprocess_exec(
        *ffmpeg.compile(stream),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()
    
    # Upload
    if settings['upload_type'] == 'upload_video':
        await message.reply_video(
            output_file,
            thumb=thumbnail,
            duration=int(float(video_info['duration'])),
            width=int(video_info['width']),
            height=int(video_info['height']),
            caption=settings.get('filename', os.path.basename(output_file)),
            progress=progress,
            progress_args=(status_msg, "Uploading")
        )
    else:
        await message.reply_document(
            output_file,
            thumb=thumbnail,
            caption=settings.get('filename', os.path.basename(output_file)),
            progress=progress,
            progress_args=(status_msg, "Uploading")
        )
    
    # Cleanup
    os.remove(input_file)
    os.remove(output_file)
    os.remove(thumbnail)
    await status_msg.delete()

app.run()
