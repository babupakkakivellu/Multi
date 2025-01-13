# bot_handlers.py

import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import (InlineKeyboardMarkup, InlineKeyboardButton, 
                           CallbackQuery, Message)
from pyrogram.errors import FloodWait
from config import Config, Messages, logger, humanbytes
from datetime import datetime

# Initialize bot
app = Client(
    "video_compress_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

# Store user settings
user_settings = {}

async def progress(current, total, message, action):
    """Generic progress function for upload/download"""
    try:
        if total == 0:
            return
            
        percent = current * 100 / total
        progress_str = (
            f"{action}: {percent:.1f}%\n"
            f"[{'=' * int(percent/5)}{'.' * (20-int(percent/5))}]\n"
            f"Current: {humanbytes(current)}\n"
            f"Total: {humanbytes(total)}\n"
        )
        
        try:
            if message.text != progress_str:
                await message.edit_text(progress_str)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            
    except Exception as e:
        logger.error(f"Progress Error: {str(e)}")

class BotCommands:
    """Handler class for bot commands"""
    
    @staticmethod
    @app.on_message(filters.command("start"))
    async def start_command(client, message):
        """Handle /start command"""
        try:
            await message.reply_text(
                Messages.START_TEXT,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("ℹ️ Help", callback_data="help"),
                     InlineKeyboardButton("👨‍💻 About", callback_data="about")]
                ])
            )
            logger.info(f"User {message.from_user.id} started the bot")
        except Exception as e:
            logger.error(f"Start Command Error: {str(e)}")

    @staticmethod
    @app.on_message(filters.command("help"))
    async def help_command(client, message):
        """Handle /help command"""
        try:
            await message.reply_text(
                Messages.HELP_TEXT,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="start")]
                ])
            )
            logger.info(f"User {message.from_user.id} requested help")
        except Exception as e:
            logger.error(f"Help Command Error: {str(e)}")

    @staticmethod
    @app.on_message(filters.command("settings"))
    async def settings_command(client, message):
        """Handle /settings command"""
        try:
            user_id = message.from_user.id
            if user_id in user_settings:
                settings_text = (
                    "Current Settings:\n"
                    f"Resolution: {user_settings[user_id].get('resolution', 'Not set')}\n"
                    f"Preset: {user_settings[user_id].get('preset', 'Not set')}\n"
                    f"CRF: {user_settings[user_id].get('crf', 'Not set')}\n"
                    f"Pixel Format: {user_settings[user_id].get('pixel_format', 'Not set')}\n"
                    f"Codec: {user_settings[user_id].get('codec', 'Not set')}"
                )
            else:
                settings_text = "No active settings. Send a video to start compression."
                
            await message.reply_text(settings_text)
            logger.info(f"User {user_id} checked settings")
        except Exception as e:
            logger.error(f"Settings Command Error: {str(e)}")

class FileHandler:
    """Handler class for file processing"""
    
    @staticmethod
    @app.on_message(filters.video | filters.document)
    async def handle_video(client: Client, message: Message):
        """Initial handler for video/document messages"""
        try:
            # Check if it's a valid video file
            if message.document:
                mime_type = message.document.mime_type
                if not mime_type or not mime_type.startswith('video/'):
                    await message.reply_text(Messages.ERROR_MESSAGES["invalid_format"])
                    return
                file_size = message.document.file_size
            else:
                file_size = message.video.file_size
                
            # Check file size
            if file_size > Config.MAX_FILE_SIZE:
                await message.reply_text(Messages.ERROR_MESSAGES["file_too_large"])
                return
                
            markup = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 Compress", callback_data="compress_start"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                ]
            ])
            
            info_text = (
                "📁 File Information:\n"
                f"Size: {humanbytes(file_size)}\n"
                "Choose an action:"
            )
            
            await message.reply_text(info_text, reply_markup=markup)
            
            # Store message and time information
            user_settings[message.from_user.id] = {
                "original_message": message,
                "start_time": datetime.now(),
                "file_size": file_size
            }
            
            logger.info(f"User {message.from_user.id} started new compression task")
            
        except Exception as e:
            logger.error(f"Handle Video Error: {str(e)}")
            await message.reply_text(Messages.ERROR_MESSAGES["processing_error"])

    @staticmethod
    @app.on_callback_query(filters.regex("^cancel$"))
    async def cancel_operation(client: Client, callback: CallbackQuery):
        """Handle cancel button press"""
        try:
            user_id = callback.from_user.id
            if user_id in user_settings:
                del user_settings[user_id]
            await callback.message.edit_text(Messages.ERROR_MESSAGES["cancelled"])
            logger.info(f"User {user_id} cancelled operation")
        except Exception as e:
            logger.error(f"Cancel Operation Error: {str(e)}")
            await callback.message.edit_text("Error occurred while cancelling.")

# Callback query handler for help and about buttons
@app.on_callback_query(filters.regex("^(help|about|start)$"))
async def handle_help_about(client: Client, callback: CallbackQuery):
    """Handle help and about button callbacks"""
    try:
        if callback.data == "help":
            await callback.message.edit_text(
                Messages.HELP_TEXT,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="start")]
                ])
            )
        elif callback.data == "about":
            about_text = (
                "🤖 **Video Compress Bot**\n\n"
                "A Telegram bot for video compression using FFmpeg.\n\n"
                "**Features:**\n"
                "• Multiple resolution options\n"
                "• Various compression presets\n"
                "• Quality control (CRF)\n"
                "• Different codecs support\n\n"
                "**Developer:** @YourUsername\n"
                "**Version:** 1.0.0"
            )
            await callback.message.edit_text(
                about_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="start")]
                ])
            )
        elif callback.data == "start":
            await callback.message.edit_text(
                Messages.START_TEXT,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("ℹ️ Help", callback_data="help"),
                     InlineKeyboardButton("👨‍💻 About", callback_data="about")]
                ])
            )
    except Exception as e:
        logger.error(f"Help/About Button Error: {str(e)}")
