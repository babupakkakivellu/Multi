# compression_processor.py

import os
import time
import asyncio
import ffmpeg
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config, Messages, logger, humanbytes
from bot_handlers import user_settings, progress

class UploadHandler:
    """Handles upload format selection and file uploading"""

    @staticmethod
    async def show_upload_format(client: Client, callback: CallbackQuery):
        """Show upload format selection menu"""
        try:
            markup = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📹 Video", callback_data="upload_video"),
                    InlineKeyboardButton("📄 Document", callback_data="upload_document")
                ],
                [
                    InlineKeyboardButton("⬅️ Back", callback_data="show_codec"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                ]
            ])
            await callback.message.edit_text(
                "📤 Select Upload Format:\n"
                "• Video: Shows preview, limited to 2GB\n"
                "• Document: No preview, better for large files",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Upload Format Menu Error: {str(e)}")
            await callback.message.edit_text("❌ Error showing upload format options.")

    @staticmethod
    @app.on_callback_query(filters.regex("^upload_(video|document)$"))
    async def handle_upload_format_selection(client: Client, callback: CallbackQuery):
        """Handle upload format selection"""
        try:
            upload_format = callback.matches[0].group(1)
            user_settings[callback.from_user.id]['upload_format'] = upload_format
            
            await callback.message.edit_text(
                "📝 Enter filename for the compressed video (reply to this message):\n"
                "Example: my_compressed_video"
            )
            user_settings[callback.from_user.id]['awaiting_filename'] = True
            logger.info(f"User {callback.from_user.id} selected upload format: {upload_format}")
        except Exception as e:
            logger.error(f"Upload Format Selection Error: {str(e)}")
            await callback.message.edit_text("❌ Error processing upload format selection.")

class FFmpegProcessor:
    """Handles video compression using FFmpeg"""

    @staticmethod
    async def compress_video(message, settings):
        """Process video compression using FFmpeg"""
        status_msg = await message.reply_text(Messages.STATUS_MESSAGES["init"])
        input_file = None
        output_file = None
        start_time = time.time()
        
        try:
            # Create unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            input_file = os.path.join(Config.TEMP_DIR, f"input_{timestamp}.mp4")
            output_file = os.path.join(Config.TEMP_DIR, f"{settings['filename']}_{timestamp}.mp4")
            
            # Download video
            await status_msg.edit_text(Messages.STATUS_MESSAGES["downloading"].format("0"))
            input_file = await app.download_media(
                settings["original_message"],
                file_name=input_file,
                progress=progress,
                progress_args=(status_msg, "📥 Downloading")
            )
            
            await status_msg.edit_text(Messages.STATUS_MESSAGES["compressing"])
            
            # Prepare FFmpeg command
            ffmpeg_cmd = (
                ffmpeg
                .input(input_file)
                .output(
                    output_file,
                    vf=f"scale={settings['resolution']}",
                    preset=settings['preset'],
                    crf=settings['crf'],
                    pix_fmt=settings['pixel_format'],
                    vcodec=settings['codec'],
                    acodec='copy',  # Copy audio stream without re-encoding
                    **{'threads': 0}  # Use all available CPU threads
                )
                .overwrite_output()
                .global_args('-hide_banner')
                .global_args('-loglevel', 'error')
            )
            
            # Run FFmpeg
            process = await ffmpeg_cmd.run_async(pipe_stdout=True, pipe_stderr=True)
            await process.communicate()
            
            # Get video information
            video_info = ffmpeg.probe(output_file)
            video_stream = next((stream for stream in video_info['streams'] 
                               if stream['codec_type'] == 'video'), None)
            
            if video_stream:
                duration = int(float(video_info['format']['duration']))
                width = int(video_stream['width'])
                height = int(video_stream['height'])
                
                # Calculate compression stats
                original_size = os.path.getsize(input_file)
                compressed_size = os.path.getsize(output_file)
                compression_ratio = (1 - (compressed_size / original_size)) * 100
                process_time = time.time() - start_time
                
                # Prepare detailed caption
                caption = (
                    f"🎥 Compressed Video Stats:\n\n"
                    f"Resolution: {width}x{height}\n"
                    f"Preset: {settings['preset']}\n"
                    f"CRF: {settings['crf']}\n"
                    f"Codec: {settings['codec']}\n"
                    f"Pixel Format: {settings['pixel_format']}\n\n"
                    f"📊 Compression Results:\n"
                    f"Original Size: {humanbytes(original_size)}\n"
                    f"Compressed Size: {humanbytes(compressed_size)}\n"
                    f"Compression Ratio: {compression_ratio:.1f}%\n"
                    f"Process Time: {process_time:.1f}s"
                )
                
                # Upload based on format selection
                await status_msg.edit_text(Messages.STATUS_MESSAGES["uploading"].format("0"))
                
                if settings['upload_format'] == 'video':
                    await app.send_video(
                        message.chat.id,
                        output_file,
                        duration=duration,
                        width=width,
                        height=height,
                        caption=caption,
                        progress=progress,
                        progress_args=(status_msg, "📤 Uploading"),
                        thumb=await FFmpegProcessor.generate_thumbnail(output_file)
                    )
                else:
                    await app.send_document(
                        message.chat.id,
                        output_file,
                        caption=caption,
                        progress=progress,
                        progress_args=(status_msg, "📤 Uploading"),
                        thumb=await FFmpegProcessor.generate_thumbnail(output_file)
                    )
                
                await status_msg.edit_text(Messages.STATUS_MESSAGES["completed"])
                logger.info(f"Compression completed for user {message.from_user.id}")
                
        except Exception as e:
            error_msg = f"❌ Error during compression: {str(e)}"
            logger.error(f"Compression Error: {str(e)}")
            await status_msg.edit_text(error_msg)
            
        finally:
            # Cleanup
            try:
                if input_file and os.path.exists(input_file):
                    os.remove(input_file)
                if output_file and os.path.exists(output_file):
                    os.remove(output_file)
            except Exception as e:
                logger.error(f"Cleanup Error: {str(e)}")

    @staticmethod
    async def generate_thumbnail(video_path):
        """Generate thumbnail for video"""
        try:
            thumbnail_path = f"{video_path}_thumb.jpg"
            
            # Extract thumbnail using FFmpeg
            (
                ffmpeg
                .input(video_path, ss="00:00:01")
                .filter('scale', 320, -1)
                .output(thumbnail_path, vframes=1)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            return thumbnail_path
        except Exception as e:
            logger.error(f"Thumbnail Generation Error: {str(e)}")
            return None

# Main execution
if __name__ == "__main__":
    try:
        # Create necessary directories
        os.makedirs(Config.TEMP_DIR, exist_ok=True)
        
        # Start bot
        logger.info("Starting Video Compress Bot...")
        app.run()
        
    except Exception as e:
        logger.error(f"Bot Startup Error: {str(e)}")
    
    finally:
        # Cleanup temp directory
        try:
            for file in os.listdir(Config.TEMP_DIR):
                file_path = os.path.join(Config.TEMP_DIR, file)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except Exception as e:
                    logger.error(f"Error deleting {file_path}: {str(e)}")
        except Exception as e:
            logger.error(f"Cleanup Error: {str(e)}")
