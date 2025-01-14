import os
import time
import json
import asyncio
import subprocess
import re
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    Message, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery
)
from pyrogram.errors import FloodWait, RPCError, BadRequest, Forbidden

# Bot configuration
API_ID = "16501053" 
API_HASH = "d8c9b01c863dabacc484c2c06cdd0f6e" 
BOT_TOKEN = "8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I"

# Compression Settings
RESOLUTIONS = {
    "144p 📱": "256x144",
    "240p 📱": "426x240",
    "360p 📱": "640x360",
    "480p 💻": "854x480",
    "720p 💻": "1280x720",
    "1080p 🖥️": "1920x1080",
    "4K 🎯": "3840x2160"
}

PRESETS = {
    "Ultrafast ⚡": "ultrafast",
    "Superfast 🚀": "superfast",
    "Veryfast 🏃": "veryfast",
    "Faster 🏃‍♂️": "faster",
    "Fast ⚡": "fast",
    "Medium 🚶": "medium",
    "Slow 🐢": "slow"
}

CRF_VALUES = {
    "15 - Visually Lossless 🎯": "15",
    "18 - High Quality 🎥": "18",
    "23 - Medium Quality 📺": "23",
    "28 - Low Quality 📱": "28"
}

THEMES = {
    "mobile": {
        "name": "📱 Mobile Data Saver",
        "resolution": "480x360",
        "preset": "veryfast",
        "crf": "28",
        "codec": "libx264",
        "pixel_format": "yuv420p",
        "description": "Smallest size, good for mobile data"
    },
    "telegram": {
        "name": "📬 Telegram Optimized",
        "resolution": "720x480",
        "preset": "medium",
        "crf": "23",
        "codec": "libx264",
        "pixel_format": "yuv420p",
        "description": "Balanced for Telegram sharing"
    },
    "high": {
        "name": "🎯 High Quality",
        "resolution": "1280x720",
        "preset": "slow",
        "crf": "18",
        "codec": "libx264",
        "pixel_format": "yuv420p",
        "description": "Best quality, larger size"
    }
}

class CompressionState:
    def __init__(self):
        self.file_id = None
        self.file_name = None
        self.message = None
        self.resolution = "720x480"
        self.preset = "medium"
        self.crf = "23"
        self.codec = "libx264"
        self.pixel_format = "yuv420p"
        self.custom_name = None
        self.output_format = "video"
        self.waiting_for_filename = False
        self.start_time = None

user_states = {}

app = Client("video_compress_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def create_progress_bar(current, total, length=20):
    filled_length = int(length * current // total)
    bar = '█' * filled_length + '░' * (length - filled_length)
    return bar

def create_theme_menu():
    buttons = [
        [
            InlineKeyboardButton("📱 Mobile Saver", callback_data="theme:mobile"),
            InlineKeyboardButton("📬 Telegram", callback_data="theme:telegram")
        ],
        [
            InlineKeyboardButton("🎯 High Quality", callback_data="theme:high"),
            InlineKeyboardButton("⚙️ Custom", callback_data="theme:custom")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(buttons)

def create_custom_menu():
    buttons = [
        [InlineKeyboardButton("📐 Resolution", callback_data="custom:resolution")],
        [InlineKeyboardButton("⚡ Preset", callback_data="custom:preset")],
        [InlineKeyboardButton("🎯 Quality (CRF)", callback_data="custom:crf")],
        [InlineKeyboardButton("✅ Confirm Settings", callback_data="custom:confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(buttons)

async def show_format_selection(message, theme_name):
    buttons = [
        [
            InlineKeyboardButton("📹 Video", callback_data="format:video"),
            InlineKeyboardButton("📄 Document", callback_data="format:document")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    await message.edit_text(
        f"🎯 **Selected: {theme_name}**\n\n"
        "Choose output format:\n\n"
        "📹 **Video** - Send as video message\n"
        "📄 **Document** - Send as file",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_message(filters.command("start"))
async def start_command(client, message):
    try:
        welcome_text = (
            "🎥 **Welcome to Video Compression Bot!**\n\n"
            "I can help you compress videos with various settings:\n\n"
            "📱 **Mobile Data Saver**\n"
            "• Smallest file size\n"
            "• Good for mobile data\n\n"
            "📬 **Telegram Optimized**\n"
            "• Balanced quality\n"
            "• Perfect for sharing\n\n"
            "🎯 **High Quality**\n"
            "• Best quality\n"
            "• Larger file size\n\n"
            "⚙️ **Custom Settings**\n"
            "• Choose your own settings\n\n"
            "Send me any video to start! 🚀"
        )
        await message.reply_text(welcome_text)
    except Exception as e:
        print(f"Start command error: {str(e)}")
        await message.reply_text("❌ An error occurred. Please try again.")

@app.on_message(filters.video | filters.document)
async def handle_video(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        
        if user_id in user_states:
            await message.reply_text(
                "⚠️ You have an ongoing compression task.\n"
                "Please wait for it to complete or send /cancel."
            )
            return
        
        user_states[user_id] = CompressionState()
        state = user_states[user_id]
        
        if message.video:
            state.file_id = message.video.file_id
            state.file_name = message.video.file_name or "video.mp4"
            file_size = message.video.file_size
            duration = message.video.duration
            width = message.video.width
            height = message.video.height
        else:
            if not message.document.mime_type or not message.document.mime_type.startswith("video/"):
                await message.reply_text("❌ Please send a valid video file.")
                del user_states[user_id]
                return
                
            state.file_id = message.document.file_id
            state.file_name = message.document.file_name or "video.mp4"
            file_size = message.document.file_size
            duration = 0
            width = height = 0
        
        if file_size > 2_000_000_000:  # 2GB limit
            await message.reply_text("❌ File too large. Maximum size: 2GB")
            del user_states[user_id]
            return
        
        state.message = message
        
        info_text = (
            "📽️ **Video Information**\n\n"
            f"📁 **Filename:** `{state.file_name}`\n"
            f"💾 **Size:** {format_size(file_size)}\n"
            f"⏱️ **Duration:** {duration} seconds\n"
            f"📐 **Resolution:** {width}x{height}\n\n"
            "**Choose a Compression Theme:**"
        )
        
        await message.reply_text(
            info_text,
            reply_markup=create_theme_menu()
        )
    
    except Exception as e:
        error_text = f"❌ Error processing video: {str(e)}"
        print(error_text)
        await message.reply_text(error_text)
        if user_id in user_states:
            del user_states[user_id]

@app.on_callback_query()
async def handle_callback(client: Client, callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        data = callback.data
        
        if user_id not in user_states:
            await callback.answer("⚠️ Session expired. Please send the video again.", show_alert=True)
            return
        
        state = user_states[user_id]
        
        if data == "cancel":
            await callback.message.edit_text("❌ Operation cancelled.")
            del user_states[user_id]
            return
        
        elif data.startswith("theme:"):
            theme_id = data.split(":")[1]
            if theme_id == "custom":
                await callback.message.edit_text(
                    "⚙️ **Custom Compression Settings**\n\n"
                    "Select what you want to configure:",
                    reply_markup=create_custom_menu()
                )
            else:
                theme = THEMES[theme_id]
                state.resolution = theme["resolution"]
                state.preset = theme["preset"]
                state.crf = theme["crf"]
                state.codec = theme["codec"]
                state.pixel_format = theme["pixel_format"]
                
                await show_format_selection(callback.message, theme["name"])
        
        elif data.startswith("custom:"):
            action = data.split(":")[1]
            if action == "resolution":
                buttons = [[InlineKeyboardButton(name, callback_data=f"res:{value}")] 
                          for name, value in RESOLUTIONS.items()]
                buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="custom:back")])
                await callback.message.edit_text(
                    "📐 **Select Output Resolution:**\n\n"
                    "Lower resolution = Smaller file size\n"
                    "Higher resolution = Better quality",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif action == "preset":
                buttons = [[InlineKeyboardButton(name, callback_data=f"preset:{value}")] 
                          for name, value in PRESETS.items()]
                buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="custom:back")])
                await callback.message.edit_text(
                    "⚡ **Select Encoding Preset:**\n\n"
                    "Faster = Larger file size\n"
                    "Slower = Better compression",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif action == "crf":
                buttons = [[InlineKeyboardButton(name, callback_data=f"crf:{value}")] 
                          for name, value in CRF_VALUES.items()]
                buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="custom:back")])
                await callback.message.edit_text(
                    "🎯 **Select Quality (CRF Value):**\n\n"
                    "Lower value = Better quality, larger size\n"
                    "Higher value = Lower quality, smaller size",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif action == "confirm":
                await show_format_selection(callback.message, "Custom Settings")
            
            elif action == "back":
                await callback.message.edit_text(
                    "⚙️ **Custom Compression Settings**\n\n"
                    "Select what you want to configure:",
                    reply_markup=create_custom_menu()
                )
        
        elif data.startswith(("res:", "preset:", "crf:")):
            setting_type, value = data.split(":")
            if setting_type == "res":
                state.resolution = value
            elif setting_type == "preset":
                state.preset = value
            elif setting_type == "crf":
                state.crf = value
            
            await callback.message.edit_text(
                "⚙️ **Custom Compression Settings**\n\n"
                f"Current Settings:\n"
                f"• Resolution: {state.resolution}\n"
                f"• Preset: {state.preset}\n"
                f"• CRF: {state.crf}\n\n"
                "Select what you want to configure:",
                reply_markup=create_custom_menu()
            )
        
        elif data.startswith("format:"):
            state.output_format = data.split(":")[1]
            await callback.message.edit_text(
                "📝 **Enter Custom Filename**\n\n"
                "• Send new filename\n"
                "• Or send /skip to keep original name\n\n"
                "Note: Include file extension (.mp4, .mkv, etc.)"
            )
            state.waiting_for_filename = True
        
        await callback.answer()
    
    except Exception as e:
        error_text = f"❌ Callback error: {str(e)}"
        print(error_text)
        await callback.answer(error_text, show_alert=True)
        if user_id in user_states:
            del user_states[user_id]

@app.on_message(filters.text & filters.private)
async def handle_filename(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        
        if user_id not in user_states or not user_states[user_id].waiting_for_filename:
            return
        
        state = user_states[user_id]
        
        if message.text == "/skip":
            state.custom_name = state.file_name
        else:
            state.custom_name = message.text
            if not any(state.custom_name.lower().endswith(ext) 
                      for ext in ['.mp4', '.mkv', '.avi', '.mov']):
                state.custom_name += '.mp4'
        
        await message.reply_text(
            "🎯 **Starting Compression Process**\n\n"
            "Please wait while I process your video..."
        )
        await start_compression(client, state)
    
    except Exception as e:
        error_text = f"❌ Error processing filename: {str(e)}"
        print(error_text)
        await message.reply_text(error_text)
        if user_id in user_states:
            del user_states[user_id]


async def progress_callback(current, total, message, start_time, action):
    try:
        now = time.time()
        elapsed_time = max(0.1, now - start_time)
        
        # Only update every 2 seconds to avoid FloodWait
        if hasattr(message, 'last_update') and (now - message.last_update) < 2:
            return
        message.last_update = now

        # Store the actual total size when first received
        if not hasattr(message, 'actual_total'):
            message.actual_total = total

        # Use stored actual total size
        total = message.actual_total

        # Calculate progress metrics
        progress = min(100, (current * 100) / total) if total else 0
        speed = current / elapsed_time
        eta = (total - current) / speed if speed > 0 else 0

        # Create progress bar
        progress_bar = create_progress_bar(current, total)
        
        # Format sizes with actual values
        current_size = format_size(current)
        total_size = format_size(total)  # Using actual total size
        speed_text = format_size(speed)

        text = (
            f"**{action}**\n\n"
            f"💫 **Progress:** {progress:.1f}%\n"
            f"{progress_bar}\n"
            f"⚡ **Speed:** {speed_text}/s\n"
            f"⏱️ **Elapsed:** {time.strftime('%H:%M:%S', time.gmtime(elapsed_time))}\n"
            f"⏳ **ETA:** {time.strftime('%H:%M:%S', time.gmtime(eta))}\n"
            f"📊 **Size:** {current_size} / {total_size}"
        )
        
        try:
            await message.edit_text(text)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            
    except Exception as e:
        print(f"Progress callback error: {str(e)}")

def create_progress_bar(current, total, length=20):
    try:
        # Ensure we have valid numbers
        current = float(current)
        total = float(total)
        
        # Calculate the progress
        if total <= 0:
            percentage = 0
        else:
            percentage = min(1, current / total)
        
        # Create the progress bar
        filled_length = int(length * percentage)
        filled = "█" * filled_length
        empty = "░" * (length - filled_length)
        
        return filled + empty
    
    except Exception as e:
        print(f"Progress bar error: {str(e)}")
        return "░" * length

def format_size(size):
    try:
        # Convert to float and handle negative values
        size = float(abs(size))
        
        if size == 0:
            return "0B"
            
        # Size units and their threshold
        units = {
            'B': 1,
            'KB': 1024,
            'MB': 1024 * 1024,
            'GB': 1024 * 1024 * 1024,
            'TB': 1024 * 1024 * 1024 * 1024
        }
        
        # Find the appropriate unit
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < units[unit] * 1024.0 or unit == 'TB':
                if unit == 'B':
                    return f"{int(size)} {unit}"
                return f"{size/units[unit]:.2f} {unit}"
                
    except Exception as e:
        print(f"Size format error: {str(e)}")
        return "0B"

def format_size(size):
    if size == 0:
        return "0B"
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}"

async def start_compression(client: Client, state: CompressionState):
    progress_msg = await state.message.reply_text(
        "⚙️ **Initializing Compression Process**\n\n"
        "🔄 Preparing your video..."
    )
    start_time = time.time()
    input_file = output_file = thumbnail = None
    
    try:
        # Download video
        try:
            await progress_msg.edit_text("📥 **Download Started**\n\nDownloading your video file...")
            input_file = await client.download_media(
                state.file_id,
                progress=progress_callback,
                progress_args=(progress_msg, start_time, "Downloading Video")
            )
            
            if not input_file:
                raise Exception("Download failed")
            
        except FloodWait as e:
            await progress_msg.edit_text(f"⚠️ Rate limited. Waiting for {e.value} seconds...")
            await asyncio.sleep(e.value)
            raise Exception("Download retry needed")
        except Exception as e:
            raise Exception(f"Download failed: {str(e)}")

        # Get video information and create thumbnail
        await progress_msg.edit_text("🔍 **Analyzing Video...**")
        
        try:
            # Get video information using FFprobe
            probe = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration:stream=width,height,codec_name",
                "-of", "json",
                input_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await probe.communicate()
            video_info = json.loads(stdout.decode('utf-8'))
            
            duration = float(video_info['format']['duration'])
            
            # Extract thumbnail
            await progress_msg.edit_text("🖼️ **Extracting Thumbnail...**")
            thumbnail = f"thumb_{os.path.basename(input_file)}.jpg"
            
            thumb_cmd = [
                "ffmpeg", "-ss", str(duration/2),
                "-i", input_file,
                "-vframes", "1",
                "-vf", "scale=320:-1",
                "-q:v", "2",
                thumbnail
            ]
            
            process = await asyncio.create_subprocess_exec(
                *thumb_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            if not os.path.exists(thumbnail):
                print("Thumbnail extraction failed, continuing without thumbnail")
                thumbnail = None
            
        except Exception as e:
            print(f"Video info/thumbnail error: {str(e)}")
            duration = 0
            thumbnail = None

        # Start compression
        output_file = f"compressed_{state.custom_name}"
        
        compression_text = (
            "🎯 **Starting Compression**\n\n"
            f"⚙️ **Settings:**\n"
            f"• Resolution: {state.resolution}\n"
            f"• Preset: {state.preset}\n"
            f"• CRF: {state.crf}\n"
            f"• Codec: {state.codec}\n"
            f"• Pixel Format: {state.pixel_format}\n\n"
            "⏳ Compressing... Please wait..."
        )
        await progress_msg.edit_text(compression_text)

        # FFmpeg compression command
        ffmpeg_cmd = [
            "ffmpeg", "-i", input_file,
            "-c:v", state.codec,
            "-preset", state.preset,
            "-crf", str(state.crf),
            "-vf", f"scale={state.resolution}",
            "-pix_fmt", state.pixel_format,
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",  # Enable fast start for web playback
            "-y",  # Overwrite output file if exists
            output_file
        ]

        # Start compression process
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1024 * 1024  # Increase buffer limit to 1MB
        )

        # Track FFmpeg progress with larger chunks
        async def read_stream(stream):
            output = []
            try:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    output.append(line.decode('utf-8', errors='replace').strip())
            except ValueError as e:
                print(f"Stream reading error: {str(e)}")
            return output

        # Process FFmpeg output
        while True:
            try:
                stderr_line = await process.stderr.readline()
                if not stderr_line:
                    break
                
                try:
                    line = stderr_line.decode('utf-8', errors='replace').strip()
                    
                    # Update progress message with FFmpeg output
                    if 'time=' in line:
                        time_match = re.search(r'time=(\d+:\d+:\d+.\d+)', line)
                        fps_match = re.search(r'fps=\s*(\d+)', line)
                        speed_match = re.search(r'speed=\s*(\d+\.?\d*x)', line)
                        
                        progress_text = (
                            "🎯 **Compressing Video**\n\n"
                            f"⏱️ Time: {time_match.group(1) if time_match else 'N/A'}\n"
                            f"🎞️ FPS: {fps_match.group(1) if fps_match else 'N/A'}\n"
                            f"⚡ Speed: {speed_match.group(1) if speed_match else 'N/A'}\n\n"
                            "Please wait..."
                        )
                        try:
                            await progress_msg.edit_text(progress_text)
                        except Exception as e:
                            print(f"Progress update error: {str(e)}")
                
                except Exception as e:
                    print(f"Line processing error: {str(e)}")
                    continue
            
            except ValueError as e:
                print(f"Stream reading error: {str(e)}")
                continue
            except Exception as e:
                print(f"Unknown error: {str(e)}")
                continue

        # Wait for process to complete
        return_code = await process.wait()
        if return_code != 0:
            raise Exception(f"FFmpeg process failed with return code {return_code}")

        # Get file sizes for comparison
        original_size = os.path.getsize(input_file)
        compressed_size = os.path.getsize(output_file)

        # Upload the compressed video
        await progress_msg.edit_text("📤 **Starting Upload...**")
        
        upload_start_time = time.time()
        
        try:
            caption = (
                f"🎥 **{state.custom_name}**\n\n"
                f"🎯 **Compression Info:**\n"
                f"• Resolution: {state.resolution}\n"
                f"• Preset: {state.preset}\n"
                f"• CRF: {state.crf}\n"
                f"• Original Size: {format_size(original_size)}\n"
                f"• Compressed Size: {format_size(compressed_size)}\n"
                f"• Space Saved: {((original_size - compressed_size) / original_size) * 100:.1f}%"
            )

            if state.output_format == "video":
                await client.send_video(
                    state.message.chat.id,
                    output_file,
                    thumb=thumbnail,
                    duration=int(duration),
                    caption=caption,
                    progress=progress_callback,
                    progress_args=(progress_msg, upload_start_time, "Uploading Video")
                )
            else:
                await client.send_document(
                    state.message.chat.id,
                    output_file,
                    thumb=thumbnail,
                    caption=caption,
                    progress=progress_callback,
                    progress_args=(progress_msg, upload_start_time, "Uploading File")
                )

            # Show completion message
            time_taken = time.time() - start_time
            completion_text = (
                "✅ **Compression Complete!**\n\n"
                f"📊 **Statistics:**\n"
                f"• Original Size: {format_size(original_size)}\n"
                f"• Compressed Size: {format_size(compressed_size)}\n"
                f"• Space Saved: {((original_size - compressed_size) / original_size) * 100:.1f}%\n"
                f"• Time Taken: {time.strftime('%H:%M:%S', time.gmtime(time_taken))}\n\n"
                "🔄 Send another video to compress again!"
            )
            await progress_msg.edit_text(completion_text)

        except FloodWait as e:
            await progress_msg.edit_text(f"⚠️ Upload rate limited. Waiting for {e.value} seconds...")
            await asyncio.sleep(e.value)
            raise Exception("Upload retry needed")
        except Exception as e:
            raise Exception(f"Upload failed: {str(e)}")

    except Exception as main_error:
        error_text = (
            "❌ **Compression Failed**\n\n"
            f"Error: `{str(main_error)}`\n\n"
            "Please try again or contact support."
        )
        await progress_msg.edit_text(error_text)
        
    finally:
        # Cleanup
        try:
            for file in [input_file, output_file, thumbnail]:
                if file and os.path.exists(file):
                    os.remove(file)
        except Exception as e:
            print(f"Cleanup error: {str(e)}")
        
        # Clear user state
        if state.message.from_user.id in user_states:
            del user_states[state.message.from_user.id]


# Add command handlers
@app.on_message(filters.command("cancel"))
async def cancel_command(client, message):
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
        await message.reply_text(
            "✅ **Compression Cancelled**\n\n"
            "Send another video to start again!"
        )
    else:
        await message.reply_text(
            "❌ **No Active Compression**\n\n"
            "Send a video to start compression!"
        )

# Start the bot
print("🤖 Bot is running...")
app.run()
