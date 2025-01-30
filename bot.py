import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
import ffmpeg
from PIL import Image
import json
import logging
from loguru import logger

# Initialize Pyrogram client
app = Client("video_compressor_bot", api_id="YOUR_API_ID", api_hash="YOUR_API_HASH")

# Logging setup
logger.add("bot.log", rotation="10 MB", level="INFO")

# User state management
user_states = {}
queues = {}

# Database (for simplicity, using JSON)
DB_FILE = "bot_data.json"
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump({}, f)

def load_db():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

# Helper functions
def extract_thumbnail(video_path, thumbnail_path):
    """Extract thumbnail from the middle of the video."""
    try:
        (
            ffmpeg.input(video_path, ss="50%")
            .filter("scale", 320, -1)
            .output(thumbnail_path, vframes=1)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except Exception as e:
        logger.error(f"Thumbnail extraction failed: {e}")

async def run_ffmpeg(input_path, output_path, resolution, preset, crf, pixel_format, codec, progress_callback):
    """Run FFmpeg compression process with progress tracking."""
    try:
        width, height = map(int, resolution.split("x"))
        process = (
            ffmpeg.input(input_path)
            .output(
                output_path,
                vf=f"scale={width}:{height}",
                preset=preset,
                crf=crf,
                pix_fmt=pixel_format,
                vcodec=codec,
                acodec="copy",
            )
            .overwrite_output()
            .global_args("-progress", "pipe:1")
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )

        while True:
            line = process.stdout.readline().decode().strip()
            if not line:
                break
            if "out_time_ms" in line:
                time_ms = int(line.split("=")[1])
                duration_ms = float(ffmpeg.probe(input_path)["format"]["duration"]) * 1000
                progress = min(time_ms / duration_ms, 1.0)
                await progress_callback(progress)

        process.wait()
        return True
    except Exception as e:
        logger.error(f"FFmpeg process failed: {e}")
        return False

# Bot handlers
@app.on_message(filters.video | filters.document)
async def handle_video_or_document(client: Client, message: Message):
    user_id = message.from_user.id
    file_name = message.video.file_name if message.video else message.document.file_name
    file_size = message.video.file_size if message.video else message.document.file_size

    if file_size > 2 * 1024 * 1024 * 1024:  # 2GB limit
        await message.reply("❌ File size exceeds 2GB. Please send a smaller file.")
        return

    # Save user state
    if user_id not in user_states:
        user_states[user_id] = {"queue": []}
    user_states[user_id]["queue"].append({
        "file_id": message.video.file_id if message.video else message.document.file_id,
        "file_name": file_name,
        "file_size": file_size,
        "step": "menu_selection",
    })

    # Show menu selection
    await message.reply(
        f"📥 Received file: `{file_name}` ({file_size / (1024 * 1024):.2f} MB)\nWhat would you like to do?",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Compress", callback_data="compress")],
                [InlineKeyboardButton("Cancel", callback_data="cancel")],
            ]
        ),
    )

@app.on_callback_query()
async def handle_callback_query(client: Client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if user_id not in user_states or not user_states[user_id]["queue"]:
        await callback_query.answer("Session expired. Please send the file again.")
        return

    current_task = user_states[user_id]["queue"][0]

    if data == "cancel":
        user_states[user_id]["queue"].pop(0)
        await callback_query.message.edit_text("❌ Operation canceled.")
        if user_states[user_id]["queue"]:
            await callback_query.message.reply("Processing next file...")
        else:
            del user_states[user_id]
        return

    if current_task["step"] == "menu_selection" and data == "compress":
        # Show compression settings menu
        current_task["step"] = "compress_settings"
        await callback_query.message.edit_text(
            "⚙️ Select compression settings:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Resolution", callback_data="resolution"),
                        InlineKeyboardButton("CRF", callback_data="crf"),
                    ],
                    [
                        InlineKeyboardButton("Preset", callback_data="preset"),
                        InlineKeyboardButton("Pixel Format", callback_data="pixel_format"),
                    ],
                    [
                        InlineKeyboardButton("Codec", callback_data="codec"),
                        InlineKeyboardButton("Thumbnail", callback_data="thumbnail"),
                    ],
                    [InlineKeyboardButton("Confirm", callback_data="confirm_settings")],
                    [InlineKeyboardButton("Cancel", callback_data="cancel")],
                ]
            ),
        )

    elif current_task["step"] == "compress_settings" and data == "confirm_settings":
        # Show upload format menu
        current_task["step"] = "upload_format"
        await callback_query.message.edit_text(
            "📤 Select upload format:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Document", callback_data="upload_document")],
                    [InlineKeyboardButton("Video", callback_data="upload_video")],
                    [InlineKeyboardButton("Cancel", callback_data="cancel")],
                ]
            ),
        )

    elif current_task["step"] == "upload_format" and data in ["upload_document", "upload_video"]:
        # Ask for filename
        current_task["upload_format"] = data.split("_")[1]
        current_task["step"] = "rename_file"
        await callback_query.message.edit_text("📝 Enter the new filename for the output:")

    elif current_task["step"] == "rename_file" and callback_query.message.text.startswith("Enter"):
        # Confirm and start processing
        current_task["new_filename"] = callback_query.message.text.strip()
        current_task["step"] = "processing"

        # Download file
        file_id = current_task["file_id"]
        original_file_name = current_task["file_name"]
        input_path = f"downloads/{original_file_name}"
        output_path = f"compressed_{original_file_name}"

        progress_msg = await callback_query.message.edit_text("📥 Downloading file...\nProgress: 0%")
        await client.download_media(file_id, file_name=input_path, progress=lambda current, total: asyncio.create_task(update_progress(progress_msg, current, total)))

        # Extract thumbnail
        thumbnail_path = "thumbnail.jpg"
        extract_thumbnail(input_path, thumbnail_path)

        # Run FFmpeg
        await progress_msg.edit_text("⚙️ Compressing video...\nProgress: 0%")
        success = await run_ffmpeg(
            input_path,
            output_path,
            resolution=current_task.get("resolution", "1280x720"),  # Default resolution
            preset=current_task.get("preset", "medium"),  # Default preset
            crf=current_task.get("crf", 23),  # Default CRF
            pixel_format=current_task.get("pixel_format", "yuv420p"),  # Default pixel format
            codec=current_task.get("codec", "libx264"),  # Default codec
            progress_callback=lambda progress: asyncio.create_task(update_progress(progress_msg, progress, 1)),
        )

        if not success:
            await progress_msg.edit_text("❌ Compression failed.")
            return

        # Upload file
        await progress_msg.edit_text("📤 Uploading file...\nProgress: 0%")
        thumb = Image.open(thumbnail_path)
        width, height = thumb.size
        duration = 0  # TODO: Extract duration from video metadata

        if current_task["upload_format"] == "document":
            await client.send_document(
                chat_id=user_id,
                document=output_path,
                thumb=thumbnail_path,
                caption=current_task["new_filename"],
                progress=lambda current, total: asyncio.create_task(update_progress(progress_msg, current, total)),
            )
        else:
            await client.send_video(
                chat_id=user_id,
                video=output_path,
                thumb=thumbnail_path,
                width=width,
                height=height,
                duration=duration,
                caption=current_task["new_filename"],
                progress=lambda current, total: asyncio.create_task(update_progress(progress_msg, current, total)),
            )

        await progress_msg.edit_text("✅ File uploaded successfully!")
        user_states[user_id]["queue"].pop(0)
        if user_states[user_id]["queue"]:
            await callback_query.message.reply("Processing next file...")
        else:
            del user_states[user_id]

async def update_progress(message, current, total):
    """Update progress in the same message."""
    progress = current * 100 / total
    await message.edit_text(f"{message.text.split('Progress:')[0]}Progress: {progress:.1f}%")

# Start the bot
if __name__ == "__main__":
    app.run()
