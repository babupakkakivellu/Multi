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

# Compression options
RESOLUTIONS = {
    "144p": "256x144",
    "240p": "426x240",
    "360p": "640x360",
    "480p": "854x480",
    "720p": "1280x720",
    "1080p": "1920x1080",
    "4K": "3840x2160"
}

PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"]
CRF_VALUES = list(range(15, 31))
PIXEL_FORMATS = ["yuv420p", "yuv422p", "yuv444p"]
CODECS = ["libx264", "libx265"]

class CompressionState:
    def __init__(self):
        self.file_id = None
        self.file_name = None
        self.resolution = None
        self.preset = None
        self.crf = None
        self.pixel_format = None
        self.codec = None
        self.output_format = None
        self.custom_name = None
        self.message = None

# Store user states
user_states = {}

app = Client("video_compress_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text(
        "Welcome to Video Compression Bot!\n"
        "Send me any video to start compression."
    )

@app.on_message(filters.video | filters.document)
async def handle_video(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Initialize user state
    user_states[user_id] = CompressionState()
    state = user_states[user_id]
    
    if message.video:
        state.file_id = message.video.file_id
        state.file_name = message.video.file_name
    else:
        state.file_id = message.document.file_id
        state.file_name = message.document.file_name
    
    state.message = message
    
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Compress", callback_data="start_compression"),
            InlineKeyboardButton("Cancel", callback_data="cancel")
        ]
    ])
    
    await message.reply_text(
        "Would you like to compress this video?",
        reply_markup=markup
    )

@app.on_callback_query()
async def handle_callback(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    if user_id not in user_states:
        await callback.answer("Session expired. Please send the video again.", show_alert=True)
        return
    
    state = user_states[user_id]
    
    if data == "cancel":
        await callback.message.edit_text("Operation cancelled.")
        del user_states[user_id]
        return
    
    elif data == "start_compression":
        buttons = [[InlineKeyboardButton(res, callback_data=f"res_{res}")] for res in RESOLUTIONS.keys()]
        buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
        markup = InlineKeyboardMarkup(buttons)
        await callback.message.edit_text("Select output resolution:", reply_markup=markup)
    
    elif data.startswith("res_"):
        state.resolution = RESOLUTIONS[data[4:]]
        buttons = [[InlineKeyboardButton(preset, callback_data=f"preset_{preset}")] for preset in PRESETS]
        buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
        markup = InlineKeyboardMarkup(buttons)
        await callback.message.edit_text("Select encoding preset:", reply_markup=markup)
    
    elif data.startswith("preset_"):
        state.preset = data[7:]
        buttons = []
        for i in range(15, 31, 3):
            row = [InlineKeyboardButton(str(j), callback_data=f"crf_{j}") for j in range(i, min(i+3, 31))]
            buttons.append(row)
        buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
        markup = InlineKeyboardMarkup(buttons)
        await callback.message.edit_text(
            "Select CRF value (15-30):\nLower = Better Quality but Larger Size",
            reply_markup=markup
        )
    
    elif data.startswith("crf_"):
        state.crf = int(data[4:])
        buttons = [[InlineKeyboardButton(fmt, callback_data=f"pix_{fmt}")] for fmt in PIXEL_FORMATS]
        buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
        markup = InlineKeyboardMarkup(buttons)
        await callback.message.edit_text("Select pixel format:", reply_markup=markup)
    
    elif data.startswith("pix_"):
        state.pixel_format = data[4:]
        buttons = [[InlineKeyboardButton(codec, callback_data=f"codec_{codec}")] for codec in CODECS]
        buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
        markup = InlineKeyboardMarkup(buttons)
        await callback.message.edit_text("Select codec:", reply_markup=markup)
    
    elif data.startswith("codec_"):
        state.codec = data[6:]
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Video", callback_data="format_video"),
                InlineKeyboardButton("Document", callback_data="format_document")
            ],
            [InlineKeyboardButton("Cancel", callback_data="cancel")]
        ])
        await callback.message.edit_text("Select output format:", reply_markup=markup)
    
    elif data.startswith("format_"):
        state.output_format = data[7:]
        await callback.message.edit_text(
            "Enter custom filename (or send /skip to use original name):"
        )
        # Switch to waiting for filename input
        state.waiting_for_filename = True
    
    await callback.answer()

@app.on_message(filters.text & filters.private)
async def handle_filename(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_states or not hasattr(user_states[user_id], 'waiting_for_filename'):
        return
    
    state = user_states[user_id]
    
    if message.text == "/skip":
        state.custom_name = state.file_name
    else:
        state.custom_name = message.text
    
    await message.reply_text("Starting compression process...")
    await start_compression(client, state)
    del user_states[user_id]

async def start_compression(client: Client, state: CompressionState):
    progress_msg = await state.message.reply_text("Downloading video...")
    
    try:
        # Download video
        input_file = await client.download_media(
            state.file_id,
            progress=progress_callback,
            progress_args=(progress_msg,)
        )
        
        # Extract thumbnail
        await progress_msg.edit_text("Extracting thumbnail...")
        thumbnail = f"thumb_{os.path.basename(input_file)}.jpg"
        
        duration = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", input_file
        ]).decode('utf-8').strip())
        
        subprocess.run([
            "ffmpeg", "-ss", str(duration/2), "-i", input_file,
            "-vframes", "1", "-f", "image2", thumbnail
        ])
        
        # Compress video
        await progress_msg.edit_text("Compressing video...")
        output_file = f"compressed_{state.custom_name}"
        
        ffmpeg_cmd = [
            "ffmpeg", "-i", input_file,
            "-c:v", state.codec,
            "-preset", state.preset,
            "-crf", str(state.crf),
            "-vf", f"scale={state.resolution}",
            "-pix_fmt", state.pixel_format,
            "-c:a", "copy",
            output_file
        ]
        
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        
        # Upload compressed video
        await progress_msg.edit_text("Uploading compressed video...")
        
        if state.output_format == "video":
            await client.send_video(
                state.message.chat.id,
                output_file,
                thumb=thumbnail,
                caption=f"Compressed: {state.custom_name}\nResolution: {state.resolution}\nPreset: {state.preset}\nCRF: {state.crf}",
                progress=progress_callback,
                progress_args=(progress_msg,)
            )
        else:
            await client.send_document(
                state.message.chat.id,
                output_file,
                thumb=thumbnail,
                caption=f"Compressed: {state.custom_name}\nResolution: {state.resolution}\nPreset: {state.preset}\nCRF: {state.crf}",
                progress=progress_callback,
                progress_args=(progress_msg,)
            )
        
        await progress_msg.delete()
        
        # Cleanup
        os.remove(input_file)
        os.remove(output_file)
        os.remove(thumbnail)
        
    except Exception as e:
        await progress_msg.edit_text(f"Error: {str(e)}")
        if 'input_file' in locals():
            os.remove(input_file)
        if 'output_file' in locals():
            os.remove(output_file)
        if 'thumbnail' in locals():
            os.remove(thumbnail)

async def progress_callback(current, total, message):
    try:
        percent = current * 100 / total
        await message.edit_text(f"Progress: {percent:.1f}%")
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass

print("Bot is running...")
app.run()
