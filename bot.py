"""
Telegram Video Compression Bot
-----------------------------
A comprehensive bot for video compression using Pyrogram and FFmpeg.
Version: 1.0
"""

import os
import time
import asyncio
import subprocess
import logging
import math
from datetime import datetime, timedelta
import humanize
from typing import Dict, Optional, Union, List, Tuple
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery,
    InputMediaPhoto
)
from pyrogram.errors import (
    FloodWait, 
    MessageNotModified, 
    UserNotParticipant,
    ChatAdminRequired,
    PeerIdInvalid
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Bot Configuration
API_ID = "your_api_id"
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token"
DOWNLOAD_DIR = "downloads/"
OWNER_ID = 123456789  # Replace with your Telegram ID
UPDATES_CHANNEL = "your_channel_username"  # Optional: Channel username for force subscribe
SUPPORT_GROUP = "your_support_group"  # Optional: Support group username

# Initialize Bot
app = Client(
    "video_compress_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=6  # Number of concurrent handler workers
)

# Compression Settings
COMPRESSION_SETTINGS = {
    "resolutions": {
        "144p": "256x144",
        "240p": "426x240",
        "360p": "640x360",
        "480p": "854x480",
        "720p": "1280x720",
        "1080p": "1920x1080",
        "4K": "3840x2160"
    },
    "presets": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
    "crfs": list(range(15, 31)),
    "pixel_formats": ["yuv420p", "yuv444p"],
    "codecs": ["libx264", "libx265"]
}

# Default Settings
DEFAULT_SETTINGS = {
    "resolution": "1280x720",
    "preset": "medium",
    "crf": "23",
    "codec": "libx264",
    "pixel_format": "yuv420p"
}

# Settings Information
SETTINGS_INFO = {
    "resolution": (
        "📐 Resolution Settings\n\n"
        "Higher resolution = Better quality, larger file size\n"
        "Lower resolution = Lower quality, smaller file size\n\n"
        "Recommended:\n"
        "• Mobile: 480p\n"
        "• Desktop: 720p\n"
        "• HD Content: 1080p"
    ),
    "preset": (
        "⚡ Preset Settings\n\n"
        "Faster preset = Faster compression, larger file size\n"
        "Slower preset = Slower compression, smaller file size\n\n"
        "Recommended:\n"
        "• Quick compression: ultrafast\n"
        "• Balanced: medium\n"
        "• Best compression: veryslow"
    ),
    "crf": (
        "🎯 CRF (Quality) Settings\n\n"
        "Lower CRF = Better quality, larger file size\n"
        "Higher CRF = Lower quality, smaller file size\n\n"
        "Recommended:\n"
        "• High quality: 18-23\n"
        "• Balanced: 23-28\n"
        "• Small size: 28-30"
    ),
    "codec": (
        "🎬 Codec Settings\n\n"
        "libx264: Widely compatible, faster encoding\n"
        "libx265: Better compression, slower encoding\n\n"
        "Recommended:\n"
        "• General use: libx264\n"
        "• Best compression: libx265"
    ),
    "pixel_format": (
        "📊 Pixel Format Settings\n\n"
        "yuv420p: Most compatible, smaller file size\n"
        "yuv444p: Better quality, larger file size\n\n"
        "Recommended:\n"
        "• General use: yuv420p\n"
        "• High quality: yuv444p"
    )
}

# Bot Messages
BOT_MESSAGES = {
    "start": (
        "👋 **Welcome to Video Compression Bot!**\n\n"
        "I can help you compress videos while maintaining quality.\n\n"
        "**Features:**\n"
        "• Multiple resolution options (144p to 4K)\n"
        "• Quality control (CRF 15-30)\n"
        "• Various compression presets\n"
        "• Advanced codec options\n\n"
        "**Commands:**\n"
        "/start - Show this message\n"
        "/help - Show detailed help\n"
        "/settings - Show current settings\n"
        "/reset - Reset to default settings\n"
        "/status - Show bot status\n"
        "/cancel - Cancel ongoing process"
    ),
    "help": (
        "📖 **Video Compression Bot Help**\n\n"
        "**How to use:**\n"
        "1. Send a video file\n"
        "2. Choose compression settings:\n"
        "   • Resolution (video quality)\n"
        "   • Preset (compression speed)\n"
        "   • CRF (quality control)\n"
        "   • Codec (compression method)\n"
        "3. Select upload format\n"
        "4. Wait for processing\n\n"
        "**Settings Explained:**\n"
        "• Resolution: Higher = better quality\n"
        "• Preset: Slower = better compression\n"
        "• CRF: Lower = better quality\n"
        "• Codec: x265 = better compression\n\n"
        "**Limitations:**\n"
        "• Max file size: 2GB\n"
        "• Max duration: 3 hours\n\n"
        f"For support, join {SUPPORT_GROUP}"
    )
}

# User session storage
user_settings = {}
active_processes = {}

#================================#
# PART 2: PROGRESS TRACKING      #
#================================#

class ProgressTracker:
    def __init__(self, message: Message):
        self.message = message
        self.start_time = time.time()
        self.last_update_time = 0
        self.last_current = 0
        self.total_steps = 4  # Download, Thumbnail, Compress, Upload
        self.current_step = 0
        
    async def update_progress(self, current: int, total: int, action: str, extra_info: str = ""):
        """Update progress with detailed statistics"""
        try:
            now = time.time()
            if now - self.last_update_time < 2:  # Update every 2 seconds
                return
                
            time_elapsed = now - self.start_time
            speed = current / time_elapsed if time_elapsed > 0 else 0
            progress = (current * 100) / total
            
            # Calculate ETA
            if speed > 0:
                eta = (total - current) / speed
                eta_text = humanize.naturaltime(datetime.now() + timedelta(seconds=eta))
            else:
                eta_text = "Unknown"

            # Overall progress
            overall_progress = (self.current_step + progress/100) / self.total_steps * 100

            # Progress bars
            current_bar = self._create_progress_bar(progress)
            overall_bar = self._create_progress_bar(overall_progress)
            
            # Format sizes
            current_size = humanize.naturalsize(current)
            total_size = humanize.naturalsize(total)
            speed_text = humanize.naturalsize(speed) + "/s"

            progress_text = (
                f"**{action}**\n"
                f"```\n"
                f"Current: {current_bar} {progress:.1f}%\n"
                f"Overall: {overall_bar} {overall_progress:.1f}%\n"
                f"Size: {current_size} / {total_size}\n"
                f"Speed: {speed_text}\n"
                f"ETA: {eta_text}\n"
                f"{extra_info}```"
            )

            await self.message.edit_text(progress_text)
            self.last_update_time = now
            self.last_current = current

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except MessageNotModified:
            pass
        except Exception as e:
            logger.error(f"Progress update error: {str(e)}")

    def _create_progress_bar(self, percentage: float, length: int = 20) -> str:
        """Create a progress bar with customizable length"""
        filled_length = int(length * percentage / 100)
        bar = '█' * filled_length + '░' * (length - filled_length)
        return f"[{bar}]"

    async def next_step(self):
        """Move to next step in the process"""
        self.current_step += 1
        self.start_time = time.time()
        self.last_update_time = 0
        self.last_current = 0

class FFmpegProgress:
    def __init__(self, tracker: ProgressTracker):
        self.tracker = tracker
        self.duration = 0
        self.current_time = 0
        self.last_update_time = 0
        self.frame_count = 0
        self.fps = 0
        self.bitrate = "N/A"
        self.speed = "N/A"
        
    async def parse_progress(self, line: str):
        """Parse FFmpeg progress output"""
        try:
            if "Duration" in line:
                self.duration = self._parse_time(line.split("Duration: ")[1].split(",")[0])
            
            elif "frame=" in line:
                # Parse all available information
                parts = line.split()
                for part in parts:
                    if "frame=" in part:
                        self.frame_count = int(part.split('=')[1])
                    elif "fps=" in part:
                        self.fps = float(part.split('=')[1])
                    elif "bitrate=" in part:
                        self.bitrate = part.split('=')[1]
                    elif "speed=" in part:
                        self.speed = part.split('=')[1]
                    elif "time=" in part:
                        self.current_time = self._parse_time(part.split('=')[1])

                if time.time() - self.last_update_time >= 2:
                    extra_info = (
                        f"Frames: {self.frame_count}\n"
                        f"FPS: {self.fps:.1f}\n"
                        f"Bitrate: {self.bitrate}\n"
                        f"Speed: {self.speed}"
                    )
                    
                    await self.tracker.update_progress(
                        self.current_time,
                        self.duration,
                        "🔄 Compressing",
                        extra_info
                    )
                    self.last_update_time = time.time()

        except Exception as e:
            logger.error(f"FFmpeg progress parsing error: {str(e)}")
    
    def _parse_time(self, time_str: str) -> float:
        """Convert FFmpeg time string to seconds"""
        try:
            h, m, s = time_str.split(':')
            return float(h) * 3600 + float(m) * 60 + float(s)
        except:
            return 0

class VideoMetadata:
    """Class to handle video metadata extraction and validation"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.metadata = None
        self.video_stream = None
        self.audio_stream = None

    async def extract(self) -> Dict:
        """Extract comprehensive video metadata"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                self.file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.metadata = eval(result.stdout)
            
            # Find video and audio streams
            for stream in self.metadata['streams']:
                if stream['codec_type'] == 'video' and not self.video_stream:
                    self.video_stream = stream
                elif stream['codec_type'] == 'audio' and not self.audio_stream:
                    self.audio_stream = stream

            return {
                'width': int(self.video_stream['width']),
                'height': int(self.video_stream['height']),
                'duration': float(self.metadata['format']['duration']),
                'size': int(self.metadata['format']['size']),
                'bitrate': int(self.metadata['format']['bit_rate']),
                'video_codec': self.video_stream['codec_name'],
                'audio_codec': self.audio_stream['codec_name'] if self.audio_stream else None,
                'fps': eval(self.video_stream['avg_frame_rate']),
                'format': self.metadata['format']['format_name']
            }
        except Exception as e:
            logger.error(f"Metadata extraction error: {str(e)}")
            raise

    async def validate(self) -> Tuple[bool, Optional[str]]:
        """Validate video for processing"""
        try:
            metadata = await self.extract()
            
            # Check duration
            if metadata['duration'] > 3 * 60 * 60:  # 3 hours
                return False, "Video duration exceeds 3 hours limit"
            
            # Check resolution
            if metadata['width'] * metadata['height'] > 3840 * 2160:  # 4K
                return False, "Video resolution exceeds 4K limit"
            
            # Check file size
            if metadata['size'] > 2 * 1024 * 1024 * 1024:  # 2GB
                return False, "File size exceeds 2GB limit"
            
            # Check format compatibility
            supported_formats = ['mp4', 'mkv', 'avi', 'mov', 'webm']
            if not any(fmt in metadata['format'].lower() for fmt in supported_formats):
                return False, "Unsupported video format"
            
            return True, None
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def estimate_output_size(self, settings: Dict) -> int:
        """Estimate output file size based on compression settings"""
        try:
            original_size = int(self.metadata['format']['size'])
            
            # Base compression ratios for different codecs
            codec_ratio = {
                'libx264': 0.7,
                'libx265': 0.5
            }.get(settings['codec'], 0.7)
            
            # Preset efficiency factors
            preset_factor = {
                'ultrafast': 1.2,
                'superfast': 1.1,
                'veryfast': 1.0,
                'faster': 0.9,
                'fast': 0.8,
                'medium': 0.7,
                'slow': 0.6,
                'slower': 0.5,
                'veryslow': 0.4
            }.get(settings['preset'], 0.7)
            
            # CRF impact
            crf = int(settings['crf'])
            crf_factor = 1 - (crf - 15) / 30
            
            # Resolution impact
            current_res = self.video_stream['width'] * self.video_stream['height']
            target_res = tuple(map(int, settings['resolution'].split('x')))
            target_res_pixels = target_res[0] * target_res[1]
            resolution_factor = target_res_pixels / current_res
            
            # Calculate final size
            estimated_size = original_size * codec_ratio * preset_factor * crf_factor * resolution_factor
            
            return max(int(estimated_size), 1024 * 1024)  # Minimum 1MB
            
        except Exception as e:
            logger.error(f"Size estimation error: {str(e)}")
            return original_size * 0.7  # Default to 70% of original size

#================================#
# PART 3: VIDEO PROCESSOR        #
#================================#

class VideoProcessor:
    def __init__(self, client: Client, message: Message, settings: dict):
        self.client = client
        self.message = message
        self.settings = settings
        self.chat_id = message.chat.id
        self.progress_message = None
        self.tracker = None
        self.input_file = None
        self.output_file = None
        self.thumb_path = None
        self.metadata = None
        self.start_time = time.time()
        self.process_id = f"{self.chat_id}_{int(self.start_time)}"

    async def start_processing(self, upload_format: str):
        """Main processing pipeline"""
        try:
            # Register active process
            active_processes[self.chat_id] = self
            
            self.progress_message = await self.message.reply_text(
                "🚀 Initializing compression process...\n"
                "This might take a while depending on the video size and settings."
            )
            self.tracker = ProgressTracker(self.progress_message)

            # Initialize file paths
            self.input_file = os.path.join(DOWNLOAD_DIR, f"input_{self.process_id}.mp4")
            self.output_file = os.path.join(DOWNLOAD_DIR, f"output_{self.process_id}.mp4")
            self.thumb_path = os.path.join(DOWNLOAD_DIR, f"thumb_{self.process_id}.jpg")

            # Process steps
            await self.download_video()
            await self.validate_video()
            await self.extract_thumbnail()
            await self.compress_video()
            await self.upload_video(upload_format)
            await self.cleanup()

        except Exception as e:
            logger.error(f"Processing error: {str(e)}")
            await self.handle_error(str(e))
        finally:
            if self.chat_id in active_processes:
                del active_processes[self.chat_id]

    async def download_video(self):
        """Download video with progress tracking"""
        try:
            await self.progress_message.edit_text("📥 Starting download...")
            await self.message.download(
                file_name=self.input_file,
                progress=lambda current, total: self.tracker.update_progress(
                    current, total,
                    "📥 Downloading",
                    "Preparing for compression..."
                )
            )
            await self.tracker.next_step()
        except Exception as e:
            raise Exception(f"Download failed: {str(e)}")

    async def validate_video(self):
        """Validate video metadata"""
        try:
            await self.progress_message.edit_text("🔍 Validating video...")
            self.metadata = VideoMetadata(self.input_file)
            is_valid, error_message = await self.metadata.validate()
            
            if not is_valid:
                raise Exception(error_message)

            # Estimate output size
            estimated_size = self.metadata.estimate_output_size(self.settings)
            await self.progress_message.edit_text(
                f"✅ Video validation complete\n"
                f"Estimated output size: {humanize.naturalsize(estimated_size)}"
            )
        except Exception as e:
            raise Exception(f"Validation failed: {str(e)}")

    async def extract_thumbnail(self):
        """Extract thumbnail with error handling"""
        try:
            await self.progress_message.edit_text("🖼️ Extracting thumbnail...")
            metadata = await self.metadata.extract()
            middle_time = metadata['duration'] / 2
            
            cmd = [
                'ffmpeg', '-ss', str(middle_time),
                '-i', self.input_file,
                '-vframes', '1',
                '-vf', 'scale=320:-1',
                '-y', self.thumb_path
            ]
            process = subprocess.run(cmd, capture_output=True, text=True)
            
            if process.returncode != 0:
                raise Exception(f"FFmpeg error: {process.stderr}")

            await self.tracker.next_step()
        except Exception as e:
            raise Exception(f"Thumbnail extraction failed: {str(e)}")

    async def compress_video(self):
        """Compress video with advanced settings"""
        try:
            ffmpeg_progress = FFmpegProgress(self.tracker)
            
            # Build comprehensive FFmpeg command
            cmd = [
                'ffmpeg', '-y',
                '-i', self.input_file,
                '-c:v', self.settings['codec'],
                '-preset', self.settings['preset'],
                '-crf', str(self.settings['crf']),
                '-vf', f"scale={self.settings['resolution']}:force_original_aspect_ratio=decrease,pad={self.settings['resolution']}:-1:-1:color=black",
                '-pix_fmt', self.settings['pixel_format'],
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',
                '-metadata', f'encoded_by=TGVideoCompressBot',
                '-progress', 'pipe:1',
                self.output_file
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    await ffmpeg_progress.parse_progress(output)

            if process.returncode != 0:
                stderr = process.stderr.read()
                raise Exception(f"FFmpeg error: {stderr}")

            await self.tracker.next_step()
        except Exception as e:
            raise Exception(f"Compression failed: {str(e)}")

    async def upload_video(self, upload_format: str):
        """Upload processed video with proper metadata"""
        try:
            metadata = await self.metadata.extract()
            caption = self.generate_caption(metadata)
            
            if upload_format == "video":
                await self.client.send_video(
                    self.chat_id,
                    self.output_file,
                    thumb=self.thumb_path,
                    duration=int(metadata['duration']),
                    width=metadata['width'],
                    height=metadata['height'],
                    caption=caption,
                    supports_streaming=True,
                    progress=lambda current, total: self.tracker.update_progress(
                        current, total,
                        "📤 Uploading",
                        "Almost done..."
                    )
                )
            else:
                await self.client.send_document(
                    self.chat_id,
                    self.output_file,
                    thumb=self.thumb_path,
                    caption=caption,
                    progress=lambda current, total: self.tracker.update_progress(
                        current, total,
                        "📤 Uploading",
                        "Almost done..."
                    )
                )
            
            await self.progress_message.edit_text(
                "✅ Video processing completed!\n"
                "Check the compressed video above."
            )
            
        except Exception as e:
            raise Exception(f"Upload failed: {str(e)}")

    def generate_caption(self, metadata: Dict) -> str:
        """Generate detailed caption with compression statistics"""
        try:
            original_size = os.path.getsize(self.input_file)
            compressed_size = os.path.getsize(self.output_file)
            compression_ratio = (1 - compressed_size / original_size) * 100
            process_time = time.time() - self.start_time

            return (
                "🎥 **Compressed Video**\n\n"
                f"📊 **Statistics:**\n"
                f"• Resolution: {metadata['width']}x{metadata['height']}\n"
                f"• Duration: {int(metadata['duration'])} seconds\n"
                f"• Original Size: {humanize.naturalsize(original_size)}\n"
                f"• Compressed Size: {humanize.naturalsize(compressed_size)}\n"
                f"• Space Saved: {compression_ratio:.1f}%\n"
                f"• Process Time: {humanize.naturaltime(process_time)}\n\n"
                f"⚙️ **Settings Used:**\n"
                f"• Preset: {self.settings['preset']}\n"
                f"• CRF: {self.settings['crf']}\n"
                f"• Codec: {self.settings['codec']}\n"
                f"• Pixel Format: {self.settings['pixel_format']}\n\n"
                f"🤖 Compressed by @{(await self.client.get_me()).username}"
            )
        except Exception as e:
            logger.error(f"Caption generation error: {str(e)}")
            return "🎥 Compressed Video"

    async def cleanup(self):
        """Clean up temporary files"""
        try:
            for file_path in [self.input_file, self.output_file, self.thumb_path]:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")

    async def handle_error(self, error_message: str):
        """Handle processing errors with user feedback"""
        error_text = (
            "❌ **Error occurred during processing**\n\n"
            f"Error: {error_message}\n\n"
            f"Please try again or contact support: {SUPPORT_GROUP}"
        )
        try:
            await self.progress_message.edit_text(error_text)
        except Exception as e:
            logger.error(f"Error handling failed: {str(e)}")
        finally:
            await self.cleanup()

#================================#
# PART 4: BOT HANDLERS           #
#================================#

async def check_user_status(message: Message) -> bool:
    """Check user status in force subscribe channel"""
    if not UPDATES_CHANNEL:
        return True
        
    try:
        user = await app.get_chat_member(UPDATES_CHANNEL, message.from_user.id)
        if user.status in [enums.ChatMemberStatus.BANNED]:
            await message.reply_text(
                "❌ You are banned from using this bot.\n"
                "Contact support for more information."
            )
            return False
            
        if user.status not in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
            await message.reply_text(
                f"🔐 To use this bot, you must join our channel.\n\n"
                f"Please join @{UPDATES_CHANNEL} and try again!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{UPDATES_CHANNEL}")]
                ])
            )
            return False
            
    except UserNotParticipant:
        await message.reply_text(
            f"🔐 To use this bot, you must join our channel.\n\n"
            f"Please join @{UPDATES_CHANNEL} and try again!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{UPDATES_CHANNEL}")]
            ])
        )
        return False
    except Exception as e:
        logger.error(f"Status check error: {str(e)}")
        return True
        
    return True

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    try:
        if not await check_user_status(message):
            return
            
        # Get user mention
        user_mention = message.from_user.mention
        
        # Send welcome message with inline keyboard
        await message.reply_text(
            f"👋 Welcome {user_mention}!\n\n" + BOT_MESSAGES["start"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📚 Help", callback_data="help"),
                 InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
                [InlineKeyboardButton("📢 Updates", url=f"https://t.me/{UPDATES_CHANNEL}"),
                 InlineKeyboardButton("💬 Support", url=f"https://t.me/{SUPPORT_GROUP}")]
            ])
        )
    except Exception as e:
        logger.error(f"Start command error: {str(e)}")
        await message.reply_text("❌ An error occurred. Please try again later.")

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Handle /help command"""
    try:
        if not await check_user_status(message):
            return
            
        await message.reply_text(
            BOT_MESSAGES["help"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="start")]
            ])
        )
    except Exception as e:
        logger.error(f"Help command error: {str(e)}")
        await message.reply_text("❌ An error occurred. Please try again later.")

@app.on_message(filters.command("settings"))
async def settings_command(client: Client, message: Message):
    """Handle /settings command"""
    try:
        if not await check_user_status(message):
            return
            
        chat_id = message.chat.id
        current_settings = user_settings.get(chat_id, {}).get('settings', DEFAULT_SETTINGS)
        
        settings_text = (
            "⚙️ **Current Settings**\n\n"
            f"• Resolution: `{current_settings.get('resolution', 'Not set')}`\n"
            f"• Preset: `{current_settings.get('preset', 'Not set')}`\n"
            f"• CRF: `{current_settings.get('crf', 'Not set')}`\n"
            f"• Codec: `{current_settings.get('codec', 'Not set')}`\n"
            f"• Pixel Format: `{current_settings.get('pixel_format', 'Not set')}`\n\n"
            "Click below to modify settings:"
        )
        
        await message.reply_text(
            settings_text,
            reply_markup=build_settings_keyboard(current_settings)
        )
    except Exception as e:
        logger.error(f"Settings command error: {str(e)}")
        await message.reply_text("❌ An error occurred. Please try again later.")

@app.on_message(filters.command("reset"))
async def reset_command(client: Client, message: Message):
    """Handle /reset command"""
    try:
        if not await check_user_status(message):
            return
            
        chat_id = message.chat.id
        if chat_id in user_settings:
            del user_settings[chat_id]
            
        await message.reply_text(
            "✅ Settings have been reset to default values.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ View Settings", callback_data="settings")]
            ])
        )
    except Exception as e:
        logger.error(f"Reset command error: {str(e)}")
        await message.reply_text("❌ An error occurred. Please try again later.")

@app.on_message(filters.command("status"))
async def status_command(client: Client, message: Message):
    """Handle /status command"""
    try:
        if message.from_user.id != OWNER_ID:
            await message.reply_text("⚠️ This command is only for the bot owner.")
            return
            
        # Collect bot statistics
        total_users = len(user_settings)
        active_processes = len(active_processes)
        
        # Get system statistics
        cpu_usage = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        status_text = (
            "🤖 **Bot Status**\n\n"
            f"👥 Total Users: {total_users}\n"
            f"⚙️ Active Processes: {active_processes}\n\n"
            "💻 **System Status**\n\n"
            f"CPU Usage: {cpu_usage}%\n"
            f"RAM Usage: {memory.percent}%\n"
            f"Disk Usage: {disk.percent}%\n"
            f"Free Disk Space: {humanize.naturalsize(disk.free)}\n\n"
            f"🕒 Bot Uptime: {humanize.naturaltime(time.time() - bot_start_time)}"
        )
        
        await message.reply_text(status_text)
    except Exception as e:
        logger.error(f"Status command error: {str(e)}")
        await message.reply_text("❌ An error occurred. Please try again later.")

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    """Handle /cancel command"""
    try:
        chat_id = message.chat.id
        
        if chat_id in active_processes:
            processor = active_processes[chat_id]
            await processor.cleanup()
            del active_processes[chat_id]
            
            await message.reply_text(
                "✅ Current process has been cancelled.\n"
                "Send a new video to start over."
            )
        else:
            await message.reply_text(
                "❌ No active process to cancel.\n"
                "Send a video to start compression."
            )
    except Exception as e:
        logger.error(f"Cancel command error: {str(e)}")
        await message.reply_text("❌ An error occurred. Please try again later.")

@app.on_message(filters.video | filters.document)
async def handle_video(client: Client, message: Message):
    """Handle incoming video or document"""
    try:
        chat_id = message.chat.id
        
        # Check user status
        if not await check_user_status(message):
            return
            
        # Check if user has ongoing process
        if chat_id in active_processes:
            await message.reply_text(
                "⚠️ You have an ongoing compression process.\n"
                "Please wait for it to complete or use /cancel to stop it."
            )
            return

        # Validate file size
        file_size = (message.video or message.document).file_size
        if file_size > 2 * 1024 * 1024 * 1024:  # 2GB
            await message.reply_text(
                "❌ File too large (>2GB).\n"
                "Please send a smaller video."
            )
            return

        # Initial menu
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Compress", callback_data="compress_init")],
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ])
        
        await message.reply_text(
            "🎥 **Video Compression**\n\n"
            f"File size: {humanize.naturalsize(file_size)}\n"
            "Would you like to compress this video?",
            reply_markup=keyboard
        )
        
        # Store message info for later use
        user_settings[chat_id] = {
            'original_message': message,
            'settings': user_settings.get(chat_id, {}).get('settings', DEFAULT_SETTINGS.copy())
        }
        
    except Exception as e:
        logger.error(f"Video handler error: {str(e)}")
        await message.reply_text("❌ An error occurred. Please try again later.")

#================================#
# PART 5: CALLBACK HANDLERS      #
#================================#

@app.on_callback_query()
async def handle_callback(client: Client, callback: CallbackQuery):
    """Handle callback queries from inline keyboards"""
    try:
        chat_id = callback.message.chat.id
        data = callback.data
        
        # Check user status for all callbacks except help and start
        if data not in ['help', 'start'] and not await check_user_status(callback.message):
            await callback.answer("Please join the channel first!", show_alert=True)
            return

        if data == "start":
            await callback.message.edit_text(
                f"👋 Welcome {callback.from_user.mention}!\n\n" + BOT_MESSAGES["start"],
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📚 Help", callback_data="help"),
                     InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
                    [InlineKeyboardButton("📢 Updates", url=f"https://t.me/{UPDATES_CHANNEL}"),
                     InlineKeyboardButton("💬 Support", url=f"https://t.me/{SUPPORT_GROUP}")]
                ])
            )

        elif data == "help":
            await callback.message.edit_text(
                BOT_MESSAGES["help"],
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="start")]
                ])
            )

        elif data == "settings":
            current_settings = user_settings.get(chat_id, {}).get('settings', DEFAULT_SETTINGS.copy())
            settings_text = (
                "⚙️ **Current Settings**\n\n"
                f"• Resolution: `{current_settings.get('resolution', 'Not set')}`\n"
                f"• Preset: `{current_settings.get('preset', 'Not set')}`\n"
                f"• CRF: `{current_settings.get('crf', 'Not set')}`\n"
                f"• Codec: `{current_settings.get('codec', 'Not set')}`\n"
                f"• Pixel Format: `{current_settings.get('pixel_format', 'Not set')}`\n\n"
                "Click below to modify settings:"
            )
            await callback.message.edit_text(
                settings_text,
                reply_markup=build_settings_keyboard(current_settings)
            )

        elif data == "compress_init":
            if chat_id not in user_settings:
                await callback.answer("Session expired. Please send the video again.", show_alert=True)
                return
                
            keyboard = build_settings_keyboard(user_settings[chat_id].get('settings', DEFAULT_SETTINGS.copy()))
            await callback.message.edit_text(
                "⚙️ **Compression Settings**\n\n"
                "Please select your preferred settings:\n"
                "• Resolution: Video quality\n"
                "• Preset: Compression speed\n"
                "• CRF: Quality control\n"
                "• Codec: Compression method\n"
                "• Pixel Format: Color encoding\n\n"
                "Current selections will be marked with ✓",
                reply_markup=keyboard
            )

        elif data.startswith("set_"):
            if chat_id not in user_settings:
                await callback.answer("Session expired. Please start over.", show_alert=True)
                return
                
            setting_type, value = data.split("_")[1:]
            if 'settings' not in user_settings[chat_id]:
                user_settings[chat_id]['settings'] = DEFAULT_SETTINGS.copy()
            user_settings[chat_id]['settings'][setting_type] = value
            
            keyboard = build_settings_keyboard(user_settings[chat_id]['settings'])
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await callback.answer(f"{setting_type.title()} set to {value}")

        elif data.startswith("info_"):
            setting_type = data.split("_")[1]
            await callback.answer(
                SETTINGS_INFO[setting_type],
                show_alert=True,
                cache_time=60
            )

        elif data == "confirm_settings":
            if not all(key in user_settings[chat_id]['settings'] 
                      for key in ['resolution', 'preset', 'crf', 'codec', 'pixel_format']):
                await callback.answer("Please select all settings first!", show_alert=True)
                return
                
            # Show estimated size and time
            original_message = user_settings[chat_id]['original_message']
            file_size = (original_message.video or original_message.document).file_size
            
            # Calculate estimates
            estimated_size = int(file_size * 0.7)  # Simple estimation
            estimated_time = "5-10 minutes"  # Simple estimation
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📹 Video", callback_data="upload_video"),
                    InlineKeyboardButton("📄 Document", callback_data="upload_document")
                ],
                [
                    InlineKeyboardButton("🔙 Back", callback_data="compress_init"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                ]
            ])
            
            await callback.message.edit_text(
                "📤 **Select Upload Format**\n\n"
                "Video: Better preview, limited to 8 minutes for non-premium users\n"
                "Document: No limit, but no preview\n\n"
                f"Estimated output size: {humanize.naturalsize(estimated_size)}\n"
                f"Estimated time: {estimated_time}",
                reply_markup=keyboard
            )

        elif data.startswith("upload_"):
            if chat_id not in user_settings:
                await callback.answer("Session expired. Please start over.", show_alert=True)
                return
                
            upload_format = data.split("_")[1]
            processor = VideoProcessor(
                client,
                user_settings[chat_id]['original_message'],
                user_settings[chat_id]['settings']
            )
            await processor.start_processing(upload_format)
            del user_settings[chat_id]

        elif data == "cancel":
            if chat_id in user_settings:
                del user_settings[chat_id]
            if chat_id in active_processes:
                processor = active_processes[chat_id]
                await processor.cleanup()
                del active_processes[chat_id]
            await callback.message.edit_text(
                "❌ Operation cancelled.\n"
                "Send another video to start over."
            )

        await callback.answer()

    except Exception as e:
        logger.error(f"Callback error: {str(e)}")
        try:
            await callback.answer("❌ An error occurred. Please try again.", show_alert=True)
        except:
            pass

#================================#
# PART 6: MAIN EXECUTION         #
#================================#

async def check_ffmpeg():
    """Check if FFmpeg is installed"""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except:
        logger.error("FFmpeg is not installed!")
        return False

async def cleanup_temp_files():
    """Clean up temporary files in downloads directory"""
    try:
        for filename in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            try:
                if os.path.isfile(filepath) and time.time() - os.path.getmtime(filepath) > 3600:
                    os.remove(filepath)
            except:
                pass
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")

async def startup():
    """Perform startup checks and initialization"""
    try:
        # Create downloads directory
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        
        # Check FFmpeg installation
        if not await check_ffmpeg():
            logger.error("FFmpeg is required but not installed. Please install FFmpeg first.")
            return False
            
        # Clean up old files
        await cleanup_temp_files()
        
        # Log startup
        logger.info("Bot started successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Startup error: {str(e)}")
        return False

if __name__ == "__main__":
    # Set bot start time
    bot_start_time = time.time()
    
    # Print banner
    print("""
    =================================
    Video Compression Bot Started
    =================================
    Bot Username: @YourBotUsername
    Version: 1.0
    Status: Running
    =================================
    """)
    
    # Start the bot
    loop = asyncio.get_event_loop()
    if loop.run_until_complete(startup()):
        app.run()
    else:
        print("Startup failed! Check logs for details.")
