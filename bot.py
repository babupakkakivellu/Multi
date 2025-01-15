from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import os
import ffmpeg
import asyncio
from datetime import datetime

API_ID = 16501053
API_HASH = "d8c9b01c863dabacc484c2c06cdd0f6e" 
BOT_TOKEN = "8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I"

# Initialize your Telegram bot
app = Client(
    "video_compression_bot",
    api_id=API_ID
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
CODECS = ["libx264", "libx265"]

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
        buttons = [[InlineKeyboardButton(codec, callback_data=f"codec_{codec}")] for codec in CODECS]
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
    user_id = message.from_user.id
    user_states[user_id] = {
        "file_id": message.video.file_id if message.video else message.document.file_id,
        "original_name": message.video.file_name if message.video else message.document.file_name
    }
    await message.reply_text(
        "Would you like to compress this file?",
        reply_markup=create_initial_menu()
    )

@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data == "compress":
        compression_settings[user_id] = {}
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
        compression_settings[user_id]["codec"] = data.split("_")[1]
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

async def process_video(client, callback_query, user_id):
    try:
        status_message = await callback_query.edit_message_text("Starting download...")
        
        # Download file
        download_path = f"downloads/{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs("downloads", exist_ok=True)
        
        file_id = user_states[user_id]["file_id"]
        original_name = user_states[user_id]["original_name"]
        input_file = await client.download_media(
            file_id,
            file_name=download_path,
            progress=lambda current, total: asyncio.create_task(
                update_progress(status_message, "Downloading", current, total)
            )
        )
        
        await status_message.edit_text("Download complete. Starting compression...")
        
        # Prepare output filename
        output_file = f"downloads/compressed_{os.path.basename(input_file)}"
        
        # Get video resolution
        resolution = RESOLUTIONS[compression_settings[user_id]["resolution"]]
        width, height = map(int, resolution.split("x"))
        
        # Prepare FFmpeg command
        stream = ffmpeg.input(input_file)
        stream = ffmpeg.output(
            stream,
            output_file,
            vcodec=compression_settings[user_id]["codec"],
            preset=compression_settings[user_id]["preset"],
            crf=compression_settings[user_id]["crf"],
            pix_fmt=compression_settings[user_id]["pixel_format"],
            vf=f'scale={width}:{height}',
            acodec='copy'
        )
        
        # Run FFmpeg
        await status_message.edit_text("Compressing video...")
        process = await asyncio.create_subprocess_exec(
            *ffmpeg.compile(stream),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        # Extract thumbnail
        thumbnail_path = f"{output_file}_thumb.jpg"
        thumb_stream = ffmpeg.input(output_file, ss='00:00:01')
        thumb_stream = ffmpeg.output(thumb_stream, thumbnail_path, vframes=1)
        process = await asyncio.create_subprocess_exec(
            *ffmpeg.compile(thumb_stream),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        # Upload compressed file
        await status_message.edit_text("Compression complete. Starting upload...")
        
        if compression_settings[user_id]["upload_format"] == "video":
            await client.send_video(
                callback_query.message.chat.id,
                output_file,
                width=width,
                height=height,
                thumb=thumbnail_path,
                caption=f"Compressed: {original_name}",
                progress=lambda current, total: asyncio.create_task(
                    update_progress(status_message, "Uploading", current, total)
                )
            )
        else:
            await client.send_document(
                callback_query.message.chat.id,
                output_file,
                thumb=thumbnail_path,
                caption=f"Compressed: {original_name}",
                progress=lambda current, total: asyncio.create_task(
                    update_progress(status_message, "Uploading", current, total)
                )
            )
        
        await status_message.edit_text("Process completed successfully!")
        
    except Exception as e:
        await status_message.edit_text(f"An error occurred: {str(e)}")
    
    finally:
        # Cleanup
        try:
            os.remove(input_file)
            os.remove(output_file)
            os.remove(thumbnail_path)
        except:
            pass
        
        if user_id in user_states:
            del user_states[user_id]
        if user_id in compression_settings:
            del compression_settings[user_id]

async def update_progress(message, operation, current, total):
    try:
        percent = (current * 100) / total
        await message.edit_text(
            f"{operation}: {percent:.1f}%\n"
            f"[{'=' * int(percent // 5)}{'.' * (20 - int(percent // 5))}]"
        )
    except:
        pass

# Start the bot
app.run()
