from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
import asyncio
import os
import time
import math
from datetime import datetime
import subprocess
import json

# Bot configuration
app = Client(
    "video_compressor_bot",
    api_id="16501053",
    api_hash="d8c9b01c863dabacc484c2c06cdd0f6e",
    bot_token="8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I"
)

# Configuration options
RESOLUTIONS = {
    "144p": (256, 144),
    "240p": (426, 240),
    "360p": (640, 360),
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "2K": (2560, 1440),
    "4K": (3840, 2160)
}

PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
PIXEL_FORMATS = ["yuv420p", "yuv422p", "yuv444p"]
CODECS = ["libx264", "libx265"]

# Store user settings
user_settings = {}

class ProgressTracker:
    def __init__(self, message, process_type):
        self.message = message
        self.process_type = process_type
        self.start_time = time.time()
        self.last_update_time = 0
        self.last_edited_text = ""

    async def update_progress(self, current, total):
        now = time.time()
        if now - self.last_update_time < 2:  # Update every 2 seconds
            return
        
        self.last_update_time = now
        
        # Handle cases where total is 0 or None
        if not total or total <= 0:
            total = current + 1  # Prevent division by zero
            percentage = 0
            bar = '░' * 50  # Show empty progress bar
        else:
            # Calculate progress
            percentage = min((current * 100 / total), 100)
            filled_length = int(50 * current // total)
            bar = '█' * filled_length + '░' * (50 - filled_length)
        
        # Calculate speed
        elapsed_time = max(now - self.start_time, 0.01)  # Prevent division by zero
        speed = current / elapsed_time
        
        # Calculate ETA
        if speed > 0 and total > current:
            eta = (total - current) / speed
            eta_str = time.strftime('%H:%M:%S', time.gmtime(eta))
        else:
            eta_str = "N/A"

        # Format sizes
        current_size = format_size(current)
        total_size = "Unknown" if not total or total <= 0 else format_size(total)
        speed_str = f"{format_size(speed)}/s"

        # Create progress text
        progress_text = (
            f"[{self.process_type}] {os.path.basename(str(self.message.document.file_name))}\n"
            f"[{bar}]\n"
            f"Progress: {percentage:.1f}%\n"
            f"Size: {current_size} of {total_size}\n"
            f"Speed: {speed_str}\n"
            f"ETA: {eta_str}"
        )

        if progress_text != self.last_edited_text:
            try:
                await self.message.edit_text(progress_text)
                self.last_edited_text = progress_text
            except Exception as e:
                print(f"Error updating progress: {str(e)}")

def format_size(size):
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(size)
    unit = 0
    while size >= 1024.0 and unit < len(units)-1:
        size /= 1024.0
        unit += 1
    return f"{size:.2f} {units[unit]}"

def get_video_duration(file_path):
    """Get video duration using ffprobe"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json',
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except Exception as e:
        print(f"Error getting duration: {str(e)}")
        return 0

def extract_thumbnail(input_file, thumbnail_file, duration):
    """Extract thumbnail using ffmpeg subprocess"""
    try:
        thumbnail_time = duration / 2
        cmd = [
            'ffmpeg',
            '-ss', str(thumbnail_time),
            '-i', input_file,
            '-vframes', '1',
            '-q:v', '2',
            thumbnail_file,
            '-y'
        ]
        subprocess.run(cmd, check=True)
        return True
    except Exception as e:
        print(f"Error extracting thumbnail: {str(e)}")
        return False

async def compress_video(input_file, output_file, settings):
    """Compress video using ffmpeg subprocess"""
    try:
        width, height = RESOLUTIONS[settings['resolution']]
        cmd = [
            'ffmpeg',
            '-i', input_file,
            '-c:v', settings['codec'],
            '-preset', settings['preset'],
            '-crf', settings['crf'],
            '-pix_fmt', settings['pixfmt'],
            '-vf', f'scale={width}:{height}',
            '-y',
            output_file
        ]
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True)
        
        # Here you could implement real-time progress monitoring by parsing ffmpeg output
        process.wait()
        
        if process.returncode != 0:
            raise Exception("FFmpeg compression failed")
        
        return True
    except Exception as e:
        print(f"Error compressing video: {str(e)}")
        return False

@app.on_message(filters.document | filters.video)
async def handle_video(client, message):
    user_id = message.from_user.id
    user_settings[user_id] = {
        'file_id': message.document.file_id if message.document else message.video.file_id,
        'message': message
    }
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Compress", callback_data="compress")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])
    
    await message.reply_text(
        "Would you like to compress this file?",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^compress$"))
async def compression_settings(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    resolution_buttons = [
        [InlineKeyboardButton(res, callback_data=f"res_{res}") 
         for res in list(RESOLUTIONS.keys())[i:i+2]]
        for i in range(0, len(RESOLUTIONS), 2)
    ]
    
    keyboard = InlineKeyboardMarkup(resolution_buttons + [
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])
    
    await callback_query.message.edit_text(
        "Select output resolution:",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^res_"))
async def handle_resolution(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    resolution = callback_query.data.split("_")[1]
    user_settings[user_id]['resolution'] = resolution
    
    preset_buttons = [
        [InlineKeyboardButton(preset, callback_data=f"preset_{preset}") 
         for preset in PRESETS[i:i+3]]
        for i in range(0, len(PRESETS), 3)
    ]
    
    keyboard = InlineKeyboardMarkup(preset_buttons + [
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])
    
    await callback_query.message.edit_text(
        "Select compression preset:",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^preset_"))
async def handle_preset(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    preset = callback_query.data.split("_")[1]
    user_settings[user_id]['preset'] = preset
    
    crf_buttons = [
        [InlineKeyboardButton(str(crf), callback_data=f"crf_{crf}") 
         for crf in range(start, start+5)]
        for start in range(15, 31, 5)
    ]
    
    keyboard = InlineKeyboardMarkup(crf_buttons + [
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])
    
    await callback_query.message.edit_text(
        "Select CRF value (lower = better quality, higher = smaller file):",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^crf_"))
async def handle_crf(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    crf = callback_query.data.split("_")[1]
    user_settings[user_id]['crf'] = crf
    
    pix_fmt_buttons = [[InlineKeyboardButton(fmt, callback_data=f"pixfmt_{fmt}") 
                       for fmt in PIXEL_FORMATS]]
    
    keyboard = InlineKeyboardMarkup(pix_fmt_buttons + [
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])
    
    await callback_query.message.edit_text(
        "Select pixel format:",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^pixfmt_"))
async def handle_pixfmt(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    pixfmt = callback_query.data.split("_")[1]
    user_settings[user_id]['pixfmt'] = pixfmt
    
    codec_buttons = [[InlineKeyboardButton(codec, callback_data=f"codec_{codec}") 
                     for codec in CODECS]]
    
    keyboard = InlineKeyboardMarkup(codec_buttons + [
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])
    
    await callback_query.message.edit_text(
        "Select video codec:",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^codec_"))
async def handle_codec(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    codec = callback_query.data.split("_")[1]
    user_settings[user_id]['codec'] = codec
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Video", callback_data="upload_video"),
         InlineKeyboardButton("Document", callback_data="upload_document")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])
    
    await callback_query.message.edit_text(
        "Select upload format:",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^upload_"))
async def handle_upload_format(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    upload_format = callback_query.data.split("_")[1]
    user_settings[user_id]['upload_format'] = upload_format
    
    await callback_query.message.edit_text(
        "Please send the desired filename for the compressed file (include extension):"
    )
    
    user_settings[user_id]['awaiting_filename'] = True

@app.on_message(filters.text & filters.private)
async def handle_filename(client, message):
    user_id = message.from_user.id
    
    if user_id in user_settings and user_settings[user_id].get('awaiting_filename'):
        filename = message.text
        user_settings[user_id]['output_filename'] = filename
        user_settings[user_id]['awaiting_filename'] = False
        
        settings = user_settings[user_id]
        confirmation_text = (
            f"Compression Settings:\n"
            f"Resolution: {settings['resolution']}\n"
            f"Preset: {settings['preset']}\n"
            f"CRF: {settings['crf']}\n"
            f"Pixel Format: {settings['pixfmt']}\n"
            f"Codec: {settings['codec']}\n"
            f"Upload Format: {settings['upload_format']}\n"
            f"Output Filename: {settings['output_filename']}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Confirm", callback_data="confirm_compression"),
             InlineKeyboardButton("Cancel", callback_data="cancel")]
        ])
        
        await message.reply_text(confirmation_text, reply_markup=keyboard)

@app.on_callback_query(filters.regex("^confirm_compression$"))
async def process_video(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    settings = user_settings[user_id]
    
    progress_msg = await callback_query.message.reply_text("Starting download...")
    
    try:
        # Download file
        download_tracker = ProgressTracker(progress_msg, "Downloading")
        input_file = await client.download_media(
            settings['file_id'],
            progress=download_tracker.update_progress
        )
        
        await progress_msg.edit_text("Starting compression...")
        
        output_file = f"compressed_{settings['output_filename']}"
        
        # Get video duration and extract thumbnail
        duration = get_video_duration(input_file)
        thumbnail_file = f"thumb_{settings['output_filename']}.jpg"
        
        if not extract_thumbnail(input_file, thumbnail_file, duration):
            await progress_msg.edit_text("Error: Failed to extract thumbnail")
            return
        
        # Compress video
        if not await compress_video(input_file, output_file, settings):
            await progress_msg.edit_text("Error: Failed to compress video")
            return
        
        # Upload file
        upload_tracker = ProgressTracker(progress_msg, "Uploading")
        width, height = RESOLUTIONS[settings['resolution']]
        
        if settings['upload_format'] == 'video':
            await client.send_video(
                callback_query.message.chat.id,
                output_file,
                thumb=thumbnail_file,
                width=width,
                height=height,
                caption=settings['output_filename'],
                progress=upload_tracker.update_progress
            )
        else:
            await client.send_document(
                callback_query.message.chat.id,
                output_file,
                thumb=thumbnail_file,
                caption=settings['output_filename'],
                progress=upload_tracker.update_progress
            )
        
        await progress_msg.edit_text("Processing completed successfully!")
        
    except Exception as e:
        await progress_msg.edit_text(f"An error occurred: {str(e)}")
    
    finally:
        # Cleanup
        try:
            os.remove(input_file)
            os.remove(output_file)
            os.remove(thumbnail_file)
        except:
            pass
        
        if user_id in user_settings:
            del user_settings[user_id]

@app.on_callback_query(filters.regex("^cancel$"))
async def cancel_operation(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if user_id in user_settings:
        del user_settings[user_id]
    
    await callback_query.message.edit_text("Operation cancelled.")

# Start the bot
app.run()
