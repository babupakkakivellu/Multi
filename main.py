# Part 1: Core Setup and Basic Classes

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import os
import json
import asyncio
import subprocess
import time
from typing import Dict, Set, Tuple
import math

# Bot configuration
app = Client(
    "stream_remover_bot",
    api_id="16501053",
    api_hash="d8c9b01c863dabacc484c2c06cdd0f6e",
    bot_token="6738287955:AAE5lXdu_kbQevdyImUIJ84CTwwNhELjHK4"
)

class UserSession:
    def __init__(self):
        self.file_path = None
        self.file_id = None
        self.streams = None
        self.last_activity = time.time()
        self.status_message = None
        self.settings = {
            'remove_streams': {
                'enabled': False,
                'selected_streams': set()
            },
            'compression': {
                'enabled': False,
                'resolution': None,
                'crf': 23,
                'preset': 'medium'
            },
            'new_filename': None,
            'awaiting_rename': False
        }

# Store user sessions
user_data: Dict[int, UserSession] = {}

async def progress(current: int, total: int, message: Message, start_time: float, action: str):
    """Display progress for file operations"""
    if total == 0:
        return
        
    try:
        elapsed_time = time.time() - start_time
        percentage = (current * 100) / total
        speed = current / elapsed_time if elapsed_time > 0 else 0
        
        # Create progress bar
        bar_length = 20
        filled_length = int(bar_length * current // total)
        bar = "█" * filled_length + "▒" * (bar_length - filled_length)
        
        # Format sizes
        current_size = format_size(current)
        total_size = format_size(total)
        speed_text = format_size(speed)
        
        await message.edit_text(
            f"{get_action_emoji(action)} **{action}**\n\n"
            f"┌ **Size:** {current_size} / {total_size}\n"
            f"├ **Speed:** {speed_text}/s\n"
            f"├ **Progress:** {percentage:.1f}%\n"
            f"└ {bar}"
        )
    except Exception as e:
        print(f"Progress update error: {str(e)}")

def get_action_emoji(action: str) -> str:
    """Get emoji for different actions"""
    return {
        "Downloading": "📥",
        "Uploading": "📤",
        "Processing": "⚙️",
        "Compressing": "🔄"
    }.get(action, "📝")

def format_size(size: float) -> str:
    """Format size in bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def format_time(seconds: float) -> str:
    """Format seconds to human readable time"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:.0f}m {seconds:.0f}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:.0f}h {minutes:.0f}m {seconds:.0f}s"

class FileManager:
    @staticmethod
    async def cleanup_files(file_paths: list):
        """Clean up temporary files"""
        for path in file_paths:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                print(f"Cleanup error: {str(e)}")

    @staticmethod
    def get_safe_filename(filename: str) -> str:
        """Convert filename to safe version"""
        return "".join([c for c in filename if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).rstrip()

    # Part 2: Video Processing and Stream Handling

class VideoProcessor:
    def __init__(self):
        self.supported_formats = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv'}

    async def process_video(self, input_file: str, session: UserSession, message: Message) -> str:
        try:
            output_file = f"processed_{os.path.basename(input_file)}"
            start_time = time.time()
            
            # Get video duration for progress tracking
            total_duration = await self.get_video_duration(input_file)
            
            # Build FFmpeg command
            cmd = ['ffmpeg', '-i', input_file]
            
            # Add stream mapping if streams are selected for removal
            if session.settings['remove_streams']['enabled']:
                for i in range(len(session.streams)):
                    if i not in session.settings['remove_streams']['selected_streams']:
                        cmd.extend(['-map', f'0:{i}'])
            else:
                cmd.extend(['-map', '0'])
            
            # Add compression settings if enabled
            if session.settings['compression']['enabled']:
                settings = session.settings['compression']
                # Video codec settings
                cmd.extend(['-c:v', 'libx264'])
                
                # Resolution
                if settings['resolution'] and settings['resolution'] != 'original':
                    height = int(settings['resolution'].replace('p', ''))
                    cmd.extend(['-vf', f'scale=-2:{height}'])
                
                # Quality and speed
                cmd.extend([
                    '-crf', str(settings['crf']),
                    '-preset', settings['preset'],
                    '-c:a', 'aac',
                    '-b:a', '192k'
                ])
            else:
                cmd.extend(['-c', 'copy'])
            
            # Add progress monitoring and output file
            cmd.extend(['-progress', 'pipe:1', '-y', output_file])
            
            # Start FFmpeg process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Monitor progress
            await self.monitor_progress(process, total_duration, message, start_time)
            
            # Wait for process to complete
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_message = stderr.decode() if stderr else "Unknown error"
                raise Exception(f"FFmpeg processing failed: {error_message}")
            
            if not os.path.exists(output_file):
                raise Exception("Output file was not created")
                
            return output_file
            
        except Exception as e:
            raise Exception(f"Processing failed: {str(e)}")

    async def monitor_progress(self, process, total_duration, message, start_time):
        """Monitor FFmpeg progress and update status message"""
        last_update_time = 0
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                    
                line = line.decode('utf-8')
                if "out_time_ms=" in line:
                    time_ms = int(line.split("out_time_ms=")[1].split()[0])
                    current_time = time_ms / 1000000  # Convert to seconds
                    
                    # Update progress every 2 seconds
                    current_time_stamp = time.time()
                    if current_time_stamp - last_update_time >= 2:
                        progress_text = (
                            f"⚙️ **Processing Video**\n\n"
                            f"┌ **Progress:** {format_time(current_time)} / {format_time(total_duration)}\n"
                            f"├ **Speed:** {format_size(current_time/(current_time_stamp-start_time))}/s\n"
                            f"└ **Elapsed:** {format_time(current_time_stamp-start_time)}"
                        )
                        await message.edit_text(progress_text)
                        last_update_time = current_time_stamp
                        
        except Exception as e:
            print(f"Progress monitoring error: {str(e)}")

    @staticmethod
    async def get_video_info(file_path: str) -> dict:
        """Get video file information using ffprobe"""
        try:
            probe = await asyncio.create_subprocess_exec(
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await probe.communicate()
            return json.loads(stdout)
        except Exception as e:
            raise Exception(f"Failed to get video info: {str(e)}")

    @staticmethod
    async def get_video_duration(file_path: str) -> float:
        """Get video duration in seconds"""
        try:
            probe = await asyncio.create_subprocess_exec(
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await probe.communicate()
            return float(stdout.decode().strip())
        except Exception as e:
            raise Exception(f"Failed to get video duration: {str(e)}")

async def extract_thumbnail(file_path: str) -> dict:
    """Extract thumbnail and get video metadata"""
    try:
        # Get video information
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
        
        # Get video duration and dimensions
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

class StreamAnalyzer:
    @staticmethod
    def get_stream_info(stream: dict) -> str:
        """Format stream information with improved readability"""
        codec_type = stream.get('codec_type', 'unknown').upper()
        codec_name = stream.get('codec_name', 'unknown').upper()
        language = stream.get('tags', {}).get('language', 'und')
        title = stream.get('tags', {}).get('title', '')
        
        info_parts = [f"{codec_type} ({codec_name})"]
        
        if language != 'und':
            info_parts.append(f"[{language.upper()}]")
        
        if codec_type == 'VIDEO':
            width = stream.get('width', '?')
            height = stream.get('height', '?')
            fps = stream.get('r_frame_rate', '').split('/')[0]
            info_parts.append(f"{width}x{height}")
            if fps:
                info_parts.append(f"{fps}fps")
                
        elif codec_type == 'AUDIO':
            channels = stream.get('channels', '?')
            info_parts.append(f"{channels}ch")
            
        if title:
            info_parts.append(f"'{title}'")
            
        return " | ".join(info_parts)

    @staticmethod
    def get_streams_summary(streams: list) -> str:
        """Create a summary of all streams"""
        summary = []
        for i, stream in enumerate(streams):
            summary.append(f"{i}: {StreamAnalyzer.get_stream_info(stream)}")
        return "\n".join(summary)

# Part 3: UI Components and Button Managers

class ButtonManager:
    @staticmethod
    def create_initial_options(session: UserSession = None) -> list:
        """Create initial operation selection buttons"""
        remove_status = "✅" if session and session.settings['remove_streams']['enabled'] else "⬜️"
        compress_status = "✅" if session and session.settings['compression']['enabled'] else "⬜️"
        
        buttons = [
            [InlineKeyboardButton(
                f"🗑️ Remove Streams {remove_status}",
                callback_data="toggle_remove_streams"
            )],
            [InlineKeyboardButton(
                f"🔄 Compress Video {compress_status}",
                callback_data="toggle_compress"
            )],
            [
                InlineKeyboardButton("✅ Continue", callback_data="continue"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        return buttons

    @staticmethod
    def create_stream_buttons(streams: list, selected_streams: Set[int]) -> list:
        """Create stream selection buttons with improved formatting"""
        buttons = []
        
        stream_groups = {
            'video': ('🎥 VIDEO STREAMS', []),
            'audio': ('🔊 AUDIO STREAMS', []),
            'subtitle': ('💭 SUBTITLE STREAMS', []),
            'other': ('📎 OTHER STREAMS', [])
        }
        
        for i, stream in enumerate(streams):
            codec_type = stream.get('codec_type', 'unknown').lower()
            stream_info = StreamAnalyzer.get_stream_info(stream)
            
            group = codec_type if codec_type in stream_groups else 'other'
            prefix = "☑️" if i in selected_streams else "⬜️"
            
            stream_groups[group][1].append({
                'index': i,
                'info': stream_info,
                'prefix': prefix
            })
        
        # Add headers and stream buttons for each group
        for group_name, (header, group_streams) in stream_groups.items():
            if group_streams:
                buttons.append([InlineKeyboardButton(
                    f"═══ {header} ═══",
                    callback_data="header"
                )])
                for stream in group_streams:
                    buttons.append([InlineKeyboardButton(
                        f"{stream['prefix']} {stream['info']}",
                        callback_data=f"stream_{stream['index']}"
                    )])
        
        buttons.append([
            InlineKeyboardButton("✅ Continue", callback_data="continue"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel")
        ])
        
        return buttons

    @staticmethod
    def create_compression_buttons(settings: dict = None) -> list:
        """Create compression settings buttons with visual indicators"""
        if not settings:
            settings = {
                'resolution': None,
                'crf': 23,
                'preset': 'medium'
            }
        
        def get_status(key, value, current_value):
            return "✅" if value == current_value else "⬜️"
        
        buttons = [
            [InlineKeyboardButton("🎯 Resolution Settings", callback_data="comp_resolution_header")],
            [
                InlineKeyboardButton(
                    f"720p {get_status('resolution', '720p', settings['resolution'])}",
                    callback_data="res_720"
                ),
                InlineKeyboardButton(
                    f"1080p {get_status('resolution', '1080p', settings['resolution'])}",
                    callback_data="res_1080"
                ),
                InlineKeyboardButton(
                    f"Original {get_status('resolution', None, settings['resolution'])}",
                    callback_data="res_original"
                )
            ],
            [InlineKeyboardButton("⚙️ Quality Settings", callback_data="comp_quality_header")],
            [
                InlineKeyboardButton(
                    f"High {get_status('crf', 18, settings['crf'])}",
                    callback_data="crf_18"
                ),
                InlineKeyboardButton(
                    f"Medium {get_status('crf', 23, settings['crf'])}",
                    callback_data="crf_23"
                ),
                InlineKeyboardButton(
                    f"Low {get_status('crf', 28, settings['crf'])}",
                    callback_data="crf_28"
                )
            ],
            [InlineKeyboardButton("⚡ Speed Settings", callback_data="comp_speed_header")],
            [
                InlineKeyboardButton(
                    f"Fast {get_status('preset', 'fast', settings['preset'])}",
                    callback_data="preset_fast"
                ),
                InlineKeyboardButton(
                    f"Medium {get_status('preset', 'medium', settings['preset'])}",
                    callback_data="preset_medium"
                ),
                InlineKeyboardButton(
                    f"Slow {get_status('preset', 'slow', settings['preset'])}",
                    callback_data="preset_slow"
                )
            ],
            [
                InlineKeyboardButton("✅ Continue", callback_data="comp_continue"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        return buttons

    @staticmethod
    def create_rename_buttons() -> list:
        """Create rename and upload format selection buttons"""
        buttons = [
            [InlineKeyboardButton("✏️ Rename File", callback_data="rename")],
            [
                InlineKeyboardButton("📹 Send as Video", callback_data="upload_video"),
                InlineKeyboardButton("📄 Send as File", callback_data="upload_document")
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings")]
        ]
        return buttons

class MessageFormatter:
    @staticmethod
    def get_start_message() -> str:
        return (
            "**🎥 Advanced Video Processor**\n\n"
            "Send me any video file to:\n"
            "• 🗑️ Remove unwanted streams\n"
            "• 🔄 Compress with custom settings\n"
            "• ✏️ Rename file (optional)\n"
            "• 📤 Choose upload format\n\n"
            "ℹ️ Supported formats: MP4, MKV, AVI, etc."
        )

    @staticmethod
    def get_help_message() -> str:
        return (
            "**📚 Help**\n\n"
            "1. Send any video file\n"
            "2. Choose operations:\n"
            "   • Remove unwanted streams\n"
            "   • Compress video\n"
            "3. Configure settings\n"
            "4. Rename file (optional)\n"
            "5. Choose upload format\n\n"
            "**Commands:**\n"
            "/start - Start the bot\n"
            "/cancel - Cancel current operation"
        )

    @staticmethod
    def get_about_message() -> str:
        return (
            "**ℹ️ About**\n\n"
            "Advanced Video Processor Bot\n"
            "Version: 2.0\n\n"
            "Features:\n"
            "• Stream removal\n"
            "• Video compression\n"
            "• Custom quality settings\n"
            "• Progress tracking\n"
            "• Multiple operations\n\n"
            "Made with ❤️ by Your Name"
        )

    @staticmethod
    def get_settings_summary(session: UserSession) -> str:
        """Create a formatted summary of current settings"""
        summary = ["**Current Settings:**\n"]
        
        if session.settings['remove_streams']['enabled']:
            count = len(session.settings['remove_streams']['selected_streams'])
            summary.append(f"🗑️ Stream Removal: {count} stream(s) selected")
        
        if session.settings['compression']['enabled']:
            comp = session.settings['compression']
            summary.extend([
                "🔄 Compression:",
                f"   • Resolution: {comp['resolution'] or 'Original'}",
                f"   • Quality: {MessageFormatter.get_quality_text(comp['crf'])}",
                f"   • Speed: {comp['preset'].title()}"
            ])
            
        return "\n".join(summary)

    @staticmethod
    def get_quality_text(crf: int) -> str:
        quality_map = {
            18: "High ⭐⭐⭐",
            23: "Medium ⭐⭐",
            28: "Low ⭐"
        }
        return quality_map.get(crf, "Custom")

    @staticmethod
    def get_processing_message() -> str:
        return "⚙️ **Processing your video...**"

    @staticmethod
    def get_rename_instructions() -> str:
        return (
            "**✏️ Please send the new filename:**\n\n"
            "• Send the new name without extension\n"
            "• Click /cancel to cancel renaming"
        )

# Part 4: Message Handlers and Basic Bot Logic

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    """Handle /start command"""
    buttons = [
        [
            InlineKeyboardButton("📚 Help", callback_data="show_help"),
            InlineKeyboardButton("ℹ️ About", callback_data="show_about")
        ]
    ]
    
    await message.reply_text(
        MessageFormatter.get_start_message(),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_message(filters.command("cancel"))
async def cancel_command(client, message: Message):
    """Handle /cancel command"""
    user_id = message.from_user.id
    if user_id in user_data:
        session = user_data[user_id]
        if session.file_path and os.path.exists(session.file_path):
            os.remove(session.file_path)
        del user_data[user_id]
        await message.reply_text("❌ Operation cancelled.")
    else:
        await message.reply_text("No active operation to cancel.")

@app.on_message(filters.video | filters.document)
async def handle_video(client, message: Message):
    """Handle incoming video/document messages"""
    try:
        user_id = message.from_user.id
        
        # Check if user has ongoing process
        if user_id in user_data:
            await message.reply_text(
                "⚠️ You have an ongoing process. Please wait or use /cancel."
            )
            return
        
        # Validate file
        if message.video:
            file_info = message.video
        elif message.document:
            if not message.document.mime_type or not message.document.mime_type.startswith('video/'):
                await message.reply_text("❌ Please send a valid video file.")
                return
            file_info = message.document
        else:
            await message.reply_text("❌ Please send a valid video file.")
            return
            
        # Check file size
        if file_info.file_size > 2 * 1024 * 1024 * 1024:  # 2GB limit
            await message.reply_text("❌ File size too large (max 2GB)")
            return
            
        # Initialize status message
        status_msg = await message.reply_text(
            "⚡ **Initializing...**\n\n"
            "Please wait while I analyze your file."
        )
        
        # Create new session
        session = UserSession()
        session.file_id = file_info.file_id
        session.status_message = status_msg
        user_data[user_id] = session
        
        # Show initial options
        buttons = ButtonManager.create_initial_options(session)
        await status_msg.edit_text(
            "**🎯 Select Operations**\n\n"
            "Choose what you want to do with this file:\n\n"
            "• Remove Streams - Select streams to remove\n"
            "• Compress Video - Compress with custom settings\n\n"
            "_You can select multiple operations_",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except Exception as e:
        error_msg = f"❌ **Error:** {str(e)}"
        if 'status_msg' in locals():
            await status_msg.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)
        
        if user_id in user_data:
            del user_data[user_id]

@app.on_message(filters.text & filters.private)
async def handle_text(client, message: Message):
    """Handle text messages (for rename operation)"""
    user_id = message.from_user.id
    
    if user_id not in user_data:
        return
    
    session = user_data[user_id]
    
    if not session.settings.get('awaiting_rename'):
        return
        
    try:
        if message.text == "/cancel":
            session.settings['awaiting_rename'] = False
            session.settings['new_filename'] = None
            buttons = ButtonManager.create_rename_buttons()
            await session.status_message.edit_text(
                "**📤 Choose upload options:**",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            # Sanitize filename
            new_filename = FileManager.get_safe_filename(message.text)
            if not new_filename:
                await message.reply_text(
                    "❌ Invalid filename. Please use only letters, numbers, spaces, or - _"
                )
                return
                
            session.settings['new_filename'] = new_filename
            session.settings['awaiting_rename'] = False
            
            buttons = ButtonManager.create_rename_buttons()
            await session.status_message.edit_text(
                f"**✅ Filename set to:** `{new_filename}`\n\n"
                "Now choose how you want to upload the file:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        
        # Delete user's message to keep chat clean
        await message.delete()
        
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")

async def process_and_upload_file(client, callback_query: CallbackQuery, upload_mode: str):
    """Handle file processing and uploading"""
    user_id = callback_query.from_user.id
    session = user_data[user_id]
    message = session.status_message
    
    try:
        # Download original file if not downloaded yet
        if not session.file_path:
            start_time = time.time()
            await message.edit_text("📥 **Downloading file...**")
            
            async def progress_wrapper(current, total):
                await progress(current, total, message, start_time, "Downloading")
            
            session.file_path = await client.download_media(
                session.file_id,
                progress=progress_wrapper
            )
        
        if not session.file_path:
            raise Exception("Download failed")
        
        # Process video
        processor = VideoProcessor()
        output_file = await processor.process_video(session.file_path, session, message)
        
        if not output_file or not os.path.exists(output_file):
            raise Exception("Processing failed")
        
        # Extract thumbnail and metadata
        thumb_data = await extract_thumbnail(output_file)
        
        # Prepare filename
        if session.settings['new_filename']:
            filename = f"{session.settings['new_filename']}{os.path.splitext(output_file)[1]}"
            final_path = os.path.join(os.path.dirname(output_file), filename)
            os.rename(output_file, final_path)
            output_file = final_path
        else:
            filename = os.path.basename(output_file)
        
        # Upload file
        start_time = time.time()
        caption = f"**{filename}**"
        
        async def progress_wrapper(current, total):
            await progress(current, total, message, start_time, "Uploading")
        
        if upload_mode == "video":
            await client.send_video(
                callback_query.message.chat.id,
                output_file,
                caption=caption,
                duration=thumb_data['duration'] if thumb_data else None,
                width=thumb_data['width'] if thumb_data else None,
                height=thumb_data['height'] if thumb_data else None,
                thumb=thumb_data['thumb_path'] if thumb_data else None,
                progress=progress_wrapper
            )
        else:
            await client.send_document(
                callback_query.message.chat.id,
                output_file,
                caption=caption,
                thumb=thumb_data['thumb_path'] if thumb_data else None,
                progress=progress_wrapper
            )
        
        await message.edit_text("✅ **Process completed successfully!**")
        
    except Exception as e:
        await message.edit_text(f"❌ **Error:** {str(e)}")
    finally:
        # Cleanup
        try:
            if session.file_path and os.path.exists(session.file_path):
                os.remove(session.file_path)
            if 'output_file' in locals() and os.path.exists(output_file):
                os.remove(output_file)
            if 'thumb_data' in locals() and thumb_data and thumb_data['thumb_path']:
                os.remove(thumb_data['thumb_path'])
        except Exception as e:
            print(f"Cleanup error: {str(e)}")
        
        if user_id in user_data:
            del user_data[user_id]

# Part 5: Callback Handlers and Advanced Features

@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    """Handle all callback queries"""
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    # Handle help and about callbacks without session
    if data in ["show_help", "show_about", "back_to_start"]:
        await handle_info_callbacks(callback_query)
        return
    
    # Check session validity
    if user_id not in user_data and data not in ['header']:
        await callback_query.answer("Session expired. Please send the video again.", show_alert=True)
        return
    
    if data == "header":
        await callback_query.answer("Section header")
        return

    session = user_data[user_id]
    session.last_activity = time.time()
    
    try:
        if data == "toggle_remove_streams":
            await handle_toggle_streams(callback_query, session)
            
        elif data == "toggle_compress":
            await handle_toggle_compress(callback_query, session)
            
        elif data == "continue":
            await handle_continue(client, callback_query, session)
            
        elif data.startswith("stream_"):
            await handle_stream_selection(callback_query, session)
            
        elif data.startswith(("res_", "crf_", "preset_")):
            await handle_compression_settings(callback_query, session)
            
        elif data == "comp_continue":
            await handle_compression_continue(callback_query, session)
            
        elif data == "rename":
            await handle_rename(callback_query, session)
            
        elif data.startswith("upload_"):
            await handle_upload(client, callback_query, session)
            
        elif data == "back_to_settings":
            await handle_back_to_settings(callback_query, session)
            
        elif data == "cancel":
            await handle_cancel(callback_query, session)
            
    except Exception as e:
        await callback_query.message.edit_text(f"❌ **Error:** {str(e)}")
        if user_id in user_data:
            del user_data[user_id]

async def handle_info_callbacks(callback_query: CallbackQuery):
    """Handle help and about button callbacks"""
    if callback_query.data == "show_help":
        text = MessageFormatter.get_help_message()
    elif callback_query.data == "show_about":
        text = MessageFormatter.get_about_message()
    else:  # back_to_start
        text = MessageFormatter.get_start_message()
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📚 Help", callback_data="show_help"),
                InlineKeyboardButton("ℹ️ About", callback_data="show_about")
            ]])
        )
        return
    
    await callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Back", callback_data="back_to_start")
        ]])
    )

async def handle_toggle_streams(callback_query: CallbackQuery, session: UserSession):
    """Handle stream removal toggle"""
    session.settings['remove_streams']['enabled'] = not session.settings['remove_streams']['enabled']
    buttons = ButtonManager.create_initial_options(session)
    await callback_query.message.edit_text(
        "**🎯 Select Operations**\n\n"
        f"{MessageFormatter.get_settings_summary(session)}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_toggle_compress(callback_query: CallbackQuery, session: UserSession):
    """Handle compression toggle"""
    session.settings['compression']['enabled'] = not session.settings['compression']['enabled']
    buttons = ButtonManager.create_initial_options(session)
    await callback_query.message.edit_text(
        "**🎯 Select Operations**\n\n"
        f"{MessageFormatter.get_settings_summary(session)}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_continue(client, callback_query: CallbackQuery, session: UserSession):
    """Handle continue button press"""
    try:
        if not any(session.settings[op]['enabled'] for op in ['remove_streams', 'compression']):
            await callback_query.answer("Please select at least one operation!", show_alert=True)
            return
        
        # Start downloading
        start_time = time.time()
        await callback_query.message.edit_text("📥 **Downloading file...**")
        
        async def progress_wrapper(current, total):
            await progress(current, total, callback_query.message, start_time, "Downloading")
        
        session.file_path = await client.download_media(
            session.file_id,
            progress=progress_wrapper
        )
        
        if not session.file_path:
            raise Exception("Download failed")
        
        # Get stream information if needed
        if session.settings['remove_streams']['enabled']:
            video_info = await VideoProcessor.get_video_info(session.file_path)
            session.streams = video_info['streams']
            
            buttons = ButtonManager.create_stream_buttons(
                session.streams,
                session.settings['remove_streams']['selected_streams']
            )
            await callback_query.message.edit_text(
                "**🎯 Select streams to remove:**\n\n"
                "⬜️ = Keep stream\n"
                "☑️ = Remove stream",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        elif session.settings['compression']['enabled']:
            buttons = ButtonManager.create_compression_buttons(session.settings['compression'])
            await callback_query.message.edit_text(
                "**🔄 Compression Settings**\n\n"
                "Configure your compression settings:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
    except Exception as e:
        await callback_query.message.edit_text(f"❌ **Error:** {str(e)}")
        if callback_query.from_user.id in user_data:
            del user_data[callback_query.from_user.id]

async def handle_stream_selection(callback_query: CallbackQuery, session: UserSession):
    """Handle stream selection"""
    stream_index = int(callback_query.data.split("_")[1])
    if stream_index in session.settings['remove_streams']['selected_streams']:
        session.settings['remove_streams']['selected_streams'].remove(stream_index)
    else:
        session.settings['remove_streams']['selected_streams'].add(stream_index)
    
    buttons = ButtonManager.create_stream_buttons(
        session.streams,
        session.settings['remove_streams']['selected_streams']
    )
    await callback_query.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_compression_settings(callback_query: CallbackQuery, session: UserSession):
    """Handle compression setting changes"""
    data = callback_query.data
    settings = session.settings['compression']
    
    if data.startswith("res_"):
        settings['resolution'] = None if data == "res_original" else data.replace("res_", "") + "p"
    elif data.startswith("crf_"):
        settings['crf'] = int(data.replace("crf_", ""))
    elif data.startswith("preset_"):
        settings['preset'] = data.replace("preset_", "")
    
    buttons = ButtonManager.create_compression_buttons(settings)
    await callback_query.message.edit_text(
        "**🔄 Compression Settings**\n\n"
        f"{MessageFormatter.get_settings_summary(session)}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_compression_continue(callback_query: CallbackQuery, session: UserSession):
    """Handle compression settings completion"""
    buttons = ButtonManager.create_rename_buttons()
    await callback_query.message.edit_text(
        "**📤 Choose upload options:**\n\n"
        "• Rename file (optional)\n"
        "• Select upload format",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_rename(callback_query: CallbackQuery, session: UserSession):
    """Handle rename button press"""
    session.settings['awaiting_rename'] = True
    await callback_query.message.edit_text(
        MessageFormatter.get_rename_instructions(),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings")
        ]])
    )

async def handle_upload(client, callback_query: CallbackQuery, session: UserSession):
    """Handle upload button press"""
    upload_mode = callback_query.data.replace("upload_", "")
    await process_and_upload_file(client, callback_query, upload_mode)

async def handle_back_to_settings(callback_query: CallbackQuery, session: UserSession):
    """Handle back button press"""
    if session.settings['remove_streams']['enabled']:
        buttons = ButtonManager.create_stream_buttons(
            session.streams,
            session.settings['remove_streams']['selected_streams']
        )
        await callback_query.message.edit_text(
            "**🎯 Select streams to remove:**\n\n"
            "⬜️ = Keep stream\n"
            "☑️ = Remove stream",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif session.settings['compression']['enabled']:
        buttons = ButtonManager.create_compression_buttons(session.settings['compression'])
        await callback_query.message.edit_text(
            "**🔄 Compression Settings**\n\n"
            f"{MessageFormatter.get_settings_summary(session)}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

async def handle_cancel(callback_query: CallbackQuery, session: UserSession):
    """Handle cancel button press"""
    if session.file_path and os.path.exists(session.file_path):
        os.remove(session.file_path)
    if callback_query.from_user.id in user_data:
        del user_data[callback_query.from_user.id]
    await callback_query.message.edit_text("❌ **Operation cancelled.**")

# Session cleanup task
async def cleanup_inactive_sessions():
    """Cleanup inactive sessions periodically"""
    while True:
        try:
            current_time = time.time()
            for user_id, session in list(user_data.items()):
                if current_time - session.last_activity > 1800:  # 30 minutes timeout
                    if session.file_path and os.path.exists(session.file_path):
                        os.remove(session.file_path)
                    del user_data[user_id]
            await asyncio.sleep(300)  # Check every 5 minutes
        except Exception as e:
            print(f"Session cleanup error: {str(e)}")

# Start the cleanup task
app.loop.create_task(cleanup_inactive_sessions())

print("🚀 Bot is starting...")
app.run()
