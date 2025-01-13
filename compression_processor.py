# compression_processor.py

import os
import time
import asyncio
import ffmpeg
from datetime import datetime
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config, Messages, logger, humanbytes
from bot import app

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
        except Exception:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Progress Error: {str(e)}")

class UploadHandler:
    """Handles upload format selection and file uploading"""

    @staticmethod
    async def show_upload_format(client, callback: CallbackQuery):
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
    async def handle_upload_format_selection(client, callback: CallbackQuery):
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
            stream = ffmpeg.input(input_file)
            
            # Add video filters
            stream = ffmpeg.filter(stream, 'scale', settings['resolution'])
            
            # Output options
            output_options = {
                'preset': settings['preset'],
                'crf': settings['crf'],
                'pix_fmt': settings['pixel_format'],
                'c:v': settings['codec'],
                'c:a': 'copy',  # Copy audio stream without re-encoding
                'threads': 0    # Use all available CPU threads
            }
            
            # Run FFmpeg
            await status_msg.edit_text("🎬 Processing video...")
            
            process = (
                ffmpeg
                .output(stream, output_file, **output_options)
                .overwrite_output()
                .global_args('-hide_banner')
                .global_args('-loglevel', 'error')
                .run_async(pipe_stdout=True, pipe_stderr=True)
            )
            
            # Wait for FFmpeg to complete
            stdout, stderr = await process.communicate()
            
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
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
                    
                    # Generate thumbnail
                    thumb = await FFmpegProcessor.generate_thumbnail(output_file)
                    
                    # Prepare caption
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
                    await status_msg.edit_text("📤 Uploading processed video...")
                    
                    try:
                        if settings['upload_format'] == 'video':
                            await app.send_video(
                                message.chat.id,
                                output_file,
                                duration=duration,
                                width=width,
                                height=height,
                                thumb=thumb,
                                caption=caption,
                                progress=progress,
                                progress_args=(status_msg, "📤 Uploading")
                            )
                        else:
                            await app.send_document(
                                message.chat.id,
                                output_file,
                                thumb=thumb,
                                caption=caption,
                                progress=progress,
                                progress_args=(status_msg, "📤 Uploading")
                            )
                        
                        await status_msg.edit_text("✅ Video processed and uploaded successfully!")
                        logger.info(f"Successfully processed video for user {message.from_user.id}")
                        
                    except Exception as e:
                        logger.error(f"Upload Error: {str(e)}")
                        await status_msg.edit_text("❌ Error uploading processed video.")
                        
            else:
                raise Exception("FFmpeg processing failed")
                
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
            
            if os.path.exists(thumbnail_path):
                return thumbnail_path
            return None
            
        except Exception as e:
            logger.error(f"Thumbnail Generation Error: {str(e)}")
            return None

@app.on_message(filters.reply & filters.text)
async def handle_filename(client, message):
    """Handle filename input from user"""
    try:
        user_id = message.from_user.id
        if user_id in user_settings and user_settings[user_id].get('awaiting_filename'):
            user_settings[user_id]['filename'] = message.text
            user_settings[user_id]['awaiting_filename'] = False
            await FFmpegProcessor.compress_video(message, user_settings[user_id])
    except Exception as e:
        logger.error(f"Filename Handler Error: {str(e)}")
        await message.reply_text("❌ Error processing filename.")
