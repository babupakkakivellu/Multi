from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import os
import json
import asyncio
import subprocess
import time
import re
from typing import Dict, Set
from datetime import datetime, timedelta

# Bot configuration
app = Client(
    "stream_remover_bot",
    api_id="YOUR_API_ID",
    api_hash="YOUR_API_HASH",
    bot_token="YOUR_BOT_TOKEN"
)

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

# Store user data
user_data: Dict[int, dict] = {}

# Default compression settings
DEFAULT_SETTINGS = {
    'preset': 'medium',
    'pixel_format': 'yuv420p10le',
    'crf': 23,
    'resolution': 'Original',
    'copy_audio': True,
    'copy_subs': True
}

class FFmpegProgress:
    def __init__(self, message):
        self.message = message
        self.start_time = time.time()
        self.last_update_time = 0
        self.update_interval = 2

    def create_progress_bar(self, current, total, length=20):
        filled = int(length * current // total)
        bar = "█" * filled + "░" * (length - filled)
        percent = current * 100 / total
        return bar, percent

    async def update_progress(self, current, total, operation):
        now = time.time()
        if now - self.last_update_time < self.update_interval and current != total:
            return

        self.last_update_time = now
        elapsed_time = int(now - self.start_time)
        speed = current / elapsed_time if elapsed_time > 0 else 0
        eta = int((total - current) / speed) if speed > 0 else 0

        bar, percent = self.create_progress_bar(current, total)
        
        try:
            await self.message.edit_text(
                f"{operation}\n\n"
                f"╭─❰ 𝙿𝚛𝚘𝚐𝚛𝚎𝚜𝚜 ❱\n"
                f"│ \n"
                f"├ {bar}\n"
                f"├ 𝙿𝚎𝚛𝚌𝚎𝚗𝚝𝚊𝚐𝚎: {percent:.1f}%\n"
                f"├ 𝚂𝚙𝚎𝚎𝚍: {format_size(speed)}/s\n"
                f"├ 𝙿𝚛𝚘𝚌𝚎𝚜𝚜𝚎𝚍: {format_size(current)}\n"
                f"├ 𝚂𝚒𝚣𝚎: {format_size(total)}\n"
                f"├ 𝙴𝚃𝙰: {format_time(eta)}\n"
                f"│ \n"
                f"╰─❰ @YourBotUsername ❱"
            )
        except Exception as e:
            print(f"Progress update error: {str(e)}")

def format_time(seconds):
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}m {seconds}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours}h {minutes}m {seconds}s"

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

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
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def create_final_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Rename File", callback_data="rename_file")],
        [InlineKeyboardButton("📹 Send as Video", callback_data="upload_video"),
         InlineKeyboardButton("📄 Send as Document", callback_data="upload_document")],
        [InlineKeyboardButton("⬅️ Back", callback_data="compress_start"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

HELP_TEXT = """
**🎥 Video Processing Bot**

Send me any video file to:
• 🎯 Compress with custom settings
• ✂️ Remove unwanted streams
• 📊 Adjust quality (CRF 15-30)
• 🎨 Choose pixel format
• ✏️ Rename output file

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

# Bot username for progress bar
BOT_USERNAME = "YourBotUsername"  # Replace with your bot's username

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

def create_stream_buttons(streams: list, selected_streams: Set[int]) -> list:
    buttons = []
    
    stream_groups = {
        'video': ('🎥 VIDEO STREAMS', []),
        'audio': ('🔊 AUDIO STREAMS', []),
        'subtitle': ('💭 SUBTITLE STREAMS', []),
        'other': ('📎 OTHER STREAMS', [])
    }
    
    for i, stream in enumerate(streams):
        codec_type = stream.get('codec_type', 'unknown').lower()
        stream_info = get_stream_info(stream)
        
        group = codec_type if codec_type in stream_groups else 'other'
        prefix = "☑️" if i in selected_streams else "⬜️"
        
        stream_groups[group][1].append({
            'index': i,
            'info': stream_info,
            'prefix': prefix
        })
    
    for group_name, (header, group_streams) in stream_groups.items():
        if group_streams:
            buttons.append([InlineKeyboardButton(f"═══ {header} ═══", callback_data="header")])
            for stream in group_streams:
                buttons.append([InlineKeyboardButton(
                    f"{stream['prefix']} {stream['info']}",
                    callback_data=f"stream_{stream['index']}"
                )])
    
    buttons.extend([
        [InlineKeyboardButton("✅ Continue", callback_data="continue"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="back_to_main")]
    ])
    
    return buttons

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

async def run_ffmpeg_with_progress(command, message, input_file):
    progress_tracker = FFmpegProgress(message)
    
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

    while True:
        if process.stderr:
            line = await process.stderr.readline()
            if not line:
                break
            
            line = line.decode('utf-8')
            matches = time_pattern.search(line)
            
            if matches:
                hours, minutes, seconds = map(int, matches.groups())
                current_time = hours * 3600 + minutes * 60 + seconds
                await progress_tracker.update_progress(
                    current_time,
                    int(total_duration),
                    "🔄 Processing Video..."
                )

    await process.wait()
    return process.returncode == 0

def get_stream_info(stream: dict) -> str:
    codec_type = stream.get('codec_type', 'unknown').upper()
    codec_name = stream.get('codec_name', 'unknown').upper()
    language = stream.get('tags', {}).get('language', 'und')
    title = stream.get('tags', {}).get('title', '')
    
    info = f"{codec_type} ({codec_name}) - {language}"
    if title:
        info += f" - {title}"
        
    if codec_type == 'VIDEO':
        width = stream.get('width', '?')
        height = stream.get('height', '?')
        fps = stream.get('r_frame_rate', '').split('/')[0]
        info += f" [{width}x{height}]"
        if fps:
            info += f" {fps}fps"
    elif codec_type == 'AUDIO':
        channels = stream.get('channels', '?')
        info += f" ({channels}ch)"
        
    return info

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text(
        "**🎥 Welcome to Video Processing Bot!**\n\n"
        "Send me any video file to:\n"
        "• 🎯 Compress with HEVC (x265)\n"
        "• ✂️ Remove unwanted streams\n"
        "• 📊 Adjust quality (CRF 15-30)\n"
        "• 🎨 Choose pixel format\n"
        "• ✏️ Rename output file\n\n"
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
        start_time = time.time()
        
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
            'start_time': start_time
        }
        
        # Download progress wrapper
        async def progress_wrapper(current, total):
            if not hasattr(progress_wrapper, 'progress_tracker'):
                progress_wrapper.progress_tracker = FFmpegProgress(status_msg)
            
            await progress_wrapper.progress_tracker.update_progress(
                current, 
                total,
                "📥 Downloading Video..."
            )
        
        # Download the file
        file_path = await message.download(
            progress=progress_wrapper
        )
        
        user_data[user_id]['file_path'] = file_path
        
        # Analyze video
        await status_msg.edit_text("🔍 Analyzing video streams...")
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
        
        # Handle rename input
        if user_id in user_data and user_data[user_id].get('awaiting_rename'):
            if message.text == "/cancel":
                user_data[user_id]['awaiting_rename'] = False
                await message.reply_text(
                    "❌ Rename cancelled.",
                    reply_markup=create_final_menu()
                )
            else:
                # Update filename
                user_data[user_id]['new_filename'] = message.text
                user_data[user_id]['awaiting_rename'] = False
                
                # Show format selection menu
                await message.reply_text(
                    f"✅ **File will be renamed to:**\n`{message.text}`\n\n"
                    "Now choose upload format:",
                    reply_markup=create_final_menu()
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

async def progress(current, total, message, start_time, action):
    if not hasattr(progress, 'timer'):
        progress.timer = Timer()
        progress.timer.start()

    if not progress.timer.should_update() and current != total:
        return

    try:
        bar, percent = create_progress_bar(current, total)
        elapsed_time = progress.timer.get_elapsed_time()
        current_mb = format_size(current)
        total_mb = format_size(total)
        speed = format_size(current/(time.time()-start_time))

        status = "📥 Downloading..." if action == "download" else "📤 Uploading..."

        await message.edit_text(
            f"{status}\n\n"
            f"╭─❰ 𝙿𝚛𝚘𝚐𝚛𝚎𝚜𝚜 ❱\n"
            f"│ \n"
            f"├ {bar}\n"
            f"├ 𝙿𝚎𝚛𝚌𝚎𝚗𝚝𝚊𝚐𝚎: {percent:.1f}%\n"
            f"├ 𝚂𝚙𝚎𝚎𝚍: {speed}/s\n"
            f"├ 𝙿𝚛𝚘𝚌𝚎𝚜𝚜𝚎𝚍: {current_mb}\n"
            f"├ 𝚂𝚒𝚣𝚎: {total_mb}\n"
            f"├ 𝚃𝚒𝚖𝚎: {elapsed_time}\n"
            f"│ \n"
            f"╰─❰ @{BOT_USERNAME} ❱"
        )
    except Exception as e:
        print(f"Progress update error: {str(e)}")

class Timer:
    def __init__(self):
        self.start_time = None
        self.last_update = 0

    def start(self):
        self.start_time = time.time()
        self.last_update = 0

    def should_update(self):
        current_time = time.time()
        if current_time - self.last_update >= 2:
            self.last_update = current_time
            return True
        return False

    def get_elapsed_time(self):
        if self.start_time:
            elapsed = int(time.time() - self.start_time)
            return format_time(elapsed)
        return "0s"

@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    try:
        user_id = callback_query.from_user.id
        data = callback_query.data
        
        # ... (previous handlers remain same until upload handling)

        # Handle Upload Format
        elif data in ["upload_video", "upload_document"]:
            if not user_data[user_id].get('new_filename'):
                await callback_query.answer("Please rename the file first!", show_alert=True)
                return

            status_msg = await callback_query.message.edit_text("🔄 Preparing upload...")
            
            try:
                input_file = user_data[user_id]['compressed_file']
                new_filename = user_data[user_id]['new_filename']
                file_ext = os.path.splitext(input_file)[1]
                final_filename = f"{new_filename}{file_ext}"

                # Extract thumbnail and metadata
                thumb_data = await extract_thumbnail(input_file)
                if not thumb_data:
                    raise Exception("Failed to extract video metadata")

                # Calculate compression ratio
                original_size = os.path.getsize(user_data[user_id]['file_path'])
                compressed_size = os.path.getsize(input_file)
                ratio = (1 - (compressed_size / original_size)) * 100

                # Prepare caption
                settings = user_data[user_id]['compression_settings']
                caption = (
                    f"**{final_filename}**\n\n"
                    f"⚙️ **Compression Info:**\n"
                    f"• Preset: `{settings['preset']}`\n"
                    f"• CRF: `{settings['crf']}`\n"
                    f"• Pixel Format: `{settings['pixel_format']}`\n"
                    f"• Size Reduced: `{ratio:.1f}%`\n"
                    f"• Duration: `{timedelta(seconds=int(thumb_data['duration']))}`\n\n"
                    f"🎬 **Original Size:** `{format_size(original_size)}`\n"
                    f"📦 **New Size:** `{format_size(compressed_size)}`\n"
                    f"📊 **Compression Ratio:** `{ratio:.1f}%`"
                )

                async def upload_progress(current, total):
                    await progress(current, total, status_msg, time.time(), "upload")

                if data == "upload_video":
                    await client.send_video(
                        callback_query.message.chat.id,
                        input_file,
                        filename=final_filename,
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
                        filename=final_filename,
                        caption=caption,
                        thumb=thumb_data['thumb_path'],
                        progress=upload_progress,
                        force_document=True
                    )

                await status_msg.edit_text(
                    "✅ **Process Completed Successfully!**\n\n"
                    f"📊 Size Reduced by: `{ratio:.1f}%`\n"
                    f"📦 Final Size: `{format_size(compressed_size)}`"
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

        # Handle Stream Removal
        elif data == "remove_streams":
            streams = get_streamsinfo(user_data[user_id]['file_path'])
            user_data[user_id]['streams'] = streams
            buttons = create_stream_buttons(streams, set())
            await callback_query.message.edit_text(
                "**✂️ Stream Selection**\n\n"
                "⬜️ = Keep stream\n"
                "☑️ = Remove stream\n\n"
                "Select streams to remove:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # Handle Stream Selection
        elif data.startswith("stream_"):
            stream_index = int(data.split("_")[1])
            if stream_index in user_data[user_id]['selected_streams']:
                user_data[user_id]['selected_streams'].remove(stream_index)
            else:
                user_data[user_id]['selected_streams'].add(stream_index)
            
            buttons = create_stream_buttons(
                user_data[user_id]['streams'],
                user_data[user_id]['selected_streams']
            )
            await callback_query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # Process Stream Removal
        elif data == "continue" and user_data[user_id].get('streams'):
            if not user_data[user_id]['selected_streams']:
                await callback_query.answer("No streams selected to remove!", show_alert=True)
                return

            status_msg = await callback_query.message.edit_text("🔄 Processing streams...")
            
            try:
                output_file = await process_video(
                    user_data[user_id]['file_path'],
                    user_data[user_id]['selected_streams'],
                    len(user_data[user_id]['streams'])
                )
                
                user_data[user_id]['compressed_file'] = output_file
                await status_msg.edit_text(
                    "✅ **Streams Removed Successfully!**\n\n"
                    "Now:\n"
                    "1️⃣ Rename the file (mandatory)\n"
                    "2️⃣ Choose upload format",
                    reply_markup=create_final_menu()
                )
            
            except Exception as e:
                await status_msg.edit_text(f"❌ **Error:** {str(e)}")

        elif data == "cancel":
            # Cleanup and exit
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

    except Exception as e:
        error_msg = f"❌ **Error:** {str(e)}"
        try:
            await callback_query.answer(error_msg, show_alert=True)
        except:
            await callback_query.message.edit_text(error_msg)

# Start the bot
print("🚀 Bot is starting...")
app.run()
