from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import os
import time
from config import Config
from utils import (
    compress_video, get_streamsinfo, get_stream_info, 
    process_video, progress
)

# Bot initialization
app = Client(
    "video_processor_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

# Store user data
user_data = {}

def create_initial_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✂️ Remove Streams", callback_data="show_streams")],
        [InlineKeyboardButton("🗜️ Compress Video", callback_data="show_compress")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def create_stream_buttons(streams, selected_streams):
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
    
    for _, (header, group_streams) in stream_groups.items():
        if group_streams:
            buttons.append([InlineKeyboardButton(f"═══ {header} ═══", callback_data="header")])
            for stream in group_streams:
                buttons.append([InlineKeyboardButton(
                    f"{stream['prefix']} {stream['info']}",
                    callback_data=f"stream_{stream['index']}"
                )])
    
    buttons.extend([
        [InlineKeyboardButton("✅ Process", callback_data="process")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")]
    ])
    return InlineKeyboardMarkup(buttons)

def create_compression_menu(settings):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("2160p (4K)", callback_data="res_2160"),
            InlineKeyboardButton("1080p", callback_data="res_1080")
        ],
        [
            InlineKeyboardButton("720p", callback_data="res_720"),
            InlineKeyboardButton("480p", callback_data="res_480")
        ],
        [
            InlineKeyboardButton("H.264", callback_data="codec_libx264"),
            InlineKeyboardButton("H.265", callback_data="codec_libx265")
        ],
        [
            InlineKeyboardButton("CRF 18", callback_data="crf_18"),
            InlineKeyboardButton("CRF 23", callback_data="crf_23"),
            InlineKeyboardButton("CRF 28", callback_data="crf_28")
        ],
        [InlineKeyboardButton("✅ Start Compression", callback_data="start_compress")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")]
    ])

@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text(Config.START_MSG)

@app.on_message(filters.video | filters.document)
async def handle_video(client, message):
    try:
        start_time = time.time()
        status_msg = await message.reply_text("⚡ 𝗜𝗻𝗶𝘁𝗶𝗮𝗹𝗶𝘇𝗶𝗻𝗴...")
        
        file_path = await message.download(
            progress=lambda current, total: progress(
                current, total, status_msg, start_time, "download"
            )
        )
        
        user_data[message.from_user.id] = {
            'file_path': file_path,
            'streams': get_streamsinfo(file_path),
            'selected_streams': set(),
            'compression_settings': {
                'resolution': '720',
                'codec': 'libx264',
                'crf': 23
            }
        }
        
        await status_msg.edit_text(
            Config.CHOOSE_OPERATION_MSG,
            reply_markup=create_initial_menu()
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error:** {str(e)}")
        if message.from_user.id in user_data:
            del user_data[message.from_user.id]

@app.on_callback_query()
async def handle_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if user_id not in user_data and data not in ["cancel", "back_to_menu"]:
        await callback_query.answer("Session expired. Please send the video again.", show_alert=True)
        return
    
    try:
        if data == "show_streams":
            await callback_query.message.edit_text(
                Config.STREAM_SELECTION_MSG,
                reply_markup=create_stream_buttons(
                    user_data[user_id]['streams'],
                    user_data[user_id]['selected_streams']
                )
            )
            
        elif data == "show_compress":
            settings = user_data[user_id]['compression_settings']
            await callback_query.message.edit_text(
                Config.COMPRESSION_HELP_MSG.format(
                    resolution=settings['resolution'],
                    codec="H.264" if settings['codec'] == 'libx264' else "H.265",
                    crf=settings['crf']
                ),
                reply_markup=create_compression_menu(settings)
            )
            
        elif data.startswith("stream_"):
            stream_index = int(data.split("_")[1])
            if stream_index in user_data[user_id]['selected_streams']:
                user_data[user_id]['selected_streams'].remove(stream_index)
            else:
                user_data[user_id]['selected_streams'].add(stream_index)
                
            await callback_query.message.edit_reply_markup(
                reply_markup=create_stream_buttons(
                    user_data[user_id]['streams'],
                    user_data[user_id]['selected_streams']
                )
            )
            
        elif data.startswith("res_"):
            user_data[user_id]['compression_settings']['resolution'] = data.split("_")[1]
            await callback_query.answer("Resolution updated!")
            await callback_query.message.edit_reply_markup(
                reply_markup=create_compression_menu(user_data[user_id]['compression_settings'])
            )
            
        elif data.startswith("codec_"):
            user_data[user_id]['compression_settings']['codec'] = data.split("_")[1]
            await callback_query.answer("Codec updated!")
            await callback_query.message.edit_reply_markup(
                reply_markup=create_compression_menu(user_data[user_id]['compression_settings'])
            )
            
        elif data.startswith("crf_"):
            user_data[user_id]['compression_settings']['crf'] = int(data.split("_")[1])
            await callback_query.answer("CRF value updated!")
            await callback_query.message.edit_reply_markup(
                reply_markup=create_compression_menu(user_data[user_id]['compression_settings'])
            )
            
        elif data == "process":
            start_time = time.time()
            status_msg = await callback_query.message.edit_text("🔄 Processing video...")
            
            output_file = await process_video(
                user_data[user_id]['file_path'],
                user_data[user_id]['selected_streams'],
                len(user_data[user_id]['streams'])
            )
            
            await client.send_video(
                callback_query.message.chat.id,
                output_file,
                caption="✅ Processed video",
                progress=lambda current, total: progress(
                    current, total, status_msg, start_time, "upload"
                )
            )
            
            os.remove(output_file)
            os.remove(user_data[user_id]['file_path'])
            del user_data[user_id]
            await status_msg.edit_text("✅ Process completed!")
            
        elif data == "start_compress":
            start_time = time.time()
            status_msg = await callback_query.message.edit_text("🔄 Compressing video...")
            
            settings = user_data[user_id]['compression_settings']
            output_file = await compress_video(
                user_data[user_id]['file_path'],
                settings['resolution'],
                settings['crf'],
                settings['codec'],
                progress_callback=lambda current, total: progress(
                    current, total, status_msg, start_time, "compress"
                )
            )
            
            await client.send_video(
                callback_query.message.chat.id,
                output_file,
                caption=f"✅ Compressed video ({settings['resolution']}p, "
                        f"{'H.264' if settings['codec'] == 'libx264' else 'H.265'}, "
                        f"CRF {settings['crf']})",
                progress=lambda current, total: progress(
                    current, total, status_msg, start_time, "upload"
                )
            )
            
            os.remove(output_file)
            os.remove(user_data[user_id]['file_path'])
            del user_data[user_id]
            await status_msg.edit_text("✅ Compression completed!")
            
        elif data == "back_to_menu":
            await callback_query.message.edit_text(
                Config.CHOOSE_OPERATION_MSG,
                reply_markup=create_initial_menu()
            )
            
        elif data == "cancel":
            if user_id in user_data:
                if os.path.exists(user_data[user_id]['file_path']):
                    os.remove(user_data[user_id]['file_path'])
                del user_data[user_id]
            await callback_query.message.edit_text("❌ Operation cancelled.")
            
    except Exception as e:
        await callback_query.message.edit_text(f"❌ **Error:** {str(e)}")
        if user_id in user_data:
            del user_data[user_id]

print("🚀 Bot is starting...")
app.run()
