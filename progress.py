import time
import asyncio
from typing import Union
from pyrogram.types import Message

class ProgressHandler:
    def __init__(self):
        self._last_update_time = 0
        self._min_update_interval = 2  # seconds

    async def update_progress(
        self,
        current: int,
        total: int,
        message: Message,
        start_time: float,
        action_text: str = "Processing"  # Changed parameter name to match usage
    ) -> None:
        """
        Update progress message with current status
        
        Args:
            current (int): Current progress value
            total (int): Total expected value
            message (Message): Message object to edit
            start_time (float): When the operation started
            action_text (str, optional): Action text to display. Defaults to "Processing"
        """
        try:
            current_time = time.time()
            should_update = (
                (current_time - self._last_update_time >= self._min_update_interval) or 
                (current == total)
            )
            
            if not should_update:
                return
                
            self._last_update_time = current_time
            
            # Calculate progress
            percent = (current * 100) / total if total > 0 else 0
            bar = self._create_progress_bar(current, total)
            speed = self._calculate_speed(current, start_time)
            elapsed = self._format_time(int(current_time - start_time))
            
            # Format sizes
            current_size = self._format_size(current)
            total_size = self._format_size(total)
            
            # Create status message
            status = (
                f"⚙️ {action_text}...\n\n"
                f"┌ **Progress:** {current_size} / {total_size}\n"
                f"├ **Speed:** {speed}/s\n"
                f"├ **Time:** {elapsed}\n"
                f"└ {bar} {percent:.1f}%"
            )
            
            await message.edit_text(status)
            
        except Exception as e:
            print(f"Progress update error: {str(e)}")
            
    @staticmethod
    def _create_progress_bar(current: int, total: int) -> str:
        if total == 0:
            return "─" * 10
        progress = min(current / total, 1)
        filled_len = int(progress * 10)
        return "━" * filled_len + "─" * (10 - filled_len)

    @staticmethod
    def _calculate_speed(current: int, start_time: float) -> str:
        elapsed_time = max(time.time() - start_time, 1)
        speed = current / elapsed_time
        return ProgressHandler._format_size(int(speed))

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f}{unit}"
            size /= 1024
        return f"{size:.2f}TB"

    @staticmethod
    def _format_time(seconds: int) -> str:
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
