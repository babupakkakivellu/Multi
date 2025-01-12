from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import os
import json
import asyncio
import subprocess
import time
from typing import Dict, Set
from datetime import datetime

# Bot configuration
app = Client(
    "stream_remover_bot",
    api_id="16501053",
    api_hash="d8c9b01c863dabacc484c2c06cdd0f6e",
    bot_token="6738287955:AAE5lXdu_kbQevdyImUIJ84CTwwNhELjHK4"
)

COMPRESSION_PRESETS = {
    'ultrafast': '⚡️ Ultrafast - Fastest, Lowest Compression',
    'superfast': '🚀 Superfast - Very Fast, Low Compression',
    'veryfast': '⏩ Veryfast - Fast, Better Compression',
    'faster': '▶️ Faster - Good Balance',
    'fast': '📊 Fast - Better Quality',
    'medium': '⭐️ Medium - Default Balance',
    'slow': '🎯 Slow - Better Quality',
    'slower': '💎 Slower - High Quality',
    'veryslow': '🏆 Veryslow - Best Quality'
}

VIDEO_FORMATS = {
    'avc': '📹 AVC (H.264) - Better Compatibility',
    'hevc': '🎥 HEVC (H.265) - Better Compression'
}

PIXEL_FORMATS = {
    'yuv420p': '⚪️ YUV420P - Standard Compatibility',
    'yuv444p': '⭕️ YUV444P - Best Quality',
    'yuv420p10le': '🔘 YUV420P 10-bit - HDR Support'
}

RESOLUTIONS = {
    'source': '📺 Source Resolution',
    '2160': '4K (3840x2160)',
    '1440': 'QHD (2560x1440)',
    '1080': 'FHD (1920x1080)',
    '720': 'HD (1280x720)',
    '480': 'SD (854x480)'
}

# Default settings
DEFAULT_COMPRESSION_SETTINGS = {
    'preset': 'medium',
    'resolution': 'source',
    'pixel_format': 'yuv420p',
    'crf': 23,
    'video_format': 'avc'
}

# Modify your existing user_data structure
user_data: Dict[int, dict] = {}

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
            return self.format_time(elapsed)
        return "0s"

    @staticmethod
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

def create_progress_bar(current, total, length=20):
    filled = int(length * current // total)
    bar = "━" * filled + "─" * (length - filled)
    percent = current * 100 / total
    return bar, percent

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

        if action == "download":
            status = "📥 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗶𝗻𝗴..."
        else:
            status = "📤𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴..."

        await message.edit_text(
            f"{status}\n\n"
            f"┌ **Progress:** {current_mb} / {total_mb}\n"
            f"├ **Speed:** {speed}/s\n"
            f"├ **Time:** {elapsed_time}\n"
            f"└ {bar} {percent:.1f}%"
        )
    except Exception as e:
        print(f"Progress update error: {str(e)}")
class ProgressHandler:
    def __init__(self):
        self.timer = Timer()
        self.timer.start()

    async def update_progress(self, message, current, total, start_time, action_text="Processing"):
        if not self.timer.should_update() and current != total:
            return

        try:
            bar, percent = create_progress_bar(current, total)
            elapsed_time = self.timer.get_elapsed_time()
            current_mb = format_size(current)
            total_mb = format_size(total)
            speed = format_size(current/(time.time()-start_time))

            await message.edit_text(
                f"⚙️ {action_text}...\n\n"
                f"┌ **Progress:** {current_mb} / {total_mb}\n"
                f"├ **Speed:** {speed}/s\n"
                f"├ **Time:** {elapsed_time}\n"
                f"└ {bar} {percent:.1f}%"
            )
        except Exception as e:
            print(f"Progress update error: {str(e)}")

async def create_caption(original_size: int, processed_size: int, user: dict) -> str:
    if user.get('new_filename'):
        filename = user['new_filename']
    else:
        filename = os.path.basename(user['file_path'])

    saved_space = original_size - processed_size
    saved_percent = (saved_space / original_size) * 100 if original_size > 0 else 0

    if user.get('processing_type') == 'compress':
        settings = user['compression_settings']
        caption = (
            f"**{filename}**\n\n"
            f"┌ **Codec:** {settings['video_format'].upper()}\n"
            f"├ **Resolution:** {settings['resolution']}p\n"
            f"├ **Preset:** {settings['preset']}\n"
            f"├ **CRF:** {settings['crf']}\n"
            f"├ **Original Size:** {format_size(original_size)}\n"
            f"├ **Compressed Size:** {format_size(processed_size)}\n"
            f"└ **Saved:** {format_size(saved_space)} ({saved_percent:.1f}%)"
        )
    else:
        caption = (
            f"**{filename}**\n\n"
            f"┌ **Streams Removed:** {len(user['selected_streams'])}\n"
            f"├ **Original Size:** {format_size(original_size)}\n"
            f"├ **New Size:** {format_size(processed_size)}\n"
            f"└ **Saved:** {format_size(saved_space)} ({saved_percent:.1f}%)"
        )

    return caption

async def process_compression_settings(message, user):
    """Process compression settings and display current configuration"""
    settings = user['compression_settings']
    
    # Calculate estimated output size
    input_size = os.path.getsize(user['file_path'])
    size_multipliers = {
        'hevc': 0.6,  # HEVC typically achieves better compression
        'avc': 0.8,   # AVC is less efficient
    }
    resolution_multipliers = {
        'source': 1.0,
        '2160': 1.0,
        '1440': 0.7,
        '1080': 0.5,
        '720': 0.3,
        '480': 0.15
    }
    
    codec_mult = size_multipliers.get(settings['video_format'], 0.8)
    res_mult = resolution_multipliers.get(settings['resolution'], 1.0)
    crf_mult = 1.0 + (23 - settings['crf']) * 0.05
    
    estimated_size = input_size * codec_mult * res_mult * crf_mult
    
    compression_info = (
        "**🗜️ Compression Settings:**\n\n"
        f"┌ **Video Codec:** {settings['video_format'].upper()}\n"
        f"├ **Preset:** {settings['preset']}\n"
        f"├ **Resolution:** {settings['resolution']}p\n"
        f"├ **Pixel Format:** {settings['pixel_format']}\n"
        f"├ **CRF Value:** {settings['crf']}\n"
        f"├ **Input Size:** {format_size(input_size)}\n"
        f"└ **Estimated Size:** {format_size(estimated_size)}\n\n"
        "Select your options below:"
    )
    
    buttons = create_compression_buttons(settings)
    await message.edit_text(
        compression_info,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def create_progress_callback(progress_handler, message, start_time, action_text):
    async def callback(current, total):
        await progress_handler.update_progress(message, current, total, start_time, action_text)
    return callback

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
        
        # Extract duration, width, and height
        duration = int(float(metadata['format']['duration']))
        video_stream = next((s for s in metadata['streams'] if s['codec_type'] == 'video'), None)
        width = int(video_stream['width']) if video_stream else 0
        height = int(video_stream['height']) if video_stream else 0
        
        # Generate thumbnail
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
        
        return {
            'thumb_path': thumbnail_path if os.path.exists(thumbnail_path) else None,
            'duration': duration,
            'width': width,
            'height': height
        }
    except Exception as e:
        print(f"Thumbnail extraction error: {str(e)}")
        return None

def get_streamsinfo(file_path: str) -> list:
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_streams',
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)['streams']

def get_stream_info(stream):
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
    
    buttons.append([
        InlineKeyboardButton("✅ 𝗣𝗿𝗼𝗰𝗲𝘀", callback_data="continue"),
        InlineKeyboardButton("❌ 𝗖𝗮𝗻𝗰𝗲𝗹", callback_data="cancel")
    ])
    
    return buttons

def create_compression_buttons(settings: dict) -> list:
    buttons = []
    
    # Video Format Section
    buttons.append([InlineKeyboardButton("═══ 🎬 VIDEO FORMAT ═══", callback_data="header")])
    for fmt, desc in VIDEO_FORMATS.items():
        prefix = "☑️" if settings['video_format'] == fmt else "⬜️"
        buttons.append([InlineKeyboardButton(
            f"{prefix} {desc}",
            callback_data=f"compress_format_{fmt}"
        )])
    
    # Preset Section
    buttons.append([InlineKeyboardButton("═══ ⚙️ PRESET ═══", callback_data="header")])
    for preset, desc in COMPRESSION_PRESETS.items():
        prefix = "☑️" if settings['preset'] == preset else "⬜️"
        buttons.append([InlineKeyboardButton(
            f"{prefix} {desc}",
            callback_data=f"compress_preset_{preset}"
        )])
    
    # Resolution Section
    buttons.append([InlineKeyboardButton("═══ 📏 RESOLUTION ═══", callback_data="header")])
    for res, desc in RESOLUTIONS.items():
        prefix = "☑️" if settings['resolution'] == res else "⬜️"
        buttons.append([InlineKeyboardButton(
            f"{prefix} {desc}",
            callback_data=f"compress_res_{res}"
        )])
    
    # Pixel Format Section
    buttons.append([InlineKeyboardButton("═══ 🎨 PIXEL FORMAT ═══", callback_data="header")])
    for fmt, desc in PIXEL_FORMATS.items():
        prefix = "☑️" if settings['pixel_format'] == fmt else "⬜️"
        buttons.append([InlineKeyboardButton(
            f"{prefix} {desc}",
            callback_data=f"compress_pixfmt_{fmt}"
        )])
    
    # CRF Section
    buttons.append([InlineKeyboardButton("═══ 📊 QUALITY (CRF) ═══", callback_data="header")])
    current_crf = settings['crf']
    buttons.append([
        InlineKeyboardButton("➖", callback_data="compress_crf_down"),
        InlineKeyboardButton(f"🎯 CRF: {current_crf}", callback_data="header"),
        InlineKeyboardButton("➕", callback_data="compress_crf_up")
    ])
    
    # Control Buttons
    buttons.append([
        InlineKeyboardButton("✅ 𝗣𝗿𝗼𝗰𝗲𝘀𝘀", callback_data="compress_process"),
        InlineKeyboardButton("❌ 𝗖𝗮𝗻𝗰𝗲𝗹", callback_data="cancel")
    ])
    
    return buttons

async def get_video_duration(file_path: str) -> float:
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json',
            file_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, _ = await process.communicate()
        data = json.loads(stdout)
        return float(data['format']['duration'])
    except:
        return 0.0

def create_rename_buttons() -> list:
    buttons = [
        [InlineKeyboardButton("✏️ 𝗥𝗲𝗻𝗮𝗺𝗲", callback_data="rename")],
        [
            InlineKeyboardButton("📹 𝗦𝗲𝗻𝗱 𝗮𝘀 𝗩𝗶𝗱𝗲𝗼", callback_data="upload_video"),
            InlineKeyboardButton("📄 𝗦𝗲𝗻𝗱 𝗮𝘀 𝗗𝗼𝗰𝘂𝗺𝗲𝗻𝘁", callback_data="upload_document")
        ],
        [InlineKeyboardButton("⬅️ 𝗕𝗮𝗰𝗸", callback_data="back_to_streams")]
    ]
    return buttons

async def process_progress(message, current, total, start_time):
    if not hasattr(process_progress, 'timer'):
        process_progress.timer = Timer()
        process_progress.timer.start()

    if not process_progress.timer.should_update() and current != total:
        return

    try:
        bar, percent = create_progress_bar(current, total)
        elapsed_time = process_progress.timer.get_elapsed_time()
        current_mb = format_size(current)
        total_mb = format_size(total)
        speed = format_size(current/(time.time()-start_time))

        await message.edit_text(
            f"⚙️ 𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴...\n\n"
            f"┌ **Progress:** {current_mb} / {total_mb}\n"
            f"├ **Speed:** {speed}/s\n"
            f"├ **Time:** {elapsed_time}\n"
            f"└ {bar} {percent:.1f}%"
        )
    except Exception as e:
        print(f"Progress update error: {str(e)}")

async def compress_video(input_file: str, settings: dict, message, start_time) -> str:
    try:
        output_file = f"compressed_{os.path.basename(input_file)}"
        
        # Get video duration for progress calculation
        duration = await get_video_duration(input_file)
        total_size = os.path.getsize(input_file)
        
        # Build FFmpeg command
        cmd = ['ffmpeg', '-i', input_file]
        
        # Video codec settings
        if settings['video_format'] == 'hevc':
            cmd.extend(['-c:v', 'libx265'])
        else:
            cmd.extend(['-c:v', 'libx264'])
        
        # Add compression settings
        cmd.extend([
            '-preset', settings['preset'],
            '-crf', str(settings['crf']),
            '-pix_fmt', settings['pixel_format']
        ])
        
        # Resolution scaling
        if settings['resolution'] != 'source':
            height = settings['resolution']
            cmd.extend(['-vf', f'scale=-2:{height}'])
        
        # Copy audio streams
        cmd.extend(['-c:a', 'copy'])
        
        # Progress and output settings
        cmd.extend([
            '-progress', 'pipe:1',
            '-y', output_file
        ])
        
        # Start FFmpeg process
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        while True:
            if process.stdout is None:
                break
                
            line = await process.stdout.readline()
            if not line:
                break
                
            try:
                # Parse FFmpeg progress
                line_text = line.decode('utf-8')
                if 'out_time_ms=' in line_text:
                    time_ms = int(line_text.split('out_time_ms=')[1])
                    progress = time_ms / (duration * 1000000)
                    current_size = int(total_size * progress)
                    
                    # Update progress bar
                    await process_progress(message, current_size, total_size, start_time)
            except:
                pass
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"FFmpeg error: {stderr.decode()}")
        
        if not os.path.exists(output_file):
            raise Exception("Output file was not created")
            
        return output_file
        
    except Exception as e:
        raise Exception(f"Compression failed: {str(e)}")

# Modify the process_video function to include progress updates
async def process_video(input_file: str, streams_to_remove: Set[int], total_streams: int, message) -> str:
    try:
        start_time = time.time()
        output_file = f"processed_{os.path.basename(input_file)}"
        total_size = os.path.getsize(input_file)
        
        progress_handler = ProgressHandler()
        
        cmd = ['ffmpeg', '-i', input_file]
        
        for i in range(total_streams):
            if i not in streams_to_remove:
                cmd.extend(['-map', f'0:{i}'])
        
        cmd.extend([
            '-c', 'copy',
            '-progress', 'pipe:1',
            output_file
        ])
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        while True:
            if process.stdout is None:
                break
                
            line = await process.stdout.readline()
            if not line:
                break
                
            line = line.decode('utf-8').strip()
            
            if line.startswith('out_time_ms='):
                try:
                    time_ms = int(line.split('=')[1])
                    current_size = min(total_size * (time_ms / (total_size * 8)), total_size)
                    await progress_handler.update_progress(
                        message, 
                        current_size, 
                        total_size, 
                        start_time,
                        "Processing"
                    )
                except:
                    pass

        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise Exception(f"FFmpeg error: {error_message}")
        
        if not os.path.exists(output_file):
            raise Exception("Output file was not created")
            
        return output_file
        
    except Exception as e:
        raise Exception(f"Processing failed: {str(e)}")

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text(
        "**🎥 Stream Remover Bot**\n\n"
        "Send me any video file to:\n"
        "• 👀 View all available streams\n"
        "• ✂️ Select streams to remove\n"
        "• 📝 Rename file (optional)\n"
        "• 📤 Choose upload format\n\n"
        "ℹ️ Supported formats: MP4, MKV, AVI, etc."
    )

@app.on_message(filters.video | filters.document)
async def handle_video(client, message: Message):
    try:
        start_time = time.time()
        status_msg = await message.reply_text("⚡ 𝗜𝗻𝗶𝘁𝗶𝗮𝗹𝗶𝘇𝗶𝗻𝗴...")
        
        # Initialize user data
        user_data[message.from_user.id] = {
            'file_path': None,
            'streams': None,
            'selected_streams': set(),
            'awaiting_rename': False,
            'new_filename': None,
            'compression_settings': DEFAULT_COMPRESSION_SETTINGS.copy(),
            'mode': None  # 'compress' or 'remove_streams'
        }
        
        # Download video
        file_path = await message.download(
            progress=lambda current, total: progress(
                current, total, status_msg, start_time, "download"
            )
        )
        
        user_data[message.from_user.id]['file_path'] = file_path
        
        # Show operation selection buttons
        buttons = [
            [InlineKeyboardButton("✂️ Remove Streams", callback_data="mode_remove_streams")],
            [InlineKeyboardButton("🗜️ Compress Video", callback_data="mode_compress")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        
        await status_msg.edit_text(
            "**🎯 Choose Operation:**\n\n"
            "• ✂️ Remove Streams - Remove unwanted audio/subtitle tracks\n"
            "• 🗜️ Compress Video - Reduce file size with custom settings",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error:** {str(e)}")
        if message.from_user.id in user_data:
            del user_data[message.from_user.id]

@app.on_message(filters.text & filters.private)
async def handle_rename(client, message: Message):
    user_id = message.from_user.id
    
    if user_id in user_data and user_data[user_id].get('awaiting_rename'):
        # Get the stored message ID
        last_bot_message_id = user_data[user_id].get('last_bot_message_id')
        
        if message.text == "/cancel":
            user_data[user_id]['awaiting_rename'] = False
            buttons = create_rename_buttons()
            
            await client.edit_message_text(
                chat_id=message.chat.id,
                message_id=last_bot_message_id,
                text="**📤 Choose upload options:**\n\n"
                "• ✏️ Rename - Change filename\n"
                "• 📹 Video - Better for watching in Telegram\n"
                "• 📄 Document - Original quality",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await message.delete()
            return

        user_data[user_id]['new_filename'] = message.text
        user_data[user_id]['awaiting_rename'] = False
        buttons = create_rename_buttons()
        
        # Edit the bot's previous message using the stored message ID
        await client.edit_message_text(
            chat_id=message.chat.id,
            message_id=last_bot_message_id,
            text=f"**✅ Filename set to:** `{message.text}`\n\n"
                 "Now choose upload format:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        # Delete the user's message containing the new filename
        await message.delete()

@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    if user_id not in user_data and callback_query.data != "header":
        await callback_query.answer("Session expired. Please send the video again.", show_alert=True)
        return
    
    if callback_query.data == "header":
        await callback_query.answer("Section header")
        return

    data = callback_query.data
    user = user_data[user_id]
    
    try:
        # Initial Operation Choice
        if data == "start_process":
            buttons = [
                [InlineKeyboardButton("✂️ Remove Streams", callback_data="remove_streams")],
                [InlineKeyboardButton("🗜️ Compress Video", callback_data="compress_start")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ]
            await callback_query.message.edit_text(
                "**🎯 Choose Operation:**\n\n"
                "• ✂️ Remove Streams - Remove unwanted audio/subtitle tracks\n"
                "• 🗜️ Compress Video - Reduce file size with custom settings\n\n"
                f"Started at: {current_time}",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # Stream Removal Handlers
        elif data == "remove_streams":
            user['processing_type'] = 'remove_streams'
            streams = get_streamsinfo(user['file_path'])
            user['streams'] = streams
            buttons = create_stream_buttons(streams, user['selected_streams'])
            await callback_query.message.edit_text(
                "**🎯 𝗦𝗲𝗹𝗲𝗰𝘁 𝘀𝘁𝗿𝗲𝗮𝗺𝘀 𝘁𝗼 𝗿𝗲𝗺𝗼𝘃𝗲:**\n\n"
                "⬜️ = Keep stream\n"
                "☑️ = Remove stream\n\n"
                "_Select all streams you want to remove and press Process._",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data.startswith("stream_"):
            stream_index = int(data.split("_")[1])
            if stream_index in user['selected_streams']:
                user['selected_streams'].remove(stream_index)
            else:
                user['selected_streams'].add(stream_index)
            
            buttons = create_stream_buttons(user['streams'], user['selected_streams'])
            await callback_query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # Compression Handlers
        elif data == "compress_start":
            user['processing_type'] = 'compress'
            user['compression_settings'] = DEFAULT_COMPRESSION_SETTINGS.copy()
            await process_compression_settings(callback_query.message, user)

        elif data.startswith("compress_format_"):
            format_choice = data.split("_")[2]
            user['compression_settings']['video_format'] = format_choice
            await process_compression_settings(callback_query.message, user)

        elif data.startswith("compress_preset_"):
            preset_choice = data.split("_")[2]
            user['compression_settings']['preset'] = preset_choice
            await process_compression_settings(callback_query.message, user)

        elif data.startswith("compress_res_"):
            resolution_choice = data.split("_")[2]
            user['compression_settings']['resolution'] = resolution_choice
            await process_compression_settings(callback_query.message, user)

        elif data.startswith("compress_pixfmt_"):
            pixfmt_choice = data.split("_")[2]
            user['compression_settings']['pixel_format'] = pixfmt_choice
            await process_compression_settings(callback_query.message, user)

        elif data.startswith("compress_crf_"):
            if data.endswith("up"):
                user['compression_settings']['crf'] = min(51, user['compression_settings']['crf'] + 1)
            else:
                user['compression_settings']['crf'] = max(0, user['compression_settings']['crf'] - 1)
            await process_compression_settings(callback_query.message, user)

        # Process Handlers (Both Compression and Stream Removal)
        elif data == "continue" or data == "compress_process":
            try:
                start_time = time.time()
                progress_handler = ProgressHandler()
            
                status_msg = await callback_query.message.edit_text(
                    "⚙️ Initializing process..."
                )
                
                processing_type = user.get('processing_type', 'unknown')
            
                async def update_status(text: str):
                    try:
                        await status_msg.edit_text(text)
                    except Exception as e:
                        print(f"Status update error: {str(e)}")
            
                try:
                    if processing_type == 'compress':
                        output_file = await compress_video(
                            user['file_path'],
                            user['compression_settings'],
                            update_status,
                            start_time
                        )
                    else:
                        output_file = await process_video(
                            user['file_path'],
                            user['selected_streams'],
                            status_msg
                        )    
                
                    # Get file metadata and prepare for upload
                    thumb_data = await extract_thumbnail(output_file)
                    original_size = os.path.getsize(user['file_path'])
                    processed_size = os.path.getsize(output_file)
                
                    # Create upload progress handler
                    async def upload_progress(current, total):
                        await progress_handler(current, total, update_status, upload_start_time, "Uploading")
                
                    # Send file with progress
                    caption = await create_caption(original_size, processed_size, user)
                    if data == "upload_video" or processing_type == 'compress':
                        await client.send_video(
                            callback_query.message.chat.id,
                            output_file,
                            caption=caption,
                            duration=thumb_data.get('duration'),
                            width=thumb_data.get('width'),
                            height=thumb_data.get('height'),
                            thumb=thumb_data.get('thumb_path'),
                            progress=upload_progress
                        )
                    else:
                        await client.send_document(
                            callback_query.message.chat.id,
                            output_file,
                            caption=caption,
                            thumb=thumb_data.get('thumb_path'),
                            progress=upload_progress
                        )
                
                    # Success message
                    await status_msg.edit_text("✅ Process completed successfully!")
                
                except Exception as e:
                    await status_msg.edit_text(f"❌ Error: {str(e)}")
                finally:
                    # Cleanup
                    cleanup_files = [output_file]
                    if thumb_data and thumb_data.get('thumb_path'):
                        cleanup_files.append(thumb_data['thumb_path'])
                
                    for file in cleanup_files:
                        try:
                            if os.path.exists(file):
                                os.remove(file)
                        except Exception as e:
                            print(f"Cleanup error: {str(e)}")
                        
                    if user_id in user_data:
                        del user_data[user_id]
                    
            except Exception as e:
                await callback_query.message.edit_text(f"❌ Error: {str(e)}")
                if user_id in user_data:
                    del user_data[user_id]

        # Rename Handlers
        elif data == "rename":
            user['awaiting_rename'] = True
            user['last_bot_message_id'] = callback_query.message.id
            await callback_query.message.edit_text(
                "**✏️ Please send the new filename:**\n\n"
                "• Send the new name without extension\n"
                "• Click /cancel to cancel renaming",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")
                ]])
            )

        elif data == "back_to_menu":
            if user.get('processing_type') == 'compress':
                await process_compression_settings(callback_query.message, user)
            else:
                buttons = create_stream_buttons(user['streams'], user['selected_streams'])
                await callback_query.message.edit_text(
                    "**🎯 𝗦𝗲𝗹𝗲𝗰𝘁 𝘀𝘁𝗿𝗲𝗮𝗺𝘀 𝘁𝗼 𝗿𝗲𝗺𝗼𝘃𝗲:**\n\n"
                    "⬜️ = Keep stream\n"
                    "☑️ = Remove stream\n\n"
                    "_Select all streams you want to remove and press Process._",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )

        # Cancel Handler
        elif data == "cancel":
            if os.path.exists(user['file_path']):
                os.remove(user['file_path'])
            if user_id in user_data:
                del user_data[user_id]
            await callback_query.message.edit_text(
                "❌ **Operation cancelled.**\n"
                f"Cancelled at: {current_time}"
            )

    except Exception as e:
        error_message = f"❌ **Error:** {str(e)}\n" f"Error occurred at: {current_time}"
        await callback_query.message.edit_text(error_message)
        if user_id in user_data:
            del user_data[user_id]


print("🚀 Bot is starting...")
app.run()
