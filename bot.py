import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import FloodWait
import subprocess
import time
import shutil
from config import API_ID, API_HASH, BOT_TOKEN

class VideoCompressBot:
    def __init__(self):
        self.app = Client("video_compress_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
        self.user_settings = {}
        self.compression_settings = {
            "resolution": {
                "144p": "256x144",
                "240p": "426x240",
                "360p": "640x360",
                "480p": "854x480",
                "720p": "1280x720",
                "1080p": "1920x1080",
                "4K": "3840x2160"
            },
            "preset": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
            "crf": list(range(15, 31)),
            "pixel_format": ["yuv420p", "yuv444p"],
            "codec": ["libx264", "libx265"]
        }
        self.setup_handlers()

    def setup_handlers(self):
        @self.app.on_message(filters.video | filters.document)
        async def handle_video(client, message: Message):
            try:
                buttons = [
                    [InlineKeyboardButton("🎯 Compress", callback_data="start_compress"),
                     InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                ]
                await message.reply_text(
                    "Would you like to compress this video?",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            except Exception as e:
                await message.reply_text(f"Error: {str(e)}")

        @self.app.on_callback_query()
        async def handle_callback(client, callback_query: CallbackQuery):
            try:
                await self._process_callback(callback_query)
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await self._process_callback(callback_query)
            except Exception as e:
                await callback_query.message.reply_text(f"Error: {str(e)}")

    async def _process_callback(self, callback_query: CallbackQuery):
        data = callback_query.data
        user_id = callback_query.from_user.id
        message = callback_query.message

        if data == "start_compress":
            self.user_settings[user_id] = {}
            await self._show_settings_menu(message, user_id)

        elif data in self.compression_settings:
            await self._show_setting_options(message, data)

        elif data.startswith("set_"):
            await self._handle_setting_selection(message, data, user_id)

        elif data == "confirm_settings":
            await self._show_upload_menu(message)

        elif data in ["upload_document", "upload_video"]:
            await self._handle_upload_type(message, user_id, data)

        elif data == "cancel":
            await self._handle_cancel(message, user_id)

    async def _show_settings_menu(self, message: Message, user_id: int):
        settings = self.user_settings.get(user_id, {})
        buttons = [
            [InlineKeyboardButton(f"Resolution: {settings.get('resolution', 'Not Set')}", 
                                callback_data="resolution")],
            [InlineKeyboardButton(f"Preset: {settings.get('preset', 'Not Set')}", 
                                callback_data="preset")],
            [InlineKeyboardButton(f"CRF: {settings.get('crf', 'Not Set')}", 
                                callback_data="crf")],
            [InlineKeyboardButton(f"Pixel Format: {settings.get('pixel_format', 'Not Set')}", 
                                callback_data="pixel_format")],
            [InlineKeyboardButton(f"Codec: {settings.get('codec', 'Not Set')}", 
                                callback_data="codec")],
            [InlineKeyboardButton("✅ Confirm", callback_data="confirm_settings"),
             InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        await message.edit_text(
            "Select compression settings:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    async def compress_video(self, message: Message, input_file: str, output_file: str, settings: dict):
        try:
            progress_msg = await message.reply_text("Starting compression...")
            
            command = [
                'ffmpeg', '-i', input_file,
                '-c:v', settings['codec'],
                '-preset', settings['preset'],
                '-crf', str(settings['crf']),
                '-vf', f'scale={self.compression_settings["resolution"][settings["resolution"]]}',
                '-pix_fmt', settings['pixel_format'],
                '-y', output_file
            ]

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            while True:
                if process.returncode is not None:
                    break
                await asyncio.sleep(2)
                await progress_msg.edit_text("Compressing... Please wait.")

            await process.communicate()
            await progress_msg.edit_text("Compression completed!")
            return True

        except Exception as e:
            await message.reply_text(f"Compression error: {str(e)}")
            return False

    async def extract_thumbnail(self, input_file: str) -> str:
        try:
            output_file = f"{input_file}_thumb.jpg"
            duration = await self._get_video_duration(input_file)
            middle_time = duration / 2

            command = [
                'ffmpeg', '-ss', str(middle_time),
                '-i', input_file,
                '-vframes', '1',
                '-q:v', '2',
                output_file
            ]

            process = await asyncio.create_subprocess_exec(*command)
            await process.communicate()
            
            return output_file if os.path.exists(output_file) else None

        except Exception as e:
            print(f"Thumbnail extraction error: {e}")
            return None

    async def _get_video_duration(self, input_file: str) -> float:
        command = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            input_file
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, _ = await process.communicate()
        return float(stdout.decode().strip())

    def run(self):
        print("Bot is running...")
        self.app.run()

if __name__ == "__main__":
    bot = VideoCompressBot()
    bot.run()
