"""
直播平台抓取基类 - 定义统一接口
"""
import threading
import time
from abc import ABC, abstractmethod
from typing import Callable, Optional
from engine.models import LiveMessage, MessageType, PlatformType
from utils.logger import get_logger


class BasePlatform(ABC):
    """直播平台抓取基类"""

    PLATFORM: PlatformType = PlatformType.DOUYIN
    DISPLAY_NAME: str = ""

    def __init__(self):
        self.logger = get_logger().get_child(self.__class__.__name__)
        self._ws = None
        self._connected: bool = False
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._room_id: str = ""
        self._room_url: str = ""
        self._reconnect_interval: int = 5  # 重连间隔(秒)
        self._max_reconnect: int = 10       # 最大重连次数
        self._reconnect_count: int = 0

        # 回调
        self._message_callbacks: list[Callable[[LiveMessage], None]] = []
        self._status_callbacks: list[Callable[[bool, str], None]] = []
        self._raw_callbacks: list[Callable[[dict], None]] = []  # 原始数据回调(调试用)

    @property
    def is_connected(self) -> bool:
        return self._connected

    def add_message_callback(self, callback: Callable[[LiveMessage], None]):
        self._message_callbacks.append(callback)

    def add_status_callback(self, callback: Callable[[bool, str], None]):
        self._status_callbacks.append(callback)

    def add_raw_callback(self, callback: Callable[[dict], None]):
        self._raw_callbacks.append(callback)

    def _emit_message(self, msg: LiveMessage):
        """通知所有消息回调"""
        for cb in self._message_callbacks:
            try:
                cb(msg)
            except Exception as e:
                self.logger.error(f"消息回调异常: {e}")

    def _emit_status(self, connected: bool, msg: str = ""):
        """通知所有状态回调"""
        self._connected = connected
        for cb in self._status_callbacks:
            try:
                cb(connected, msg)
            except Exception as e:
                self.logger.error(f"状态回调异常: {e}")

    def _emit_raw(self, data: dict):
        """通知原始数据回调"""
        for cb in self._raw_callbacks:
            try:
                cb(data)
            except Exception:
                pass

    @abstractmethod
    def connect(self, room_url_or_id: str) -> bool:
        """连接直播间"""
        pass

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    def _create_message(self, msg_type: MessageType, **kwargs) -> LiveMessage:
        """创建平台消息"""
        return LiveMessage(
            msg_type=msg_type,
            platform=self.PLATFORM,
            **kwargs
        )

    def _stop_flag(self):
        """检查是否应该停止"""
        return not self._running
