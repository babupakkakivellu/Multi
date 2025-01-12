import time
import asyncio
from typing import Callable, Any

class ProgressHandler:
    def __init__(self):
        self._last_update_time = 0
        self._min_update_interval = 2  # seconds

    async def __call__(self, current: int, total: int, 
                      message_handler: Callable[[str], Any], 
                      start_time: float,
                      action: str = "Processing") -> None:
        try:
            current_time = time.time()
            if (current_time - self._last_update_time >= self._min_update_interval) or (current == total):
                self._last_update_time = current_time
                
                # Calculate progress
                percent = (current * 100) / total
                bar = self._create_progress_bar(current, total)
                speed = self._calculate_speed(current, start_time)
                elapsed = self._format_time(int(current_time - start_time))
                
                # Format sizes
                current_size = self._format_size(current)
                total_size = self._format_size(total)
                
                # Create status message
                status = (
                    f"⚙️ {action}...\n\n"
                    f"┌ **Progress:** {current_size} / {total_size}\n"
                    f"├ **Speed:** {speed}/s\n"
                    f"├ **Time:** {elapsed}\n"
                    f"└ {bar} {percent:.1f}%"
                )
                
                await message_handler(status)
                
                # Small delay to prevent excessive CPU usage
                await asyncio.sleep(0.1)
                
        except Exception as e:
            print(f"Progress update error: {str(e)}")

    @staticmethod
    def _create_progress_bar(current: int, total: int) -> str:
        progress = min(current / total, 1)
        filled_len = int(progress * 10)
        return "━" * filled_len + "─" * (10 - filled_len)

    @staticmethod
    def _calculate_speed(current: int, start_time: float) -> str:
        speed = current / max(time.time() - start_time, 1)
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
