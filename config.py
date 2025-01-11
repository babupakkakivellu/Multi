class Config:
    # Replace these with your actual values
    API_ID = "YOUR_API_ID"
    API_HASH = "YOUR_API_HASH"
    BOT_TOKEN = "YOUR_BOT_TOKEN"

    # Bot messages
    START_MSG = """**🎥 Video Processor Bot**

Send me any video to:
• ✂️ Remove unwanted streams
• 🗜️ Compress with custom settings
• 📦 Get smaller file size

ℹ️ Supported formats: MP4, MKV, AVI, etc."""

    CHOOSE_OPERATION_MSG = """**🎯 Choose operation:**

• Remove Streams - Select which streams to keep/remove
• Compress Video - Compress to smaller size
• Cancel - Abort operation"""

    COMPRESSION_HELP_MSG = """**🗜️ Compression Settings**

• Resolution: Higher = Better quality
• Codec: H.265 = Smaller size
• CRF: Lower = Better quality

Current Settings:
└ Resolution: {resolution}p
└ Codec: {codec}
└ CRF: {crf}"""

    STREAM_SELECTION_MSG = """**✂️ Select streams to remove:**

⬜️ = Keep stream
☑️ = Remove stream"""
