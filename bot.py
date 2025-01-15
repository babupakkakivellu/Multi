import os
import ffmpeg
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from time import time, sleep

# Bot API configuration
API_ID = "16501053" 
API_HASH = "d8c9b01c863dabacc484c2c06cdd0f6e" 
BOT_TOKEN = "8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I"

app = Client("compressor_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Global dictionary to store user-specific data
user_data = {}


# Helper Functions
def compression_menu():
    """Generate compression settings menu."""
    buttons = [
        [InlineKeyboardButton("144p", callback_data="res_144"), InlineKeyboardButton("240p", callback_data="res_240")],
        [InlineKeyboardButton("360p", callback_data="res_360"), InlineKeyboardButton("480p", callback_data="res_480")],
        [InlineKeyboardButton("720p", callback_data="res_720"), InlineKeyboardButton("1080p", callback_data="res_1080")],
        [InlineKeyboardButton("4K", callback_data="res_4k")],
        [InlineKeyboardButton("Confirm", callback_data="confirm"), InlineKeyboardButton("Cancel", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def upload_menu():
    """Generate upload format menu."""
    buttons = [
        [InlineKeyboardButton("Document", callback_data="upload_document"), InlineKeyboardButton("Video", callback_data="upload_video")],
        [InlineKeyboardButton("Confirm", callback_data="upload_confirm"), InlineKeyboardButton("Cancel", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


async def progress_bar(current, total, last_update, message: Message, stage: str):
    """Update progress bar every 2 seconds."""
    now = time()
    if now - last_update >= 2:  # Only update every 2 seconds
        percent = (current / total) * 100
        bar = f"[{'█' * int(percent // 5)}{' ' * (20 - int(percent // 5))}] {percent:.2f}%"
        await message.edit_text(f"{stage}:\n{bar}")
        return now
    return last_update


# Event Handlers
@app.on_message(filters.video | filters.document)
async def handle_media(client, message: Message):
    """Handle received video or document."""
    file_id = message.video.file_id if message.video else message.document.file_id
    user_data[message.from_user.id] = {"file_id": file_id}
    await message.reply("Choose compression settings:", reply_markup=compression_menu())


@app.on_callback_query()
async def handle_callback(client, callback_query):
    """Handle callback queries for settings and confirmation."""
    user_id = callback_query.from_user.id
    if user_id not in user_data:
        await callback_query.answer("Please send a video or document first.")
        return

    data = callback_query.data
    if data.startswith("res_"):
        resolution = data.split("_")[1]
        user_data[user_id]["resolution"] = resolution
        await callback_query.answer(f"Selected resolution: {resolution}")
    elif data == "confirm":
        await callback_query.message.reply("Select upload format and filename:", reply_markup=upload_menu())
    elif data.startswith("upload_"):
        upload_format = data.split("_")[1]
        user_data[user_id]["upload_format"] = upload_format
        if upload_format == "confirm":
            await callback_query.message.reply("Enter a new filename for the output (without extension):")
    elif data == "cancel":
        user_data.pop(user_id, None)
        await callback_query.message.reply("Process cancelled.")


@app.on_message(filters.text)
async def handle_filename(client, message: Message):
    """Handle custom filename input."""
    user_id = message.from_user.id
    if user_id not in user_data or "upload_format" not in user_data[user_id]:
        return

    user_data[user_id]["filename"] = message.text
    status_message = await message.reply("Starting compression process...")

    # Download file
    file_id = user_data[user_id]["file_id"]
    input_file = f"downloads/{file_id}.mp4"
    output_file = f"compressed/{user_data[user_id]['filename']}.mp4"

    os.makedirs("downloads", exist_ok=True)
    os.makedirs("compressed", exist_ok=True)

    await status_message.edit_text("Downloading file...")
    last_update = time()
    await app.download_media(
        file_id,
        file_name=input_file,
        progress=lambda current, total: app.loop.create_task(
            progress_bar(current, total, last_update, status_message, "Downloading")
        ),
    )

    # Compress file with ffmpeg
    resolution = user_data[user_id].get("resolution", "720")
    width, height = {
        "144": (256, 144),
        "240": (426, 240),
        "360": (640, 360),
        "480": (854, 480),
        "720": (1280, 720),
        "1080": (1920, 1080),
        "4k": (3840, 2160),
    }.get(resolution, (1280, 720))

    await status_message.edit_text(f"Compressing to {resolution}...")
    last_update = time()

    process = (
        ffmpeg.input(input_file)
        .output(output_file, vf=f"scale={width}:{height}", crf=23, pix_fmt="yuv420p", vcodec="libx264")
        .run_async(pipe_stdout=True, pipe_stderr=True)
    )

    while True:
        line = process.stderr.readline()
        if not line:
            break
        last_update = await progress_bar(0, 1, last_update, status_message, "Compressing")  # Dummy progress for compression
        sleep(2)

    # Extract thumbnail
    thumbnail = f"thumbnails/{user_data[user_id]['filename']}.jpg"
    os.makedirs("thumbnails", exist_ok=True)
    duration = ffmpeg.probe(output_file)["streams"][0]["duration"]
    ffmpeg.input(output_file, ss=float(duration) / 2).output(thumbnail, vframes=1).run()

    # Upload compressed file
    await status_message.edit_text("Uploading file...")
    last_update = time()
    upload_params = {
        "thumb": thumbnail,
        "width": width,
        "height": height,
        "duration": int(float(duration)),
        "caption": f"Filename: {user_data[user_id]['filename']}",
    }

    if user_data[user_id]["upload_format"] == "document":
        await app.send_document(
            message.chat.id,
            output_file,
            **upload_params,
            progress=lambda current, total: app.loop.create_task(
                progress_bar(current, total, last_update, status_message, "Uploading")
            ),
        )
    else:
        await app.send_video(
            message.chat.id,
            output_file,
            **upload_params,
            progress=lambda current, total: app.loop.create_task(
                progress_bar(current, total, last_update, status_message, "Uploading")
            ),
        )

    # Cleanup
    os.remove(input_file)
    os.remove(output_file)
    os.remove(thumbnail)
    user_data.pop(user_id, None)
    await status_message.edit_text("Process completed!")


if __name__ == "__main__":
    app.run()
