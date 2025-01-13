from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import asyncio
import os
import time
import math
import json
from datetime import datetime

class UIManager:
    def __init__(self):
        self.last_update = 0
        self.update_interval = 2  # seconds

    def create_progress_bar(self, current, total, length=20):
        percentage = current / total
        filled_length = int(length * percentage)
        bar = '█' * filled_length + '░' * (length - filled_length)
        return bar

    def format_size(self, size_bytes):
        if size_bytes == 0:
            return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"

    def get_welcome_message(self):
        return (
            "╔══════ 🎬 ENCODER PRO 2.0 ══════╗\n"
            "║    Professional Encoding Suite    ║\n"
            "╚════════════════════════════════╝\n\n"
            "📊 SYSTEM STATUS\n"
            "┌─────────── LIVE ───────────┐\n"
            "│ CPU: [▰▰▰▰▱▱] 40% 🟢      │\n"
            "│ GPU: [▰▰▰▰▰▱] 50% 🟡      │\n"
            "│ RAM: [▰▰▰▱▱▱] 30% 🟢      │\n"
            "└──────────────────────────┘\n"
        )

    def get_welcome_buttons(self):
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🆕 New Task", callback_data="new_task"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings")
            ],
            [
                InlineKeyboardButton("📊 Statistics", callback_data="stats"),
                InlineKeyboardButton("💡 Help", callback_data="help")
            ],
            [
                InlineKeyboardButton("📋 Queue", callback_data="queue"),
                InlineKeyboardButton("⚡ Boost", callback_data="boost")
            ]
        ])

    def get_settings_message(self):
        return (
            "⚙️ ADVANCED SETTINGS\n\n"
            "[Video Settings]\n"
            "┌─────────┬─────────┬─────────┐\n"
            "│🎯 CRF   │⚡ Speed │🎨 Tune  │\n"
            "├─────────┼─────────┼─────────┤\n"
            "│18 Ultra │Slow     │Film     │\n"
            "│23 High  │Medium   │Animation│\n"
            "│28 Medium│Fast     │Grain    │\n"
            "└─────────┴─────────┴─────────┘\n"
        )

    def get_settings_buttons(self):
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎯 Quality", callback_data="set_quality"),
                InlineKeyboardButton("⚡ Speed", callback_data="set_speed")
            ],
            [
                InlineKeyboardButton("🔊 Audio", callback_data="set_audio"),
                InlineKeyboardButton("📊 Size", callback_data="set_size")
            ],
            [
                InlineKeyboardButton("↩️ Back", callback_data="main_menu")
            ]
        ])

    async def create_progress_message(self, current, total, message, start_time, action):
        now = time.time()
        if now - self.last_update < self.update_interval:
            return

        self.last_update = now
        elapsed_time = now - start_time
        speed = current / elapsed_time if elapsed_time > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0
        percentage = current * 100 / total

        progress_text = (
            f"🎯 {action.upper()} PROGRESS\n\n"
            f"┌──────── Status ──────────┐\n"
            f"│ {self.create_progress_bar(current, total)} {percentage:.1f}% │\n"
            f"└──────────────────────────┘\n\n"
            f"📊 STATISTICS\n"
            f"├─💫 Progress: {percentage:.1f}%\n"
            f"├─📦 Size: {self.format_size(current)}/{self.format_size(total)}\n"
            f"├─⚡ Speed: {self.format_size(speed)}/s\n"
            f"├─⏱️ Elapsed: {time.strftime('%H:%M:%S', time.gmtime(elapsed_time))}\n"
            f"└─⌛ ETA: {time.strftime('%H:%M:%S', time.gmtime(eta))}\n"
        )

        try:
            await message.edit_text(
                progress_text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⏸️ Pause", callback_data="pause"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                ]])
            )
        except Exception as e:
            print(f"Progress update error: {e}")

class EncodingManager:
    def __init__(self):
        self.current_process = None
        self.encoding_queue = []
        self.active_tasks = {}

    async def get_video_duration(self, input_path):
        try:
            process = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                input_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return float(stdout.decode().strip())
        except:
            return 0

    async def extract_thumbnail(self, input_path, output_path):
        try:
            duration = await self.get_video_duration(input_path)
            middle_time = duration / 2

            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-ss', str(middle_time),
                '-i', input_path,
                '-vframes', '1',
                '-vf', 'scale=320:-1',
                '-y',
                output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            if os.path.exists(output_path):
                return output_path
            return None
        except:
            return None

    async def encode_video(self, input_path, output_path, status_message, ui_manager):
        try:
            duration = await self.get_video_duration(input_path)
            start_time = time.time()

            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-i', input_path,
                '-c:v', 'libx264', '-preset', 'medium',
                '-c:a', 'aac',
                '-progress', 'pipe:1',
                output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            self.current_process = process

            while True:
                if process.stdout:
                    line = await process.stdout.readline()
                    if not line:
                        break
                        
                    line_str = line.decode('utf-8')
                    if 'out_time_ms=' in line_str:
                        time_in_ms = int(line_str.split('=')[1])
                        current_time = time_in_ms / 1000000
                        
                        await ui_manager.create_progress_message(
                            current_time,
                            duration,
                            status_message,
                            start_time,
                            "Encoding"
                        )

            await process.wait()
            return process.returncode == 0

        except Exception as e:
            print(f"Encoding error: {e}")
            return False

    async def cancel_encoding(self):
        if self.current_process:
            self.current_process.terminate()
            await self.current_process.wait()
            self.current_process = None

class EncoderBot:
    def __init__(self, api_id, api_hash, bot_token):
        self.app = Client("encoder_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)
        self.ui_manager = UIManager()
        self.encoding_manager = EncodingManager()
        self.user_settings = {}

    async def handle_video(self, message: Message):
        try:
            # Initial status message
            status_msg = await message.reply_text(
                "╔══════ 🎬 NEW TASK ══════╗\n"
                "║    Initializing Process    ║\n"
                "╚════════════════════════════╝\n\n"
                "🔍 Analyzing video...",
                quote=True
            )

            # Get file information
            if message.video:
                file_name = message.video.file_name
                file_size = message.video.file_size
                duration = message.video.duration
                width = message.video.width
                height = message.video.height
            else:
                file_name = message.document.file_name
                file_size = message.document.file_size
                duration = 0
                width = height = 0

            # Show file info
            await status_msg.edit_text(
                "╔══════ 📋 FILE INFO ══════╗\n"
                f"├ 📁 Name: {file_name}\n"
                f"├ 📦 Size: {self.ui_manager.format_size(file_size)}\n"
                f"├ ⏱️ Duration: {time.strftime('%H:%M:%S', time.gmtime(duration))}\n"
                f"└ 📺 Resolution: {width}x{height}\n\n"
                "📥 Starting Download..."
            )

            # Download
            start_time = time.time()
            download_path = f"downloads/{file_name}"
            os.makedirs("downloads", exist_ok=True)

            downloaded_file = await message.download(
                file_name=download_path,
                progress=lambda current, total: asyncio.create_task(
                    self.ui_manager.create_progress_message(
                        current, total, status_msg, start_time, "Downloading"
                    )
                )
            )

            # Extract thumbnail
            await status_msg.edit_text("🎯 Extracting Thumbnail...")
            thumb_path = f"{download_path}_thumb.jpg"
            thumb = await self.encoding_manager.extract_thumbnail(downloaded_file, thumb_path)

            # Encode
            await status_msg.edit_text(
                "╔══════ 🎬 ENCODING ══════╗\n"
                "║    Starting Process       ║\n"
                "╚════════════════════════════╝"
            )
            
            output_path = f"encoded_{file_name}"
            success = await self.encoding_manager.encode_video(
                downloaded_file,
                output_path,
                status_msg,
                self.ui_manager
            )

            if not success:
                raise Exception("Encoding failed")

            # Upload
            start_time = time.time()
            await status_msg.edit_text(
                "╔══════ 📤 UPLOAD ══════╗\n"
                "║    Starting Upload       ║\n"
                "╚════════════════════════════╝"
            )
            
            # Upload parameters
            upload_params = {
                "file_name": file_name,
                "thumb": thumb,
                "duration": duration,
                "width": width,
                "height": height,
                "caption": (
                    "╔══════ ✅ ENCODED ══════╗\n"
                    f"├ 📁 File: {file_name}\n"
                    f"├ 📦 Original: {self.ui_manager.format_size(file_size)}\n"
                    f"├ 📊 New Size: {self.ui_manager.format_size(os.path.getsize(output_path))}\n"
                    f"├ 📺 Quality: High\n"
                    "└ 🎯 Encoded by @YourBot"
                ),
                "supports_streaming": True,
                "progress": lambda current, total: asyncio.create_task(
                    self.ui_manager.create_progress_message(
                        current, total, status_msg, start_time, "Uploading"
                    )
                )
            }

            await message.reply_video(
                output_path,
                **upload_params
            )

            # Cleanup
            if thumb:
                os.remove(thumb)
            os.remove(downloaded_file)
            os.remove(output_path)
            await status_msg.delete()

        except Exception as e:
            await status_msg.edit_text(
                "╔══════ ❌ ERROR ══════╗\n"
                f"├ Type: {type(e).__name__}\n"
                f"├ Details: {str(e)}\n"
                "└ Status: Process Failed\n\n"
                "🔄 Options:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Retry", callback_data="retry"),
                    InlineKeyboardButton("⚙️ Settings", callback_data="settings")
                ]])
            )

    async def start(self):
        @self.app.on_message(filters.command("start"))
        async def start_command(client, message):
            welcome_message = self.ui_manager.get_welcome_message()
            welcome_buttons = self.ui_manager.get_welcome_buttons()
            await message.reply_text(welcome_message, reply_markup=welcome_buttons)

        @self.app.on_message(filters.command("settings"))
        async def settings_command(client, message):
            settings_message = self.ui_manager.get_settings_message()
            settings_buttons = self.ui_manager.get_settings_buttons()
            await message.reply_text(settings_message, reply_markup=settings_buttons)

        @self.app.on_message(filters.video | filters.document)
        async def on_video(client, message):
            await self.handle_video(message)

        @self.app.on_callback_query()
        async def callback_handler(client, callback_query: CallbackQuery):
            data = callback_query.data
            
            if data == "cancel":
                await self.encoding_manager.cancel_encoding()
                await callback_query.message.edit_text(
                    "╔══════ ❌ CANCELLED ══════╗\n"
                    "║    Process Terminated      ║\n"
                    "╚════════════════════════════╝"
                )
            elif data == "settings":
                settings_message = self.ui_manager.get_settings_message()
                settings_buttons = self.ui_manager.get_settings_buttons()
                await callback_query.message.edit_text(
                    settings_message,
                    reply_markup=settings_buttons
                )
            elif data == "retry":
                await self.handle_video(callback_query.message.reply_to_message)
            
            await callback_query.answer()

        await self.app.start()
        print("✅ Bot Started Successfully!")
        await self.app.idle()

# Usage
if __name__ == "__main__":
    # Replace with your credentials
    API_ID = "16501053"
    API_HASH = "d8c9b01c863dabacc484c2c06cdd0f6e"
    BOT_TOKEN = "6738287955:AAE5lXdu_kbQevdyImUIJ84CTwwNhELjHK4"

    # Create and start bot
    bot = EncoderBot(API_ID, API_HASH, BOT_TOKEN)
    asyncio.run(bot.start())
