from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import os
import json
import asyncio
import subprocess
import time
from typing import Dict, Set
from datetime import datetime

# Bot configuration
app = Client(
    "stream_remover_bot",
    api_id="16501053",
    api_hash="d8c9b01c863dabacc484c2c06cdd0f6e",
    bot_token="8125717355:AAGEqXec28WfZ5V_wb4bkKoSyTt_slw6x2I"
)

# Store user data
user_data: Dict[int, dict] = {}

class Timer:
    def __init__(self):
        self.start_time = None
        self.last_update = 0

    def start(self):
        self.start_time = time.time()
        self.last_update = 0

    def should_update(self):
        current_time = time.time()
        if current_time - self.last_update >= 2:
            self.last_update = current_time
            return True
        return False

    def get_elapsed_time(self):
        if self.start_time:
            elapsed = int(time.time() - self.start_time)
            return self.format_time(elapsed)
        return "0s"

    @staticmethod
    def format_time(seconds):
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            seconds = seconds % 60
            return f"{minutes}m {seconds}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            seconds = seconds % 60
            return f"{hours}h {minutes}m {seconds}s"

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

def create_progress_bar(current, total, length=20):
    filled = int(length * current // total)
    bar = "━" * filled + "─" * (length - filled)
    percent = current * 100 / total
    return bar, percent

async def progress(current, total, message, start_time, action):
    if not hasattr(progress, 'timer'):
        progress.timer = Timer()
        progress.timer.start()

    if not progress.timer.should_update() and current != total:
        return

    try:
        bar, percent = create_progress_bar(current, total)
        elapsed_time = progress.timer.get_elapsed_time()
        current_mb = format_size(current)
        total_mb = format_size(total)
        speed = format_size(current/(time.time()-start_time))

        if action == "download":
            status = "📥 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗶𝗻𝗴..."
        else:
            status = "📤𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴..."

        await message.edit_text(
            f"{status}\n\n"
            f"┌ **Progress:** {current_mb} / {total_mb}\n"
            f"├ **Speed:** {speed}/s\n"
            f"├ **Time:** {elapsed_time}\n"
            f"└ {bar} {percent:.1f}%"
        )
    except Exception as e:
        print(f"Progress update error: {str(e)}")

async def extract_thumbnail(file_path):
    try:
        probe = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await probe.communicate()
        metadata = json.loads(stdout)
        
        # Extract duration, width, and height
        duration = int(float(metadata['format']['duration']))
        video_stream = next((s for s in metadata['streams'] if s['codec_type'] == 'video'), None)
        width = int(video_stream['width']) if video_stream else 0
        height = int(video_stream['height']) if video_stream else 0
        
        # Generate thumbnail
        thumbnail_path = f"thumb_{os.path.splitext(os.path.basename(file_path))[0]}.jpg"
        cmd = [
            'ffmpeg', '-ss', str(duration//2),
            '-i', file_path,
            '-vframes', '1',
            '-vf', 'scale=320:-1',
            '-y', thumbnail_path
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        return {
            'thumb_path': thumbnail_path if os.path.exists(thumbnail_path) else None,
            'duration': duration,
            'width': width,
            'height': height
        }
    except Exception as e:
        print(f"Thumbnail extraction error: {str(e)}")
        return None

def get_streamsinfo(file_path: str) -> list:
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_streams',
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)['streams']

def get_stream_info(stream):
    codec_type = stream.get('codec_type', 'unknown').upper()
    codec_name = stream.get('codec_name', 'unknown').upper()
    language = stream.get('tags', {}).get('language', 'und')
    title = stream.get('tags', {}).get('title', '')
    
    info = f"{codec_type} ({codec_name}) - {language}"
    if title:
        info += f" - {title}"
        
    if codec_type == 'VIDEO':
        width = stream.get('width', '?')
        height = stream.get('height', '?')
        fps = stream.get('r_frame_rate', '').split('/')[0]
        info += f" [{width}x{height}]"
        if fps:
            info += f" {fps}fps"
    elif codec_type == 'AUDIO':
        channels = stream.get('channels', '?')
        info += f" ({channels}ch)"
        
    return info

def create_stream_buttons(streams: list, selected_streams: Set[int]) -> list:
    buttons = []
    
    stream_groups = {
        'video': ('🎥 VIDEO STREAMS', []),
        'audio': ('🔊 AUDIO STREAMS', []),
        'subtitle': ('💭 SUBTITLE STREAMS', []),
        'other': ('📎 OTHER STREAMS', [])
    }
    
    for i, stream in enumerate(streams):
        codec_type = stream.get('codec_type', 'unknown').lower()
        stream_info = get_stream_info(stream)
        
        group = codec_type if codec_type in stream_groups else 'other'
        prefix = "☑️" if i in selected_streams else "⬜️"
        
        stream_groups[group][1].append({
            'index': i,
            'info': stream_info,
            'prefix': prefix
        })
    
    for group_name, (header, group_streams) in stream_groups.items():
        if group_streams:
            buttons.append([InlineKeyboardButton(f"═══ {header} ═══", callback_data="header")])
            for stream in group_streams:
                buttons.append([InlineKeyboardButton(
                    f"{stream['prefix']} {stream['info']}",
                    callback_data=f"stream_{stream['index']}"
                )])
    
    buttons.append([
        InlineKeyboardButton("✅ 𝗣𝗿𝗼𝗰𝗲𝘀", callback_data="continue"),
        InlineKeyboardButton("❌ 𝗖𝗮𝗻𝗰𝗲𝗹", callback_data="cancel")
    ])
    
    return buttons

def create_rename_buttons() -> list:
    buttons = [
        [InlineKeyboardButton("✏️ 𝗥𝗲𝗻𝗮𝗺𝗲", callback_data="rename")],
        [
            InlineKeyboardButton("📹 𝗦𝗲𝗻𝗱 𝗮𝘀 𝗩𝗶𝗱𝗲𝗼", callback_data="upload_video"),
            InlineKeyboardButton("📄 𝗦𝗲𝗻𝗱 𝗮𝘀 𝗗𝗼𝗰𝘂𝗺𝗲𝗻𝘁", callback_data="upload_document")
        ],
        [InlineKeyboardButton("⬅️ 𝗕𝗮𝗰𝗸", callback_data="back_to_streams")]
    ]
    return buttons

async def process_video(input_file: str, streams_to_remove: Set[int], total_streams: int) -> str:
    try:
        output_file = f"processed_{os.path.basename(input_file)}"
        
        cmd = ['ffmpeg', '-i', input_file]
        
        for i in range(total_streams):
            if i not in streams_to_remove:
                cmd.extend(['-map', f'0:{i}'])
        
        cmd.extend(['-c', 'copy', output_file])
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise Exception(f"FFmpeg error: {error_message}")
        
        if not os.path.exists(output_file):
            raise Exception("Output file was not created")
            
        return output_file
        
    except Exception as e:
        raise Exception(f"Processing failed: {str(e)}")

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text(
        "**🎥 Stream Remover Bot**\n\n"
        "Send me any video file to:\n"
        "• 👀 View all available streams\n"
        "• ✂️ Select streams to remove\n"
        "• 📝 Rename file (optional)\n"
        "• 📤 Choose upload format\n\n"
        "ℹ️ Supported formats: MP4, MKV, AVI, etc."
    )

@app.on_message(filters.video | filters.document)
async def handle_video(client, message: Message):
    try:
        start_time = time.time()
        status_msg = await message.reply_text("⚡ 𝗜𝗻𝗶𝘁𝗶𝗮𝗹𝗶𝘇𝗶𝗻𝗴...")
        
        async def progress_wrapper(current, total):
            await progress(current, total, status_msg, start_time, "download")
        
        file_path = await message.download(
            progress=progress_wrapper
        )
        
        await status_msg.edit_text("🔍 𝗔𝗻𝗮𝗹𝘆𝘇𝗶𝗻𝗴 𝘀𝘁𝗿𝗲𝗮𝗺𝘀...")
        
        streams = get_streamsinfo(file_path)
        
        user_data[message.from_user.id] = {
            'file_path': file_path,
            'streams': streams,
            'selected_streams': set(),
            'awaiting_rename': False,
            'new_filename': None
        }
        
        buttons = create_stream_buttons(streams, set())
        await status_msg.edit_text(
            "**🎯 𝗦𝗲𝗹𝗲𝗰𝘁 𝘀𝘁𝗿𝗲𝗮𝗺𝘀 𝘁𝗼 𝗿𝗲𝗺𝗼𝘃𝗲:**\n\n"
            "⬜️ = Keep stream\n"
            "☑️ = Remove stream\n\n"
            "_Select all streams you want to remove and press Process._",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error:** {str(e)}")
        if message.from_user.id in user_data:
            del user_data[message.from_user.id]

@app.on_message(filters.text & filters.private)
async def handle_rename(client, message: Message):
    user_id = message.from_user.id
    
    if user_id in user_data and user_data[user_id].get('awaiting_rename'):
        # Get the stored message ID
        last_bot_message_id = user_data[user_id].get('last_bot_message_id')
        
        if message.text == "/cancel":
            user_data[user_id]['awaiting_rename'] = False
            buttons = create_rename_buttons()
            
            await client.edit_message_text(
                chat_id=message.chat.id,
                message_id=last_bot_message_id,
                text="**📤 Choose upload options:**\n\n"
                "• ✏️ Rename - Change filename\n"
                "• 📹 Video - Better for watching in Telegram\n"
                "• 📄 Document - Original quality",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await message.delete()
            return

        user_data[user_id]['new_filename'] = message.text
        user_data[user_id]['awaiting_rename'] = False
        buttons = create_rename_buttons()
        
        # Edit the bot's previous message using the stored message ID
        await client.edit_message_text(
            chat_id=message.chat.id,
            message_id=last_bot_message_id,
            text=f"**✅ Filename set to:** `{message.text}`\n\n"
                 "Now choose upload format:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        # Delete the user's message containing the new filename
        await message.delete()

@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if user_id not in user_data and callback_query.data != "header":
        await callback_query.answer("Session expired. Please send the video again.", show_alert=True)
        return
    
    if callback_query.data == "header":
        await callback_query.answer("Section header")
        return

    data = callback_query.data
    user = user_data[user_id]
    
    try:
        if data.startswith("stream_"):
            stream_index = int(data.split("_")[1])
            if stream_index in user['selected_streams']:
                user['selected_streams'].remove(stream_index)
            else:
                user['selected_streams'].add(stream_index)
            
            buttons = create_stream_buttons(user['streams'], user['selected_streams'])
            await callback_query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
        elif data == "continue":
            buttons = create_rename_buttons()
            await callback_query.message.edit_text(
                "**📤 Choose upload options:**\n\n"
                "• ✏️ Rename - Change filename\n"
                "• 📹 Video - Better for watching in Telegram\n"
                "• 📄 Document - Original quality",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data == "rename":
            user_data[user_id]['awaiting_rename'] = True
            # Store the message ID that we'll need to edit later
            user_data[user_id]['last_bot_message_id'] = callback_query.message.id
            await callback_query.message.edit_text(
                 "**✏️ Please send the new filename:**\n\n"
                 "• Send the new name without extension\n"
                 "• Click /cancel to cancel renaming",
                 reply_markup=InlineKeyboardMarkup([[
                     InlineKeyboardButton("⬅️ 𝗕𝗮𝗰𝗸", callback_data="continue")
                ]])
             )
            
        elif data.startswith("upload_"):
            start_time = time.time()
            status_msg = await callback_query.message.edit_text("🔄 **Processing video...**")
            
            try:
                output_file = await process_video(
                    user['file_path'],
                    user['selected_streams'],
                    len(user['streams'])
                )
                if os.path.exists(output_file):
                    # Extract thumbnail and metadata
                    thumb_data = await extract_thumbnail(output_file)
                    
                    # Get filename
                    if user.get('new_filename'):
                        filename = f"{user['new_filename']}{os.path.splitext(output_file)[1]}"
                        file_path = os.path.join(os.path.dirname(output_file), filename)
                        os.rename(output_file, file_path)
                        output_file = file_path
                    else:
                        filename = os.path.basename(output_file)

                    caption = (
                        f"**{filename}**\n"
                    )
                    
                    async def progress_wrapper(current, total):
                        await progress(current, total, status_msg, start_time, "upload")
                    
                    if data == "upload_video":
                        await client.send_video(
                            callback_query.message.chat.id,
                            output_file,
                            caption=caption,
                            duration=thumb_data['duration'] if thumb_data else None,
                            width=thumb_data['width'] if thumb_data else None,
                            height=thumb_data['height'] if thumb_data else None,
                            thumb=thumb_data['thumb_path'] if thumb_data else None,
                            progress=progress_wrapper
                        )
                    else:
                        await client.send_document(
                            callback_query.message.chat.id,
                            output_file,
                            caption=caption,
                            thumb=thumb_data['thumb_path'] if thumb_data else None,
                            progress=progress_wrapper
                        )
                    await status_msg.edit_text("✅ **Process completed!**")
                    
                    # Cleanup thumbnail
                    if thumb_data and thumb_data['thumb_path']:
                        try:
                            os.remove(thumb_data['thumb_path'])
                        except:
                            pass
                else:
                    raise Exception("Output file not found")
                
            except Exception as e:
                await status_msg.edit_text(f"❌ **Processing error:** {str(e)}")
            finally:
                try:
                    if os.path.exists(user['file_path']):
                        os.remove(user['file_path'])
                    if 'output_file' in locals() and os.path.exists(output_file):
                        os.remove(output_file)
                except Exception as e:
                    print(f"Cleanup error: {str(e)}")
                del user_data[user_id]

        elif data == "back_to_streams":
            buttons = create_stream_buttons(user['streams'], user['selected_streams'])
            await callback_query.message.edit_text(
                "**🎯 𝗦𝗲𝗹𝗲𝗰𝘁 𝘀𝘁𝗿𝗲𝗮𝗺𝘀 𝘁𝗼 𝗿𝗲𝗺𝗼𝘃𝗲:**\n\n"
                "⬜️ = Keep stream\n"
                "☑️ = Remove stream\n\n"
                "_Select all streams you want to remove and press Process._",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
                
                
        elif data == "cancel":
            if os.path.exists(user['file_path']):
                os.remove(user['file_path'])
            del user_data[user_id]
            await callback_query.message.edit_text("❌ **Operation cancelled.**")
            
    except Exception as e:
        await callback_query.message.edit_text(f"❌ **Error:** {str(e)}")
        if user_id in user_data:
            del user_data[user_id]

print("🚀 Bot is starting...")
app.run()
