"""
日志系统 - 支持多级别日志和GUI回调
"""
import logging
import os
from datetime import datetime
from collections import deque
from typing import Callable, Optional


class GuiLogHandler(logging.Handler):
    """将日志转发到GUI的handler"""

    def __init__(self):
        super().__init__()
        self._callbacks: list[Callable] = []
        self._buffer = deque(maxlen=5000)  # 环形缓冲区

    def add_callback(self, callback: Callable):
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def emit(self, record):
        msg = self.format(record)
        self._buffer.append({
            'time': datetime.now().strftime('%H:%M:%S'),
            'level': record.levelname,
            'message': msg,
            'logger': record.name,
        })
        for cb in self._callbacks:
            try:
                cb(msg, record.levelname, record.name)
            except Exception:
                pass

    def get_history(self) -> list:
        return list(self._buffer)


class AppLogger:
    """应用日志管理器"""

    def __init__(self, name='LiveControl', log_dir: str = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

        # 避免重复添加handler
        if not self.logger.handlers:
            # GUI handler
            self.gui_handler = GuiLogHandler()
            fmt = logging.Formatter('%(name)s | %(message)s')
            self.gui_handler.setFormatter(fmt)
            self.gui_handler.setLevel(logging.DEBUG)
            self.logger.addHandler(self.gui_handler)

            # 控制台 handler
            console = logging.StreamHandler()
            console.setLevel(logging.INFO)
            fmt2 = logging.Formatter('[%(asctime)s] %(levelname)s %(name)s | %(message)s',
                                     datefmt='%H:%M:%S')
            console.setFormatter(fmt2)
            self.logger.addHandler(console)

            # 文件 handler
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
                today = datetime.now().strftime('%Y-%m-%d')
                file_handler = logging.FileHandler(
                    os.path.join(log_dir, f'{today}.log'),
                    encoding='utf-8'
                )
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(fmt2)
                self.logger.addHandler(file_handler)

    def get_child(self, name: str):
        """获取子logger"""
        return self.logger.getChild(name)

    def add_gui_callback(self, callback: Callable):
        self.gui_handler.add_callback(callback)

    def remove_gui_callback(self, callback: Callable):
        self.gui_handler.remove_callback(callback)

    def get_history(self):
        return self.gui_handler.get_history()


# 全局日志实例
_logger_instance: Optional[AppLogger] = None


def get_logger(log_dir: str = None) -> AppLogger:
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = AppLogger(log_dir=log_dir)
    return _logger_instance
