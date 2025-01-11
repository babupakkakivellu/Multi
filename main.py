# Part 1: Imports and Global Variables
import asyncio
import os
import json
import re
import time
from datetime import timedelta
from typing import Set
from pyrogram.types import CallbackQuery
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# Replace with your bot token and username
API_ID = 16501053
API_HASH = "d8c9b01c863dabacc484c2c06cdd0f6e"
BOT_TOKEN = "6738287955:AAE5lXdu_kbQevdyImUIJ84CTwwNhELjHK4"
BOT_USERNAME = "YOUR_BOT_USERNAME"

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_data = {}

# Part 2: Settings, Constants and Helper Functions

# Compression Settings
COMPRESSION_SETTINGS = {
    'presets': ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'],
    'pixel_formats': [
        ('yuv420p', '8-bit Compatible'),
        ('yuv420p10le', '10-bit Standard'),
        ('yuv444p10le', '10-bit High Quality')
    ],
    'crf_range': range(15, 31)
}

# Default Settings
DEFAULT_SETTINGS = {
    'preset': 'medium',
    'pixel_format': 'yuv420p10le',
    'crf': 23,
    'copy_audio': True,
    'copy_subs': True
}

# Help Message
HELP_TEXT = """
**🎥 Video Processing Bot**

Send me any video file to:
• 🎯 Compress with HEVC (x265)
• ✂️ Remove unwanted streams
• 📊 Adjust quality (CRF 15-30)
• 🎨 Choose pixel format

**Features:**
• HEVC (x265) encoding
• 10-bit support
• Multiple presets
• Stream selection
• Progress tracking

**Commands:**
/start - Start the bot
/help - Show this help
/cancel - Cancel current process

ℹ️ Supported formats: MP4, MKV, AVI, etc.
"""

def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}m {seconds:.1f}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours}h {minutes}m {seconds:.1f}s"

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

def create_progress_bar(current, total, length=20):
    filled = int(length * current // total)
    bar = "█" * filled + "░" * (length - filled)
    percent = current * 100 / total
    return bar, percent

class FFmpegProgress:
    def __init__(self, message):
        self.message = message
        self.start_time = time.time()
        self.last_update_time = 0
        self.update_interval = 2

    async def update_progress(self, current, total, operation):
        now = time.time()
        if now - self.last_update_time < self.update_interval and current != total:
            return

        self.last_update_time = now
        elapsed_time = int(now - self.start_time)
        speed = current / elapsed_time if elapsed_time > 0 else 0
        eta = int((total - current) / speed) if speed > 0 else 0

        bar, percent = create_progress_bar(current, total)
        
        try:
            await self.message.edit_text(
                f"{operation}\n\n"
                f"╭─❰ 𝙿𝚛𝚘𝚐𝚛𝚎𝚜𝚜 ❱\n"
                f"│\n"
                f"├ {bar}\n"
                f"├ **Progress:** `{percent:.1f}%`\n"
                f"├ **Speed:** `{format_size(speed)}/s`\n"
                f"├ **Processed:** `{format_size(current)}`\n"
                f"├ **Total:** `{format_size(total)}`\n"
                f"├ **Time:** `{format_time(elapsed_time)}`\n"
                f"├ **ETA:** `{format_time(eta)}`\n"
                f"│\n"
                f"╰─❰ @{BOT_USERNAME} ❱"
            )
        except Exception as e:
            print(f"Progress update error: {str(e)}")

def create_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Compress Video", callback_data="compress_start")],
        [InlineKeyboardButton("✂️ Remove Streams", callback_data="remove_streams")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def create_settings_menu(settings):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Encoding Preset", callback_data="show_preset")],
        [InlineKeyboardButton("📊 CRF Value", callback_data="show_crf")],
        [InlineKeyboardButton("🎨 Pixel Format", callback_data="show_pixfmt")],
        [InlineKeyboardButton(f"🔊 Audio: {'Copy' if settings['copy_audio'] else 'Re-encode'}", 
                            callback_data="toggle_audio")],
        [InlineKeyboardButton(f"💬 Subtitles: {'Copy' if settings['copy_subs'] else 'Remove'}", 
                            callback_data="toggle_subs")],
        [InlineKeyboardButton("✅ Start Process", callback_data="start_compress")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def create_final_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Rename File", callback_data="rename_file")],
        [InlineKeyboardButton("📹 Send as Video", callback_data="upload_video"),
         InlineKeyboardButton("📄 Send as Document", callback_data="upload_document")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

async def progress(current, total, message, start_time, action):
    if not hasattr(progress, 'last_update_time'):
        progress.last_update_time = 0

    now = time.time()
    if now - progress.last_update_time < 2:
        return

    progress.last_update_time = now
    elapsed_time = int(now - start_time)
    speed = current / elapsed_time if elapsed_time > 0 else 0
    eta = int((total - current) / speed) if speed > 0 else 0

    bar, percent = create_progress_bar(current, total)
    
    status = "📥 Downloading..." if action == "download" else "📤 Uploading..."
    
    try:
        await message.edit_text(
            f"{status}\n\n"
            f"╭─❰ 𝙿𝚛𝚘𝚐𝚛𝚎𝚜𝚜 ❱\n"
            f"│\n"
            f"├ {bar}\n"
            f"├ **Progress:** `{percent:.1f}%`\n"
            f"├ **Speed:** `{format_size(speed)}/s`\n"
            f"├ **Processed:** `{format_size(current)}`\n"
            f"├ **Total:** `{format_size(total)}`\n"
            f"├ **Time:** `{format_time(elapsed_time)}`\n"
            f"├ **ETA:** `{format_time(eta)}`\n"
            f"│\n"
            f"╰─❰ @{BOT_USERNAME} ❱"
        )
    except Exception as e:
        print(f"Progress update error: {str(e)}")


# Part 3: Video Processing and FFmpeg Handlers

async def extract_thumbnail(file_path):
    try:
        probe = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await probe.communicate()
        metadata = json.loads(stdout)
        
        format_info = metadata.get('format', {})
        video_stream = next((s for s in metadata['streams'] if s['codec_type'] == 'video'), None)
        
        if not video_stream:
            raise Exception("No video stream found")
            
        duration = float(format_info.get('duration', 0))
        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))
        
        thumbnail_path = f"thumb_{os.path.splitext(os.path.basename(file_path))[0]}.jpg"
        cmd = [
            'ffmpeg', '-ss', str(duration//2),
            '-i', file_path,
            '-vframes', '1',
            '-vf', 'scale=320:-1',
            '-y', thumbnail_path
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if not os.path.exists(thumbnail_path):
            raise Exception("Failed to generate thumbnail")
        
        return {
            'thumb_path': thumbnail_path,
            'duration': duration,
            'width': width,
            'height': height,
            'format': format_info.get('format_name', ''),
            'size': int(format_info.get('size', 0))
        }
    except Exception as e:
        print(f"Thumbnail extraction error: {str(e)}")
        return None

async def run_ffmpeg_with_progress(command, message, input_file):
    try:
        # Get video duration
        duration_cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', 
            input_file
        ]
        
        process = await asyncio.create_subprocess_exec(
            *duration_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        total_duration = float(stdout.decode().strip())

        # Start FFmpeg process
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        time_pattern = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.\d+")
        speed_pattern = re.compile(r"speed=(\d+\.\d+)x")
        fps_pattern = re.compile(r"fps=\s*(\d+)")
        
        last_update_time = 0
        update_interval = 2

        while True:
            if process.stderr:
                line = await process.stderr.readline()
                if not line:
                    break
                
                line = line.decode('utf-8')
                time_matches = time_pattern.search(line)
                speed_matches = speed_pattern.search(line)
                fps_matches = fps_pattern.search(line)
                
                if time_matches:
                    current_time = time.time()
                    if current_time - last_update_time >= update_interval:
                        last_update_time = current_time
                        
                        hours, minutes, seconds = map(int, time_matches.groups())
                        current_time = hours * 3600 + minutes * 60 + seconds
                        speed = float(speed_matches.group(1)) if speed_matches else 0
                        fps = fps_matches.group(1) if fps_matches else "0"
                        
                        progress = current_time / total_duration
                        bar_length = 20
                        filled_length = int(bar_length * progress)
                        bar = '█' * filled_length + '░' * (bar_length - filled_length)
                        
                        eta = (total_duration - current_time) / speed if speed > 0 else 0
                        
                        await message.edit_text(
                            f"🔄 **Processing Video...**\n\n"
                            f"╭─❰ 𝙿𝚛𝚘𝚐𝚛𝚎𝚜𝚜 ❱\n"
                            f"│\n"
                            f"├ {bar}\n"
                            f"├ **Progress:** `{progress*100:.1f}%`\n"
                            f"├ **Speed:** `{speed:.1f}x`\n"
                            f"├ **FPS:** `{fps}`\n"
                            f"├ **Time:** `{format_time(current_time)} / {format_time(total_duration)}`\n"
                            f"├ **ETA:** `{format_time(eta)}`\n"
                            f"│\n"
                            f"╰─❰ @{BOT_USERNAME} ❱"
                        )

        await process.wait()
        return process.returncode == 0

    except Exception as e:
        print(f"FFmpeg progress error: {str(e)}")
        return False

async def get_video_info(file_path: str) -> dict:
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"FFprobe error: {stderr.decode()}")
            
        info = json.loads(stdout.decode())
        return format_video_info(info)
    except Exception as e:
        raise Exception(f"Failed to get video info: {str(e)}")

def format_video_info(info: dict) -> dict:
    streams = info.get('streams', [])
    format_info = info.get('format', {})
    
    video_stream = next((s for s in streams if s['codec_type'] == 'video'), None)
    audio_streams = [s for s in streams if s['codec_type'] == 'audio']
    subtitle_streams = [s for s in streams if s['codec_type'] == 'subtitle']
    
    formatted_info = {
        'duration': float(format_info.get('duration', 0)),
        'size': int(format_info.get('size', 0)),
        'format': format_info.get('format_name', ''),
        'streams': {
            'video': [],
            'audio': [],
            'subtitle': []
        }
    }
    
    if video_stream:
        formatted_info['streams']['video'].append({
            'codec': video_stream.get('codec_name', '').upper(),
            'width': video_stream.get('width', 0),
            'height': video_stream.get('height', 0),
            'fps': eval(video_stream.get('r_frame_rate', '0/1')),
            'bitrate': int(video_stream.get('bit_rate', 0))
        })
    
    for audio in audio_streams:
        formatted_info['streams']['audio'].append({
            'codec': audio.get('codec_name', '').upper(),
            'channels': audio.get('channels', 0),
            'language': audio.get('tags', {}).get('language', 'und'),
            'title': audio.get('tags', {}).get('title', '')
        })
    
    for sub in subtitle_streams:
        formatted_info['streams']['subtitle'].append({
            'codec': sub.get('codec_name', '').upper(),
            'language': sub.get('tags', {}).get('language', 'und'),
            'title': sub.get('tags', {}).get('title', '')
        })
    
    return formatted_info

async def process_video(input_file: str, streams_to_remove: Set[int], total_streams: int) -> str:
    try:
        output_file = f"processed_{os.path.basename(input_file)}"
        
        cmd = ['ffmpeg', '-i', input_file]
        
        for i in range(total_streams):
            if i not in streams_to_remove:
                cmd.extend(['-map', f'0:{i}'])
        
        cmd.extend(['-c', 'copy', output_file])
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise Exception(f"FFmpeg error: {error_message}")
        
        if not os.path.exists(output_file):
            raise Exception("Output file was not created")
            
        return output_file
        
    except Exception as e:
        raise Exception(f"Processing failed: {str(e)}")


# Part 4: Message and Command Handlers

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text(
        "**🎥 Welcome to Video Processing Bot!**\n\n"
        "Send me any video file to:\n"
        "• 🎯 Compress with HEVC (x265)\n"
        "• ✂️ Remove unwanted streams\n"
        "• 📊 Adjust quality (CRF 15-30)\n"
        "• 🎨 Choose pixel format\n\n"
        "**Features:**\n"
        "• Advanced compression\n"
        "• 10-bit support\n"
        "• Multiple presets\n"
        "• Stream selection\n"
        "• Progress tracking\n\n"
        "ℹ️ Send any video to start processing!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💡 Help", callback_data="show_help")],
            [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/YourUsername")]
        ])
    )

@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    await message.reply_text(HELP_TEXT)

@app.on_message(filters.video | filters.document)
async def handle_video(client, message: Message):
    try:
        user_id = message.from_user.id
        
        # Send initial processing message
        status_msg = await message.reply_text(
            "⚡ **Initializing Process**\n\n"
            "Please wait while I analyze the video..."
        )
        
        # Initialize user data with default settings
        user_data[user_id] = {
            'file_path': None,
            'streams': None,
            'selected_streams': set(),
            'compression_settings': DEFAULT_SETTINGS.copy(),
            'status_msg': status_msg,
            'start_time': time.time()
        }

        # Analyze video first
        await status_msg.edit_text("🔍 Analyzing video streams...")
        
        # Download progress wrapper
        async def progress_wrapper(current, total):
            try:
                await progress(current, total, status_msg, time.time(), "download")
            except Exception as e:
                print(f"Progress error: {str(e)}")
        
        # Download the file
        file_path = await message.download(
            progress=progress_wrapper
        )
        
        user_data[user_id]['file_path'] = file_path
        
        # Get video info
        video_info = await get_video_info(file_path)
        user_data[user_id]['video_info'] = video_info
        
        # Format video information
        size_mb = video_info['size'] / (1024 * 1024)
        duration = int(video_info['duration'])
        
        if video_info['streams']['video']:
            video_stream = video_info['streams']['video'][0]
            info_text = (
                "**📝 Video Information:**\n\n"
                f"• **Size:** `{size_mb:.2f}` MB\n"
                f"• **Duration:** `{timedelta(seconds=duration)}`\n"
                f"• **Resolution:** `{video_stream['width']}x{video_stream['height']}`\n"
                f"• **Codec:** `{video_stream['codec']}`\n"
                f"• **FPS:** `{video_stream['fps']:.2f}`\n\n"
                f"• **Audio Tracks:** `{len(video_info['streams']['audio'])}`\n"
                f"• **Subtitles:** `{len(video_info['streams']['subtitle'])}`\n\n"
                "**Choose operation:**"
            )
        else:
            info_text = "⚠️ No video stream found!\n\nChoose operation:"
        
        # Show main menu
        await status_msg.edit_text(
            info_text,
            reply_markup=create_main_menu()
        )
        
    except Exception as e:
        error_msg = f"❌ **Error:** {str(e)}"
        try:
            await status_msg.edit_text(error_msg)
        except:
            await message.reply_text(error_msg)
        
        # Cleanup
        if user_id in user_data:
            file_path = user_data[user_id].get('file_path')
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            del user_data[user_id]

@app.on_message(filters.text & filters.private)
async def handle_text(client, message: Message):
    try:
        user_id = message.from_user.id
        
        if user_id in user_data and user_data[user_id].get('awaiting_rename'):
            status_msg = user_data[user_id].get('status_msg')
            
            if message.text in ["/skip", "/cancel"]:
                # Use original filename
                original_name = os.path.splitext(os.path.basename(user_data[user_id]['file_path']))[0]
                user_data[user_id]['new_filename'] = original_name
            else:
                # Update filename
                user_data[user_id]['new_filename'] = message.text
            
            user_data[user_id]['awaiting_rename'] = False
            
            # Edit original message with upload format options
            if status_msg:
                await status_msg.edit_text(
                    f"**📝 File Name:** `{user_data[user_id]['new_filename']}`\n\n"
                    "Choose upload format:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📹 Send as Video", callback_data="upload_video"),
                         InlineKeyboardButton("📄 Send as Document", callback_data="upload_document")],
                        [InlineKeyboardButton("✏️ Rename Again", callback_data="rename_file")],
                        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                    ])
                )
            
            # Delete user's message
            await message.delete()
            return
        
        # Handle other text messages
        await message.reply_text(
            "📤 Please send me a video file to process.\n"
            "Use /help to see available options."
        )
        
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")

@app.on_message(filters.command("cancel"))
async def cancel_command(client, message: Message):
    try:
        user_id = message.from_user.id
        if user_id in user_data:
            # Cleanup files
            file_path = user_data[user_id].get('file_path')
            compressed_file = user_data[user_id].get('compressed_file')
            
            for path in [file_path, compressed_file]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass
            
            del user_data[user_id]
            
            await message.reply_text(
                "❌ Operation cancelled.\n\n"
                "Send another video to start again."
            )
        else:
            await message.reply_text("No active process to cancel.")
            
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")


@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    try:
        user_id = callback_query.from_user.id
        data = callback_query.data
        
        if user_id not in user_data and data not in ["show_help", "cancel"]:
            await callback_query.answer("Session expired. Please send video again.", show_alert=True)
            return

        if data == "header":
            await callback_query.answer("Section header")
            return

        # Help and Main Menu
        if data == "show_help":
            await callback_query.message.edit_text(
                HELP_TEXT,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")
                ]])
            )
            
        elif data == "back_to_start":
            await callback_query.message.edit_text(
                "**🎥 Welcome to Video Processing Bot!**\n\n"
                "Send me any video file to:\n"
                "• 🎯 Compress with HEVC (x265)\n"
                "• ✂️ Remove unwanted streams\n"
                "• 📊 Adjust quality (CRF 15-30)\n"
                "• 🎨 Choose pixel format\n\n"
                "**Features:**\n"
                "• Advanced compression\n"
                "• 10-bit support\n"
                "• Multiple presets\n"
                "• Stream selection\n"
                "• Progress tracking\n\n"
                "ℹ️ Send any video to start processing!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💡 Help", callback_data="show_help")],
                    [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/YourUsername")]
                ])
            )

        # Compression Settings Menu
        elif data == "compress_start":
            settings = user_data[user_id]['compression_settings']
            await callback_query.message.edit_text(
                "**⚙️ Compression Settings**\n\n"
                f"Current Settings:\n"
                f"• Preset: `{settings['preset']}`\n"
                f"• CRF: `{settings['crf']}`\n"
                f"• Pixel Format: `{settings['pixel_format']}`\n"
                f"• Audio: `{'Copy' if settings['copy_audio'] else 'Re-encode'}`\n"
                f"• Subtitles: `{'Copy' if settings['copy_subs'] else 'Remove'}`\n\n"
                "Select option to modify:",
                reply_markup=create_settings_menu(settings)
            )

        # Show Preset Selection
        elif data == "show_preset":
            buttons = []
            row = []
            current_preset = user_data[user_id]['compression_settings']['preset']
            
            for preset in COMPRESSION_SETTINGS['presets']:
                current = "✅ " if preset == current_preset else ""
                row.append(InlineKeyboardButton(f"{current}{preset}", callback_data=f"preset_{preset}"))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="compress_start")])
            
            await callback_query.message.edit_text(
                "**⚙️ Select Encoding Preset:**\n\n"
                "• ultrafast = Fastest, largest size\n"
                "• medium = Balanced option\n"
                "• veryslow = Best compression, slowest\n\n"
                f"Current: `{current_preset}`",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # Show CRF Selection
        elif data == "show_crf":
            buttons = []
            row = []
            current_crf = user_data[user_id]['compression_settings']['crf']
            
            for crf in range(15, 31):
                current = "✅ " if crf == current_crf else ""
                row.append(InlineKeyboardButton(f"{current}{crf}", callback_data=f"crf_{crf}"))
                if len(row) == 4:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="compress_start")])
            
            await callback_query.message.edit_text(
                "**📊 Select CRF Value:**\n\n"
                "• 15-18 = Visually lossless\n"
                "• 19-23 = High quality\n"
                "• 24-27 = Medium quality\n"
                "• 28-30 = Low quality\n\n"
                f"Current: `{current_crf}`",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # Show Pixel Format Selection
        elif data == "show_pixfmt":
            buttons = []
            current_fmt = user_data[user_id]['compression_settings']['pixel_format']
            
            for fmt, desc in COMPRESSION_SETTINGS['pixel_formats']:
                current = "✅ " if fmt == current_fmt else ""
                buttons.append([InlineKeyboardButton(f"{current}{desc}", callback_data=f"pixfmt_{fmt}")])
            
            buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="compress_start")])
            
            await callback_query.message.edit_text(
                "**🎨 Select Pixel Format:**\n\n"
                "• 8-bit = Standard compatibility\n"
                "• 10-bit = Better quality, HDR support\n"
                "• 10-bit High = Best quality, larger size\n\n"
                f"Current: `{current_fmt}`",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # Handle Setting Updates
        elif data.startswith(("preset_", "pixfmt_", "crf_")):
            setting_type, value = data.split("_")
            settings = user_data[user_id]['compression_settings']
            
            if setting_type == "preset":
                settings['preset'] = value
            elif setting_type == "pixfmt":
                settings['pixel_format'] = value
            elif setting_type == "crf":
                settings['crf'] = int(value)
            
            await callback_query.answer(f"{setting_type.title()} updated!")
            await callback_query.message.edit_text(
                "**⚙️ Compression Settings**\n\n"
                f"• Preset: `{settings['preset']}`\n"
                f"• CRF: `{settings['crf']}`\n"
                f"• Pixel Format: `{settings['pixel_format']}`\n"
                f"• Audio: `{'Copy' if settings['copy_audio'] else 'Re-encode'}`\n"
                f"• Subtitles: `{'Copy' if settings['copy_subs'] else 'Remove'}`\n\n"
                "Select option to modify:",
                reply_markup=create_settings_menu(settings)
            )

        # Toggle Audio/Subtitle Settings
        elif data in ["toggle_audio", "toggle_subs"]:
            settings = user_data[user_id]['compression_settings']
            if data == "toggle_audio":
                settings['copy_audio'] = not settings['copy_audio']
            else:
                settings['copy_subs'] = not settings['copy_subs']
            
            await callback_query.message.edit_reply_markup(
                reply_markup=create_settings_menu(settings)
            )

        # Start Processing
        elif data == "start_compress":
            settings = user_data[user_id]['compression_settings']
            input_file = user_data[user_id]['file_path']
            output_file = f"compressed_{os.path.basename(input_file)}"
            status_msg = await callback_query.message.edit_text("🔄 Preparing compression...")

            try:
                command = [
                    "ffmpeg", "-y",
                    "-i", input_file,
                    "-c:v", "libx265",
                    "-preset", settings['preset'],
                    "-crf", str(settings['crf']),
                    "-pix_fmt", settings['pixel_format']
                ]

                if settings['copy_audio']:
                    command.extend(["-c:a", "copy"])
                else:
                    command.extend(["-c:a", "aac", "-b:a", "128k"])

                if settings['copy_subs']:
                    command.extend(["-c:s", "copy"])
                else:
                    command.extend(["-sn"])

                command.append(output_file)

                success = await run_ffmpeg_with_progress(command, status_msg, input_file)

                if success:
                    user_data[user_id]['compressed_file'] = output_file
                    await status_msg.edit_text(
                        "✅ **Compression Complete!**\n\n"
                        "Choose upload format:",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📹 Send as Video", callback_data="upload_video"),
                             InlineKeyboardButton("📄 Send as Document", callback_data="upload_document")],
                            [InlineKeyboardButton("✏️ Rename File", callback_data="rename_file")],
                            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                        ])
                    )
                else:
                    raise Exception("Compression failed")

            except Exception as e:
                await status_msg.edit_text(f"❌ **Error:** {str(e)}")
                if os.path.exists(output_file):
                    os.remove(output_file)

        # Handle Rename
        elif data == "rename_file":
            user_data[user_id]['awaiting_rename'] = True
            await callback_query.message.edit_text(
                "**✏️ Send new filename:**\n\n"
                "• Send the name without extension\n"
                "• /skip to use original name\n"
                "• /cancel to cancel process",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Back", callback_data="back_to_upload")]
                ])
            )

        # Handle Upload
        elif data in ["upload_video", "upload_document"]:
            status_msg = await callback_query.message.edit_text("🔄 Preparing upload...")
            
            try:
                input_file = user_data[user_id]['compressed_file']
                new_filename = user_data[user_id].get('new_filename', 
                    os.path.splitext(os.path.basename(input_file))[0])
                
                thumb_data = await extract_thumbnail(input_file)
                if not thumb_data:
                    raise Exception("Failed to extract video metadata")

                original_size = os.path.getsize(user_data[user_id]['file_path'])
                compressed_size = os.path.getsize(input_file)
                ratio = (1 - (compressed_size / original_size)) * 100

                settings = user_data[user_id]['compression_settings']
                caption = (
                    f"**{new_filename}**\n\n"
                    f"⚙️ **Compression Info:**\n"
                    f"• Preset: `{settings['preset']}`\n"
                    f"• CRF: `{settings['crf']}`\n"
                    f"• Pixel Format: `{settings['pixel_format']}`\n"
                    f"• Size Reduced: `{ratio:.1f}%`\n"
                    f"• Duration: `{timedelta(seconds=int(thumb_data['duration']))}`\n\n"
                    f"🎬 **Original Size:** `{format_size(original_size)}`\n"
                    f"📦 **New Size:** `{format_size(compressed_size)}`"
                )

                async def upload_progress(current, total):
                    await progress(current, total, status_msg, time.time(), "upload")

                if data == "upload_video":
                    await client.send_video(
                        callback_query.message.chat.id,
                        input_file,
                        caption=caption,
                        thumb=thumb_data['thumb_path'],
                        duration=int(thumb_data['duration']),
                        width=thumb_data['width'],
                        height=thumb_data['height'],
                        progress=upload_progress,
                        supports_streaming=True
                    )
                else:
                    await client.send_document(
                        callback_query.message.chat.id,
                        input_file,
                        caption=caption,
                        thumb=thumb_data['thumb_path'],
                        progress=upload_progress,
                        force_document=True
                    )

                await status_msg.edit_text(
                    "✅ **Process Completed Successfully!**\n\n"
                    f"📊 Size Reduced by: `{ratio:.1f}%`\n"
                    f"📦 Final Size: `{format_size(compressed_size)}`\n\n"
                    "Send another video to start again."
                )

            except Exception as e:
                await status_msg.edit_text(f"❌ **Error:** {str(e)}")
            finally:
                # Cleanup
                try:
                    if os.path.exists(input_file):
                        os.remove(input_file)
                    if thumb_data and thumb_data['thumb_path']:
                        os.remove(thumb_data['thumb_path'])
                except:
                    pass

        # Handle Cancel
        elif data == "cancel":
            if user_id in user_data:
                file_path = user_data[user_id].get('file_path')
                compressed_file = user_data[user_id].get('compressed_file')
                
                for path in [file_path, compressed_file]:
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except:
                            pass
                
                del user_data[user_id]
            
            await callback_query.message.edit_text(
                "❌ Operation cancelled.\n\n"
                "Send another video to start again."
            )

        # Handle Back to Upload Options
        elif data == "back_to_upload":
            await callback_query.message.edit_text(
                "Choose upload format:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📹 Send as Video", callback_data="upload_video"),
                     InlineKeyboardButton("📄 Send as Document", callback_data="upload_document")],
                    [InlineKeyboardButton("✏️ Rename File", callback_data="rename_file")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                ])
            )

        # Handle Stream Selection
        elif data == "remove_streams":
            video_info = user_data[user_id]['video_info']
            buttons = []
            
            # Add video streams
            for i, stream in enumerate(video_info['streams']['video']):
                buttons.append([InlineKeyboardButton(
                    f"🎥 Video: {stream['width']}x{stream['height']} ({stream['codec']})",
                    callback_data=f"stream_{i}"
                )])
            
            # Add audio streams
            for i, stream in enumerate(video_info['streams']['audio'], len(video_info['streams']['video'])):
                lang = stream['language']
                title = f" - {stream['title']}" if stream['title'] else ""
                buttons.append([InlineKeyboardButton(
                    f"🔊 Audio: {lang}{title} ({stream['codec']})",
                    callback_data=f"stream_{i}"
                )])
            
            # Add subtitle streams
            start_idx = len(video_info['streams']['video']) + len(video_info['streams']['audio'])
            for i, stream in enumerate(video_info['streams']['subtitle'], start_idx):
                lang = stream['language']
                title = f" - {stream['title']}" if stream['title'] else ""
                buttons.append([InlineKeyboardButton(
                    f"💬 Subtitle: {lang}{title}",
                    callback_data=f"stream_{i}"
                )])
            
            buttons.append([InlineKeyboardButton("✅ Continue", callback_data="process_streams")])
            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
            
            await callback_query.message.edit_text(
                "**✂️ Select Streams to Remove:**\n\n"
                "• Click to toggle stream removal\n"
                "• Selected streams will be removed\n"
                "• Click Continue when done",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # Handle Stream Toggle
        elif data.startswith("stream_"):
            stream_idx = int(data.split("_")[1])
            if stream_idx in user_data[user_id]['selected_streams']:
                user_data[user_id]['selected_streams'].remove(stream_idx)
            else:
                user_data[user_id]['selected_streams'].add(stream_idx)
            
            # Recreate stream selection menu with updated selections
            video_info = user_data[user_id]['video_info']
            buttons = []
            
            # Add video streams
            for i, stream in enumerate(video_info['streams']['video']):
                selected = "✅ " if i in user_data[user_id]['selected_streams'] else ""
                buttons.append([InlineKeyboardButton(
                    f"{selected}🎥 Video: {stream['width']}x{stream['height']} ({stream['codec']})",
                    callback_data=f"stream_{i}"
                )])
            
            # Add audio streams
            for i, stream in enumerate(video_info['streams']['audio'], len(video_info['streams']['video'])):
                selected = "✅ " if i in user_data[user_id]['selected_streams'] else ""
                lang = stream['language']
                title = f" - {stream['title']}" if stream['title'] else ""
                buttons.append([InlineKeyboardButton(
                    f"{selected}🔊 Audio: {lang}{title} ({stream['codec']})",
                    callback_data=f"stream_{i}"
                )])
            
            # Add subtitle streams
            start_idx = len(video_info['streams']['video']) + len(video_info['streams']['audio'])
            for i, stream in enumerate(video_info['streams']['subtitle'], start_idx):
                selected = "✅ " if i in user_data[user_id]['selected_streams'] else ""
                lang = stream['language']
                title = f" - {stream['title']}" if stream['title'] else ""
                buttons.append([InlineKeyboardButton(
                    f"{selected}💬 Subtitle: {lang}{title}",
                    callback_data=f"stream_{i}"
                )])
            
            buttons.append([InlineKeyboardButton("✅ Continue", callback_data="process_streams")])
            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
            
            await callback_query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # Process Stream Removal
        elif data == "process_streams":
            if not user_data[user_id]['selected_streams']:
                await callback_query.answer("No streams selected to remove!", show_alert=True)
                return

            status_msg = await callback_query.message.edit_text("🔄 Processing streams...")
            
            try:
                output_file = await process_video(
                    user_data[user_id]['file_path'],
                    user_data[user_id]['selected_streams'],
                    len(user_data[user_id]['video_info']['streams'])
                )
                
                user_data[user_id]['compressed_file'] = output_file
                await status_msg.edit_text(
                    "✅ **Streams Removed Successfully!**\n\n"
                    "Choose upload format:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📹 Send as Video", callback_data="upload_video"),
                         InlineKeyboardButton("📄 Send as Document", callback_data="upload_document")],
                        [InlineKeyboardButton("✏️ Rename File", callback_data="rename_file")],
                        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                    ])
                )
            
            except Exception as e:
                await status_msg.edit_text(f"❌ **Error:** {str(e)}")

    except Exception as e:
        error_msg = f"❌ **Error:** {str(e)}"
        try:
            await callback_query.answer(error_msg, show_alert=True)
        except:
            await callback_query.message.edit_text(error_msg)
# Start the bot
print("🚀 Bot is starting...")
app.run()

