# config.py

import os
import logging
from datetime import datetime

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
class Config:
    API_ID = "16501053"
    API_HASH = "d8c9b01c863dabacc484c2c06cdd0f6e"
    BOT_TOKEN = "8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I"
    
    # Compression Settings
    RESOLUTIONS = {
        "144p": "256x144",
        "240p": "426x240",
        "360p": "640x360",
        "480p": "854x480",
        "720p": "1280x720",
        "1080p": "1920x1080",
        "4K": "3840x2160"
    }

    PRESETS = [
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower"
    ]

    PIXEL_FORMATS = [
        "yuv420p",
        "yuv444p",
        "yuv422p"
    ]

    CODECS = [
        "libx264",
        "libx265"
    ]

    CRFS = list(range(15, 31))

    # File size limits (in bytes)
    MAX_FILE_SIZE = 2147483648  # 2GB (Telegram limit)

    # Temporary file directory
    TEMP_DIR = "temp"
    
    # Create temp directory if it doesn't exist
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

# Helper Functions
def humanbytes(size):
    """Convert bytes to human readable format"""
    if not size:
        return "0B"
    power = 2**10
    n = 0
    units = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}B"

def get_progress_text(current, total, action):
    """Generate progress text"""
    if total == 0:
        return f"{action}: N/A"
        
    percent = current * 100 / total
    progress_str = (
        f"{action}: {percent:.1f}%\n"
        f"[{'=' * int(percent/5)}{'.' * (20-int(percent/5))}]\n"
        f"Current: {humanbytes(current)}\n"
        f"Total: {humanbytes(total)}\n"
    )
    return progress_str

# Bot Messages
class Messages:
    START_TEXT = """
👋 Welcome to Video Compress Bot!

Send me any video or document to start compression.
I support various compression settings including:
• Multiple resolutions (144p to 4K)
• Different presets and CRF values
• Various pixel formats and codecs

Send a video to begin!
"""

    HELP_TEXT = """
📖 **How to use this bot:**

1. Send any video file
2. Choose compression settings:
   • Resolution
   • Preset (compression speed)
   • CRF (quality)
   • Pixel Format
   • Codec
3. Select upload format
4. Enter filename

The bot will process your video and send back the compressed version!

**Notes:**
• Maximum file size: 2GB
• Lower CRF = Better quality
• Slower preset = Better compression
"""

    ERROR_MESSAGES = {
        "file_too_large": "⚠️ File too large! Maximum size is 2GB.",
        "processing_error": "❌ Error occurred while processing your video.",
        "compression_error": "❌ Error during compression: {}",
        "cancelled": "✖️ Operation cancelled.",
        "invalid_format": "⚠️ Invalid file format. Please send a video file."
    }

    STATUS_MESSAGES = {
        "init": "⏳ Initializing compression...",
        "downloading": "📥 Downloading: {}%",
        "processing": "🎬 Processing video...",
        "compressing": "🔄 Compressing video...",
        "uploading": "📤 Uploading: {}%",
        "completed": "✅ Compression completed successfully!"
    }
