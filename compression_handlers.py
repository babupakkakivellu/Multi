# compression_handlers.py

import os
import ffmpeg
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config, Messages, logger, humanbytes
from bot_handlers import user_settings, progress

class CompressionHandler:
    """Handles all compression-related callbacks and processing"""

    @staticmethod
    @app.on_callback_query(filters.regex("^compress_start$"))
    async def show_compression_settings(client: Client, callback: CallbackQuery):
        """Show initial compression settings menu"""
        try:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"📺 {res}", callback_data=f"res_{res}") 
                 for res in list(Config.RESOLUTIONS.keys())[:4]],
                [InlineKeyboardButton(f"📺 {res}", callback_data=f"res_{res}") 
                 for res in list(Config.RESOLUTIONS.keys())[4:]],
                [InlineKeyboardButton("➡️ Next", callback_data="show_presets"),
                 InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ])
            await callback.message.edit_text(
                "🎯 Select Video Resolution:\n"
                "Higher resolution = Better quality but larger file size",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Resolution Menu Error: {str(e)}")
            await callback.message.edit_text("❌ Error showing resolution options.")

    @staticmethod
    @app.on_callback_query(filters.regex("^res_(.+)"))
    async def handle_resolution_selection(client: Client, callback: CallbackQuery):
        """Handle resolution selection"""
        try:
            resolution = callback.matches[0].group(1)
            user_settings[callback.from_user.id]['resolution'] = Config.RESOLUTIONS[resolution]
            logger.info(f"User {callback.from_user.id} selected resolution: {resolution}")
            await CompressionHandler.show_presets(client, callback)
        except Exception as e:
            logger.error(f"Resolution Selection Error: {str(e)}")
            await callback.message.edit_text("❌ Error processing resolution selection.")

    @staticmethod
    async def show_presets(client: Client, callback: CallbackQuery):
        """Show preset selection menu"""
        try:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"⚙️ {preset}", callback_data=f"preset_{preset}") 
                 for preset in Config.PRESETS[:4]],
                [InlineKeyboardButton(f"⚙️ {preset}", callback_data=f"preset_{preset}") 
                 for preset in Config.PRESETS[4:]],
                [
                    InlineKeyboardButton("⬅️ Back", callback_data="compress_start"),
                    InlineKeyboardButton("➡️ Next", callback_data="show_crf"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                ]
            ])
            await callback.message.edit_text(
                "⚙️ Select Encoding Preset:\n"
                "Slower = Better compression but takes longer",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Preset Menu Error: {str(e)}")
            await callback.message.edit_text("❌ Error showing preset options.")

    @staticmethod
    @app.on_callback_query(filters.regex("^preset_(.+)"))
    async def handle_preset_selection(client: Client, callback: CallbackQuery):
        """Handle preset selection"""
        try:
            preset = callback.matches[0].group(1)
            user_settings[callback.from_user.id]['preset'] = preset
            logger.info(f"User {callback.from_user.id} selected preset: {preset}")
            await CompressionHandler.show_crf(client, callback)
        except Exception as e:
            logger.error(f"Preset Selection Error: {str(e)}")
            await callback.message.edit_text("❌ Error processing preset selection.")

    @staticmethod
    async def show_crf(client: Client, callback: CallbackQuery):
        """Show CRF selection menu"""
        try:
            # Create rows of CRF values
            crf_buttons = []
            for i in range(0, len(Config.CRFS), 5):
                row = [
                    InlineKeyboardButton(f"🎚️ {crf}", callback_data=f"crf_{crf}") 
                    for crf in Config.CRFS[i:i+5]
                ]
                crf_buttons.append(row)
            
            # Add navigation buttons
            crf_buttons.append([
                InlineKeyboardButton("⬅️ Back", callback_data="show_presets"),
                InlineKeyboardButton("➡️ Next", callback_data="show_pixel_format"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ])
            
            markup = InlineKeyboardMarkup(crf_buttons)
            
            await callback.message.edit_text(
                "🎚️ Select CRF Value:\n"
                "15-30 (Lower = Better quality but larger file size)",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"CRF Menu Error: {str(e)}")
            await callback.message.edit_text("❌ Error showing CRF options.")

    @staticmethod
    @app.on_callback_query(filters.regex("^crf_(\d+)"))
    async def handle_crf_selection(client: Client, callback: CallbackQuery):
        """Handle CRF selection"""
        try:
            crf = int(callback.matches[0].group(1))
            user_settings[callback.from_user.id]['crf'] = crf
            logger.info(f"User {callback.from_user.id} selected CRF: {crf}")
            await CompressionHandler.show_pixel_format(client, callback)
        except Exception as e:
            logger.error(f"CRF Selection Error: {str(e)}")
            await callback.message.edit_text("❌ Error processing CRF selection.")

    @staticmethod
    async def show_pixel_format(client: Client, callback: CallbackQuery):
        """Show pixel format selection menu"""
        try:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🎨 {pix_fmt}", callback_data=f"pix_fmt_{pix_fmt}") 
                 for pix_fmt in Config.PIXEL_FORMATS],
                [
                    InlineKeyboardButton("⬅️ Back", callback_data="show_crf"),
                    InlineKeyboardButton("➡️ Next", callback_data="show_codec"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                ]
            ])
            await callback.message.edit_text(
                "🎨 Select Pixel Format:\n"
                "yuv420p is recommended for most cases",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Pixel Format Menu Error: {str(e)}")
            await callback.message.edit_text("❌ Error showing pixel format options.")

    @staticmethod
    @app.on_callback_query(filters.regex("^pix_fmt_(.+)"))
    async def handle_pixel_format_selection(client: Client, callback: CallbackQuery):
        """Handle pixel format selection"""
        try:
            pix_fmt = callback.matches[0].group(1)
            user_settings[callback.from_user.id]['pixel_format'] = pix_fmt
            logger.info(f"User {callback.from_user.id} selected pixel format: {pix_fmt}")
            await CompressionHandler.show_codec(client, callback)
        except Exception as e:
            logger.error(f"Pixel Format Selection Error: {str(e)}")
            await callback.message.edit_text("❌ Error processing pixel format selection.")

    @staticmethod
    async def show_codec(client: Client, callback: CallbackQuery):
        """Show codec selection menu"""
        try:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🎬 {codec}", callback_data=f"codec_{codec}") 
                 for codec in Config.CODECS],
                [
                    InlineKeyboardButton("⬅️ Back", callback_data="show_pixel_format"),
                    InlineKeyboardButton("➡️ Next", callback_data="show_upload_format"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                ]
            ])
            await callback.message.edit_text(
                "🎬 Select Video Codec:\n"
                "• libx264: Faster, widely compatible\n"
                "• libx265: Better compression, less compatible",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Codec Menu Error: {str(e)}")
            await callback.message.edit_text("❌ Error showing codec options.")

    @staticmethod
    @app.on_callback_query(filters.regex("^codec_(.+)"))
    async def handle_codec_selection(client: Client, callback: CallbackQuery):
        """Handle codec selection"""
        try:
            codec = callback.matches[0].group(1)
            user_settings[callback.from_user.id]['codec'] = codec
            logger.info(f"User {callback.from_user.id} selected codec: {codec}")
            await CompressionHandler.show_upload_format(client, callback)
        except Exception as e:
            logger.error(f"Codec Selection Error: {str(e)}")
            await callback.message.edit_text("❌ Error processing codec selection.")
