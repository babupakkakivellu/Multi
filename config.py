class Config:
    # Replace these with your actual values
    API_ID = "16501053"
    API_HASH = "d8c9b01c863dabacc484c2c06cdd0f6e"
    BOT_TOKEN = "6738287955:AAE5lXdu_kbQevdyImUIJ84CTwwNhELjHK4"

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
