# Part 1: Imports and Global Variables
import asyncio
import os
import json
import re
import time
from datetime import timedelta
from typing import Set, Dict, Any, Optional
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import API_ID, API_HASH, BOT_TOKEN, BOT_USERNAME, TEMP_DIR

# Create temp directory if it doesn't exist
os.makedirs(TEMP_DIR, exist_ok=True)

# Initialize bot
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# User session data
user_data: Dict[int, Dict[str, Any]] = {}

# Part 2: Settings and Constants
COMPRESSION_SETTINGS = {
    'presets': [
        ('ultrafast', 'Fastest (Largest Size)'),
        ('superfast', 'Very Fast'),
        ('veryfast', 'Fast'),
        ('faster', 'Quick'),
        ('medium', 'Balanced'),
        ('slow', 'Better Quality'),
        ('veryslow', 'Best Quality (Slowest)')
    ],
    'pixel_formats': [
        ('yuv420p', '8-bit Compatible'),
        ('yuv420p10le', '10-bit Standard'),
        ('yuv444p10le', '10-bit High Quality')
    ],
    'crf_range': {
        'low': range(15, 19),     # High Quality
        'medium': range(19, 24),   # Good Quality
        'high': range(24, 31)      # Smaller Size
    }
}

DEFAULT_SETTINGS = {
    'preset': 'medium',
    'pixel_format': 'yuv420p10le',
    'crf': 23,
    'copy_audio': True,
    'copy_subs': True
}

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

# Part 3: Helper Functions
def format_size(size: float, suffix: str = "B") -> str:
    """Format file size to human readable format"""
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(size) < 1024.0:
            return f"{size:3.1f} {unit}{suffix}"
        size /= 1024.0
    return f"{size:.1f} Y{suffix}"

def format_time(seconds: float) -> str:
    """Format time duration to human readable format"""
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

def create_progress_bar(current: float, total: float, length: int = 20) -> tuple[str, float]:
    """Create a progress bar with specified length"""
    filled_length = int(length * current // total)
    bar = "█" * filled_length + "░" * (length - filled_length)
    percent = current * 100 / total
    return bar, percent

# Part 4: Progress Tracking Classes and Functions

class FFmpegProgress:
    def __init__(self, message: Message):
        self.message = message
        self.start_time = time.time()
        self.last_update_time = 0
        self.update_interval = 2  # Update every 2 seconds
        self.last_current = 0
        self.highest_percentage = 0

    async def update_progress(self, current: int, total: int, operation: str = "Processing") -> None:
        now = time.time()
        if (now - self.last_update_time < self.update_interval and 
            current != total and 
            current < self.last_current + (1024 * 1024)):  # 1MB threshold
            return

        self.last_update_time = now
        self.last_current = current
        elapsed_time = int(now - self.start_time)
        speed = current / elapsed_time if elapsed_time > 0 else 0
        eta = int((total - current) / speed) if speed > 0 else 0

        # Calculate percentage and ensure it never decreases
        percent = (current * 100 / total)
        self.highest_percentage = max(self.highest_percentage, percent)
        bar, _ = create_progress_bar(current, total)
        
        try:
            await self.message.edit_text(
                f"🔄 **{operation}**\n\n"
                f"╭─❰ 𝙿𝚛𝚘𝚐𝚛𝚎𝚜𝚜 ❱\n"
                f"│\n"
                f"├ {bar}\n"
                f"├ **Speed:** `{format_size(speed)}/s`\n"
                f"├ **Processed:** `{format_size(current)}`\n"
                f"├ **Total:** `{format_size(total)}`\n"
                f"├ **Progress:** `{self.highest_percentage:.1f}%`\n"
                f"├ **Time:** `{format_time(elapsed_time)}`\n"
                f"├ **ETA:** `{format_time(eta)}`\n"
                f"│\n"
                f"╰─❰ @{BOT_USERNAME} ❱"
            )
        except Exception as e:
            print(f"Progress update error: {str(e)}")

async def parse_ffmpeg_progress(line: str) -> dict:
    """Parse FFmpeg progress information from output line"""
    progress_data = {}
    
    try:
        # Time pattern HH:MM:SS
        time_pattern = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.\d+")
        # Speed pattern (e.g., speed=2.5x)
        speed_pattern = re.compile(r"speed=\s*(\d+\.\d+)x")
        # FPS pattern
        fps_pattern = re.compile(r"fps=\s*(\d+)")
        # Size pattern (e.g., size=10kB)
        size_pattern = re.compile(r"size=\s*(\d+)kB")
        # Bitrate pattern
        bitrate_pattern = re.compile(r"bitrate=\s*(\d+\.\d+)kbits/s")
        
        # Extract time
        time_match = time_pattern.search(line)
        if time_match:
            hours, minutes, seconds = map(int, time_match.groups())
            progress_data['time'] = hours * 3600 + minutes * 60 + seconds
            
        # Extract speed
        speed_match = speed_pattern.search(line)
        if speed_match:
            progress_data['speed'] = float(speed_match.group(1))
            
        # Extract fps
        fps_match = fps_pattern.search(line)
        if fps_match:
            progress_data['fps'] = int(fps_match.group(1))
            
        # Extract size
        size_match = size_pattern.search(line)
        if size_match:
            progress_data['size'] = int(size_match.group(1)) * 1024  # Convert kB to bytes
            
        # Extract bitrate
        bitrate_match = bitrate_pattern.search(line)
        if bitrate_match:
            progress_data['bitrate'] = float(bitrate_match.group(1))
            
    except Exception as e:
        print(f"Error parsing FFmpeg progress: {str(e)}")
        
    return progress_data

async def run_ffmpeg_with_progress(command: list, message: Message, input_file: str) -> bool:
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
        total_size = os.path.getsize(input_file)  # Get input file size
        
        # Initialize progress tracker
        progress_tracker = FFmpegProgress(message)
        
        # Start FFmpeg process
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Monitor FFmpeg progress
        async for line in process.stderr:
            line = line.decode('utf-8')
            progress_data = await parse_ffmpeg_progress(line)
            
            if progress_data:
                current_time = progress_data.get('time', 0)
                current_size = progress_data.get('size', 0)
                
                # Calculate progress based on time and size
                time_progress = current_time / total_duration if total_duration > 0 else 0
                size_progress = current_size / total_size if total_size > 0 else 0
                
                # Use the more accurate progress metric
                current_progress = max(time_progress, size_progress)
                
                # Update progress display
                await progress_tracker.update_progress(
                    current=int(current_progress * total_size),
                    total=total_size,
                    operation="Encoding Video"
                )

        await process.wait()
        return process.returncode == 0

    except Exception as e:
        print(f"FFmpeg progress error: {str(e)}")
        return False

async def cleanup_files(user_id: int) -> None:
    """Clean up temporary files for a user"""
    if user_id in user_data:
        # List of files to clean up
        files_to_clean = [
            user_data[user_id].get('file_path'),
            user_data[user_id].get('compressed_file'),
            user_data[user_id].get('thumb_path')
        ]
        
        # Clean up each file
        for file_path in files_to_clean:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error cleaning up file {file_path}: {str(e)}")
        
        # Clear user data
        user_data.pop(user_id, None)

async def generate_thumbnail(input_file: str, duration: float = None) -> str:
    """Generate thumbnail from video file"""
    try:
        if not duration:
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
            duration = float(stdout.decode().strip())

        # Generate thumbnail at middle point
        thumbnail_path = os.path.join(TEMP_DIR, f"thumb_{os.path.splitext(os.path.basename(input_file))[0]}.jpg")
        cmd = [
            'ffmpeg', '-ss', str(duration/2),
            '-i', input_file,
            '-vframes', '1',
            '-vf', 'scale=320:-2',
            '-y', thumbnail_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if os.path.exists(thumbnail_path):
            return thumbnail_path
        
    except Exception as e:
        print(f"Error generating thumbnail: {str(e)}")
    
    return None

# Part 5: Menu Creation Functions

def create_main_menu() -> InlineKeyboardMarkup:
    """Create main menu with compression and stream options"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Compress Video", callback_data="compress_start")],
        [
            InlineKeyboardButton("✂️ Remove Streams", callback_data="remove_streams"),
            InlineKeyboardButton("⚙️ Settings", callback_data="show_settings")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def create_settings_menu(settings: dict) -> InlineKeyboardMarkup:
    """Create settings menu with current values"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Encoding Preset", callback_data="show_preset")],
        [InlineKeyboardButton("📊 CRF Value", callback_data="show_crf")],
        [InlineKeyboardButton("🎨 Pixel Format", callback_data="show_pixfmt")],
        [InlineKeyboardButton(
            f"🔊 Audio: {'Copy' if settings['copy_audio'] else 'Re-encode'}", 
            callback_data="toggle_audio"
        )],
        [InlineKeyboardButton(
            f"💬 Subtitles: {'Copy' if settings['copy_subs'] else 'Remove'}", 
            callback_data="toggle_subs"
        )],
        [InlineKeyboardButton("✅ Start Process", callback_data="start_compress")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def create_final_menu() -> InlineKeyboardMarkup:
    """Create final menu with upload options"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Rename File", callback_data="rename_file")],
        [
            InlineKeyboardButton("📹 Video", callback_data="upload_video"),
            InlineKeyboardButton("📄 Document", callback_data="upload_document")
        ],
        [InlineKeyboardButton("📊 Show Stats", callback_data="show_stats")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def create_stream_selection_menu(video_info: dict, selected_streams: Set[int]) -> InlineKeyboardMarkup:
    """Create menu for stream selection"""
    buttons = []
    
    # Add video streams
    for i, stream in enumerate(video_info['streams']['video']):
        selected = "✅ " if i in selected_streams else ""
        buttons.append([InlineKeyboardButton(
            f"{selected}🎥 Video: {stream['width']}x{stream['height']} ({stream['codec']})",
            callback_data=f"stream_{i}"
        )])
    
    # Add audio streams
    start_idx = len(video_info['streams']['video'])
    for i, stream in enumerate(video_info['streams']['audio'], start_idx):
        selected = "✅ " if i in selected_streams else ""
        lang = stream['language']
        title = f" - {stream['title']}" if stream.get('title') else ""
        buttons.append([InlineKeyboardButton(
            f"{selected}🔊 Audio: {lang}{title} ({stream['codec']})",
            callback_data=f"stream_{i}"
        )])
    
    # Add subtitle streams
    start_idx = start_idx + len(video_info['streams']['audio'])
    for i, stream in enumerate(video_info['streams']['subtitle'], start_idx):
        selected = "✅ " if i in selected_streams else ""
        lang = stream['language']
        title = f" - {stream['title']}" if stream.get('title') else ""
        buttons.append([InlineKeyboardButton(
            f"{selected}💬 Subtitle: {lang}{title}",
            callback_data=f"stream_{i}"
        )])
    
    # Add control buttons
    buttons.append([InlineKeyboardButton("✅ Continue", callback_data="process_streams")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    
    return InlineKeyboardMarkup(buttons)

# Part 6: Message Handlers

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
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
async def help_command(client: Client, message: Message):
    """Handle /help command"""
    await message.reply_text(HELP_TEXT)

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    """Handle /cancel command"""
    try:
        user_id = message.from_user.id
        if user_id in user_data:
            await cleanup_files(user_id)
            await message.reply_text(
                "❌ Operation cancelled.\n\n"
                "Send another video to start again."
            )
        else:
            await message.reply_text("No active process to cancel.")
            
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")

# Part 7: Video Handler and Processing Functions

@app.on_message(filters.video | filters.document)
async def handle_video(client: Client, message: Message):
    """Handle incoming video files"""
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

        # Download progress callback
        async def progress_wrapper(current: int, total: int):
            now = time.time()
            if not hasattr(progress_wrapper, 'last_update_time'):
                progress_wrapper.last_update_time = 0
            
            if now - progress_wrapper.last_update_time < 2:
                return
            
            progress_wrapper.last_update_time = now
            elapsed_time = int(now - user_data[user_id]['start_time'])
            speed = current / elapsed_time if elapsed_time > 0 else 0
            eta = int((total - current) / speed) if speed > 0 else 0
            
            bar, percent = create_progress_bar(current, total)
            try:
                await status_msg.edit_text(
                    f"📥 **Downloading Video...**\n\n"
                    f"╭─❰ 𝙿𝚛𝚘𝚐𝚛𝚎𝚜𝚜 ❱\n"
                    f"│\n"
                    f"├ {bar}\n"
                    f"├ **Speed:** `{format_size(speed)}/s`\n"
                    f"├ **Downloaded:** `{format_size(current)}`\n"
                    f"├ **Total:** `{format_size(total)}`\n"
                    f"├ **Progress:** `{percent:.1f}%`\n"
                    f"├ **Time:** `{format_time(elapsed_time)}`\n"
                    f"├ **ETA:** `{format_time(eta)}`\n"
                    f"│\n"
                    f"╰─❰ @{BOT_USERNAME} ❱"
                )
            except Exception as e:
                print(f"Progress update error: {str(e)}")
        
        # Download file
        try:
            file_path = os.path.join(TEMP_DIR, f"{message.id}_{message.from_user.id}")
            if message.video:
                file_path += ".mp4"
                await message.download(
                    file_name=file_path,
                    progress=progress_wrapper
                )
            else:
                # For document, try to keep original extension
                original_name = message.document.file_name
                ext = os.path.splitext(original_name)[1] or ".mp4"
                file_path += ext
                await message.download(
                    file_name=file_path,
                    progress=progress_wrapper
                )
        except Exception as e:
            raise Exception(f"Failed to download file: {str(e)}")

        user_data[user_id]['file_path'] = file_path
        
        # Get video metadata
        await status_msg.edit_text("🔍 **Analyzing video streams...**")
        
        # Get video info using FFprobe
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
                
            video_info = json.loads(stdout.decode())
            
            # Format video information
            format_info = video_info.get('format', {})
            streams = video_info.get('streams', [])
            
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
            
            # Process streams
            for stream in streams:
                stream_type = stream.get('codec_type')
                if stream_type == 'video':
                    formatted_info['streams']['video'].append({
                        'codec': stream.get('codec_name', '').upper(),
                        'width': stream.get('width', 0),
                        'height': stream.get('height', 0),
                        'fps': eval(stream.get('r_frame_rate', '0/1')),
                        'bitrate': int(stream.get('bit_rate', 0))
                    })
                elif stream_type == 'audio':
                    formatted_info['streams']['audio'].append({
                        'codec': stream.get('codec_name', '').upper(),
                        'channels': stream.get('channels', 0),
                        'language': stream.get('tags', {}).get('language', 'und'),
                        'title': stream.get('tags', {}).get('title', '')
                    })
                elif stream_type == 'subtitle':
                    formatted_info['streams']['subtitle'].append({
                        'codec': stream.get('codec_name', '').upper(),
                        'language': stream.get('tags', {}).get('language', 'und'),
                        'title': stream.get('tags', {}).get('title', '')
                    })
            
            user_data[user_id]['video_info'] = formatted_info
            
            # Format display message
            size_mb = formatted_info['size'] / (1024 * 1024)
            duration = int(formatted_info['duration'])
            
            if formatted_info['streams']['video']:
                video_stream = formatted_info['streams']['video'][0]
                info_text = (
                    "**📝 Video Information:**\n\n"
                    f"• **Size:** `{size_mb:.2f}` MB\n"
                    f"• **Duration:** `{timedelta(seconds=duration)}`\n"
                    f"• **Resolution:** `{video_stream['width']}x{video_stream['height']}`\n"
                    f"• **Codec:** `{video_stream['codec']}`\n"
                    f"• **FPS:** `{video_stream['fps']:.2f}`\n\n"
                    f"• **Audio Tracks:** `{len(formatted_info['streams']['audio'])}`\n"
                    f"• **Subtitles:** `{len(formatted_info['streams']['subtitle'])}`\n\n"
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
            raise Exception(f"Failed to analyze video: {str(e)}")
            
    except Exception as e:
        error_msg = f"❌ **Error:** {str(e)}"
        try:
            await status_msg.edit_text(error_msg)
        except:
            await message.reply_text(error_msg)
        
        # Cleanup
        await cleanup_files(user_id)

# Part 8: Callback Query Handlers

@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    """Handle callback queries from inline keyboards"""
    try:
        user_id = callback_query.from_user.id
        data = callback_query.data
        
        # Check for expired sessions
        if user_id not in user_data and data not in ["show_help", "cancel"]:
            await callback_query.answer("Session expired. Please send video again.", show_alert=True)
            return

        # Help and Navigation Handlers
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
                    [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/babupakkakivellu")]
                ])
            )

        # Compression Settings Handlers
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

        # Settings Selection Handlers
        elif data == "show_preset":
            settings = user_data[user_id]['compression_settings']
            buttons = []
            for preset, desc in COMPRESSION_SETTINGS['presets']:
                current = "✅ " if preset == settings['preset'] else ""
                buttons.append([InlineKeyboardButton(
                    f"{current}{desc}",
                    callback_data=f"preset_{preset}"
                )])
            buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="compress_start")])
            
            await callback_query.message.edit_text(
                "**⚙️ Select Encoding Preset:**\n\n"
                "• ultrafast = Fastest, largest size\n"
                "• medium = Balanced option\n"
                "• veryslow = Best compression, slowest\n\n"
                f"Current: `{settings['preset']}`",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data == "show_crf":
            settings = user_data[user_id]['compression_settings']
            buttons = []
            row = []
            for crf in range(15, 31):
                current = "✅ " if crf == settings['crf'] else ""
                row.append(InlineKeyboardButton(
                    f"{current}{crf}",
                    callback_data=f"crf_{crf}"
                ))
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
                f"Current: `{settings['crf']}`",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data == "show_pixfmt":
            settings = user_data[user_id]['compression_settings']
            buttons = []
            for fmt, desc in COMPRESSION_SETTINGS['pixel_formats']:
                current = "✅ " if fmt == settings['pixel_format'] else ""
                buttons.append([InlineKeyboardButton(
                    f"{current}{desc}",
                    callback_data=f"pixfmt_{fmt}"
                )])
            buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="compress_start")])
            
            await callback_query.message.edit_text(
                "**🎨 Select Pixel Format:**\n\n"
                "• 8-bit = Standard compatibility\n"
                "• 10-bit = Better quality, HDR support\n"
                "• 10-bit High = Best quality, larger size\n\n"
                f"Current: `{settings['pixel_format']}`",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # Settings Update Handlers
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

        # Toggle Settings Handlers
        elif data in ["toggle_audio", "toggle_subs"]:
            settings = user_data[user_id]['compression_settings']
            if data == "toggle_audio":
                settings['copy_audio'] = not settings['copy_audio']
            else:
                settings['copy_subs'] = not settings['copy_subs']
            
            await callback_query.message.edit_reply_markup(
                reply_markup=create_settings_menu(settings)
            )

        # Part 9: Compression Processing and Upload Handlers

        # Start Compression Process
        elif data == "start_compress":
            settings = user_data[user_id]['compression_settings']
            input_file = user_data[user_id]['file_path']
            output_file = os.path.join(TEMP_DIR, f"compressed_{os.path.basename(input_file)}")
            status_msg = await callback_query.message.edit_text("🔄 **Preparing compression...**")

            try:
                # Build FFmpeg command
                command = [
                    "ffmpeg", "-y",  # Force overwrite output file
                    "-i", input_file,
                    "-c:v", "libx265",  # Use HEVC codec
                    "-preset", settings['preset'],
                    "-crf", str(settings['crf']),
                    "-pix_fmt", settings['pixel_format'],
                    "-tag:v", "hvc1"  # Add hvc1 tag for better compatibility
                ]

                # Audio settings
                if settings['copy_audio']:
                    command.extend(["-c:a", "copy"])
                else:
                    command.extend(["-c:a", "aac", "-b:a", "128k"])

                # Subtitle settings
                if settings['copy_subs']:
                    command.extend(["-c:s", "copy"])
                else:
                    command.extend(["-sn"])  # Remove subtitles

                # Add output file
                command.append(output_file)

                # Start compression
                success = await run_ffmpeg_with_progress(command, status_msg, input_file)

                if success:
                    user_data[user_id]['compressed_file'] = output_file
                    # Generate thumbnail
                    thumb_path = await generate_thumbnail(output_file)
                    if thumb_path:
                        user_data[user_id]['thumb_path'] = thumb_path

                    # Get compression stats
                    original_size = os.path.getsize(input_file)
                    compressed_size = os.path.getsize(output_file)
                    ratio = ((original_size - compressed_size) / original_size) * 100

                    await status_msg.edit_text(
                        f"✅ **Compression Complete!**\n\n"
                        f"📊 **Compression Stats:**\n"
                        f"• Original Size: `{format_size(original_size)}`\n"
                        f"• Compressed Size: `{format_size(compressed_size)}`\n"
                        f"• Saved Space: `{ratio:.1f}%`\n\n"
                        f"Choose upload format:",
                        reply_markup=create_final_menu()
                    )
                else:
                    raise Exception("Compression failed")

            except Exception as e:
                await status_msg.edit_text(f"❌ **Compression Error:** {str(e)}")
                if os.path.exists(output_file):
                    os.remove(output_file)

        # File Upload Handlers
        elif data in ["upload_video", "upload_document"]:
            status_msg = await callback_query.message.edit_text("🔄 **Preparing upload...**")
            
            try:
                input_file = user_data[user_id]['compressed_file']
                thumb_path = user_data[user_id].get('thumb_path')
                
                # Get video information
                probe = await asyncio.create_subprocess_exec(
                    'ffprobe', '-v', 'quiet',
                    '-print_format', 'json',
                    '-show_format',
                    '-show_streams',
                    input_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await probe.communicate()
                metadata = json.loads(stdout.decode())
                
                format_info = metadata.get('format', {})
                video_stream = next((s for s in metadata['streams'] if s['codec_type'] == 'video'), None)
                
                if not video_stream:
                    raise Exception("No video stream found in processed file")

                # Prepare caption
                settings = user_data[user_id]['compression_settings']
                original_size = os.path.getsize(user_data[user_id]['file_path'])
                compressed_size = os.path.getsize(input_file)
                ratio = ((original_size - compressed_size) / original_size) * 100
                
                caption = (
                    f"**📊 Video Information**\n\n"
                    f"• **Preset:** `{settings['preset']}`\n"
                    f"• **CRF:** `{settings['crf']}`\n"
                    f"• **Pixel Format:** `{settings['pixel_format']}`\n"
                    f"• **Resolution:** `{video_stream.get('width')}x{video_stream.get('height')}`\n"
                    f"• **Original Size:** `{format_size(original_size)}`\n"
                    f"• **Compressed Size:** `{format_size(compressed_size)}`\n"
                    f"• **Saved Space:** `{ratio:.1f}%`\n\n"
                    f"🤖 **@{BOT_USERNAME}**"
                )

                # Progress callback for upload
                start_time = time.time()
                async def upload_progress(current, total):
                    try:
                        now = time.time()
                        if now - upload_progress.last_time < 2:
                            return
                        upload_progress.last_time = now
                        
                        elapsed_time = int(now - start_time)
                        speed = current / elapsed_time if elapsed_time > 0 else 0
                        eta = int((total - current) / speed) if speed > 0 else 0
                        
                        bar, percent = create_progress_bar(current, total)
                        
                        await status_msg.edit_text(
                            f"📤 **Uploading Video...**\n\n"
                            f"╭─❰ 𝙿𝚛𝚘𝚐𝚛𝚎𝚜𝚜 ❱\n"
                            f"│\n"
                            f"├ {bar}\n"
                            f"├ **Progress:** `{percent:.1f}%`\n"
                            f"├ **Speed:** `{format_size(speed)}/s`\n"
                            f"├ **Uploaded:** `{format_size(current)}`\n"
                            f"├ **Size:** `{format_size(total)}`\n"
                            f"├ **Time:** `{format_time(elapsed_time)}`\n"
                            f"├ **ETA:** `{format_time(eta)}`\n"
                            f"│\n"
                            f"╰─❰ @{BOT_USERNAME} ❱"
                        )
                    except Exception as e:
                        print(f"Upload progress error: {str(e)}")

                upload_progress.last_time = 0

                # Send file
                if data == "upload_video":
                    await client.send_video(
                        callback_query.message.chat.id,
                        input_file,
                        caption=caption,
                        thumb=thumb_path,
                        duration=int(float(format_info.get('duration', 0))),
                        width=video_stream.get('width', 0),
                        height=video_stream.get('height', 0),
                        progress=upload_progress,
                        supports_streaming=True
                    )
                else:
                    await client.send_document(
                        callback_query.message.chat.id,
                        input_file,
                        caption=caption,
                        thumb=thumb_path,
                        progress=upload_progress,
                        force_document=True
                    )

                # Final cleanup
                await cleanup_files(user_id)
                await status_msg.edit_text(
                    "✅ **Process Completed Successfully!**\n\n"
                    f"📊 Space saved: `{ratio:.1f}%`\n"
                    f"📦 Final size: `{format_size(compressed_size)}`\n\n"
                    "Send another video to start again."
                )

            except Exception as e:
                await status_msg.edit_text(f"❌ **Upload Error:** {str(e)}")
                await cleanup_files(user_id)

        # Cancel Operation
        elif data == "cancel":
            await cleanup_files(user_id)
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

# Part 10: Bot Startup

if __name__ == "__main__":
    print("🚀 Starting Video Processing Bot...")
    try:
        app.run()
    except Exception as e:
        print(f"❌ Error starting bot: {str(e)}")
