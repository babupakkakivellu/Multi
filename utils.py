import os
import json
import asyncio
import subprocess
import time
import re
from typing import Dict, List, Set, Callable, Optional

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
        elif action == "compress":
            status = "🔄 𝗖𝗼𝗺𝗽𝗿𝗲𝘀𝘀𝗶𝗻𝗴..."
        else:
            status = "📤 𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴..."

        await message.edit_text(
            f"{status}\n\n"
            f"┌ **Progress:** {current_mb} / {total_mb}\n"
            f"├ **Speed:** {speed}/s\n"
            f"├ **Time:** {elapsed_time}\n"
            f"└ {bar} {percent:.1f}%"
        )
    except Exception as e:
        print(f"Progress update error: {str(e)}")

async def get_video_duration(file_path: str) -> float:
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        return float(stdout.decode().strip())
    except Exception as e:
        print(f"Error getting duration: {str(e)}")
        return 0

def get_streamsinfo(file_path: str) -> List[Dict]:
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return json.loads(result.stdout)['streams']
    except Exception as e:
        print(f"Error getting streams info: {str(e)}")
        return []

def get_stream_info(stream: Dict) -> str:
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
        await process.communicate()
        
        if not os.path.exists(output_file):
            raise Exception("Output file was not created")
            
        return output_file
        
    except Exception as e:
        raise Exception(f"Processing failed: {str(e)}")

async def compress_video(
    input_file: str,
    resolution: str,
    crf: int,
    codec: str,
    progress_callback: Optional[Callable] = None
) -> str:
    try:
        duration = await get_video_duration(input_file)
        
        settings = {
            "2160": {"scale": "3840:2160", "preset": "slow"},
            "1080": {"scale": "1920:1080", "preset": "slow"},
            "720": {"scale": "1280:720", "preset": "medium"},
            "480": {"scale": "854:480", "preset": "medium"}
        }
        
        setting = settings[resolution]
        output_file = f"compressed_{resolution}p_{os.path.basename(input_file)}"
        
        cmd = [
            'ffmpeg', '-i', input_file,
            '-c:v', codec,
            '-preset', setting['preset'],
            '-crf', str(crf),
            '-vf', f"scale={setting['scale']}:force_original_aspect_ratio=decrease,pad={setting['scale']}:-1:-1:color=black",
            '-c:a', 'copy',  # Copy audio without re-encoding
            '-movflags', '+faststart'
        ]
        
        if codec == 'libx265':
            cmd.extend(['-x265-params', 'log-level=error'])
            cmd.extend(['-pix_fmt', 'yuv420p10le'])
        else:
            cmd.extend(['-pix_fmt', 'yuv420p'])
            
        cmd.append(output_file)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        if progress_callback:
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='ignore')
                time_match = re.search(r"time=(\d+:\d+:\d+.\d+)", line_str)
                if time_match:
                    time_str = time_match.group(1)
                    h, m, s = time_str.split(':')
                    current = float(h) * 3600 + float(m) * 60 + float(s)
                    await progress_callback(current, duration)

        await process.communicate()

        if not os.path.exists(output_file):
            raise Exception("Output file was not created")

        return output_file

    except Exception as e:
        raise Exception(f"Compression failed: {str(e)}")
