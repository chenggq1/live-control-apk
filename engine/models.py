"""
数据模型 - 定义直播消息、指令规则等核心数据结构
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time
import uuid


class MessageType(Enum):
    """直播消息类型"""
    COMMENT = "comment"      # 评论
    GIFT = "gift"            # 礼物
    LIKE = "like"            # 点赞
    FOLLOW = "follow"        # 关注
    ENTER = "enter"          # 进入直播间
    SYSTEM = "system"        # 系统消息
    UNKNOWN = "unknown"


class TriggerType(Enum):
    """触发类型"""
    EXACT = "exact"          # 精确匹配
    CONTAINS = "contains"    # 包含匹配
    REGEX = "regex"          # 正则匹配
    GIFT_NAME = "gift_name"  # 礼物名称匹配
    GIFT_COUNT = "gift_count"  # 礼物数量触发
    LIKE_COUNT = "like_count"  # 点赞数触发


class PlatformType(Enum):
    """直播平台"""
    DOUYIN = "douyin"
    KUAISHOU = "kuaishou"
    XIAOHONGSHU = "xiaohongshu"
    TIKTOK = "tiktok"

    @property
    def display_name(self) -> str:
        names = {
            "douyin": "抖音",
            "kuaishou": "快手",
            "xiaohongshu": "小红书",
            "tiktok": "TikTok",
        }
        return names.get(self.value, self.value)


@dataclass
class LiveMessage:
    """直播消息数据结构"""
    msg_type: MessageType
    platform: PlatformType
    user_id: str = ""
    user_name: str = ""
    content: str = ""          # 评论内容或礼物名称
    gift_id: str = ""          # 礼物ID
    gift_count: int = 0        # 礼物数量
    gift_value: int = 0        # 礼物价值(钻石/音浪)
    raw_data: dict = field(default_factory=dict)  # 原始数据
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "msg_type": self.msg_type.value,
            "platform": self.platform.value,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "content": self.content,
            "gift_id": self.gift_id,
            "gift_count": self.gift_count,
            "gift_value": self.gift_value,
            "timestamp": self.timestamp,
        }

    @property
    def display_text(self) -> str:
        if self.msg_type == MessageType.COMMENT:
            return f"[评论] {self.user_name}: {self.content}"
        elif self.msg_type == MessageType.GIFT:
            return f"[礼物] {self.user_name} 送出 {self.content} x{self.gift_count}"
        elif self.msg_type == MessageType.LIKE:
            return f"[点赞] {self.user_name} 点了赞"
        elif self.msg_type == MessageType.FOLLOW:
            return f"[关注] {self.user_name} 关注了主播"
        elif self.msg_type == MessageType.ENTER:
            return f"[进场] {self.user_name} 进入直播间"
        elif self.msg_type == MessageType.SYSTEM:
            return f"[系统] {self.content}"
        return f"[未知] {self.user_name}: {self.content}"


@dataclass
class CommandRule:
    """指令规则 - 定义什么消息触发什么蓝牙动作"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""                          # 规则名称
    enabled: bool = True                     # 是否启用
    platform: str = "all"                    # 适用平台 (all/douyin/kuaishou/...)
    msg_type: str = "comment"               # 消息类型 (comment/gift/like/follow/enter)
    trigger_type: str = "exact"             # 触发类型
    trigger_value: str = ""                 # 触发值 (评论内容/礼物名称等)
    min_count: int = 1                      # 最小数量(礼物数量/点赞数)
    bluetooth_channel: int = 1              # 蓝牙通道(继电器编号)
    bluetooth_command: str = ""             # 蓝牙指令(hex字符串)
    action_type: str = "send_once"          # 动作类型: send_once/pulse/toggle
    pulse_duration: int = 500               # 脉冲持续时间(ms), 仅pulse模式
    cooldown: int = 0                        # 冷却时间(ms)
    last_triggered: float = 0.0             # 上次触发时间

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "platform": self.platform,
            "msg_type": self.msg_type,
            "trigger_type": self.trigger_type,
            "trigger_value": self.trigger_value,
            "min_count": self.min_count,
            "bluetooth_channel": self.bluetooth_channel,
            "bluetooth_command": self.bluetooth_command,
            "action_type": self.action_type,
            "pulse_duration": self.pulse_duration,
            "cooldown": self.cooldown,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'CommandRule':
        return cls(
            id=d.get("id", uuid.uuid4().hex[:8]),
            name=d.get("name", ""),
            enabled=d.get("enabled", True),
            platform=d.get("platform", "all"),
            msg_type=d.get("msg_type", "comment"),
            trigger_type=d.get("trigger_type", "exact"),
            trigger_value=d.get("trigger_value", ""),
            min_count=d.get("min_count", 1),
            bluetooth_channel=d.get("bluetooth_channel", 1),
            bluetooth_command=d.get("bluetooth_command", ""),
            action_type=d.get("action_type", "send_once"),
            pulse_duration=d.get("pulse_duration", 500),
            cooldown=d.get("cooldown", 0),
        )

    def matches(self, msg: LiveMessage) -> bool:
        """检查消息是否匹配此规则"""
        if not self.enabled:
            return False
        # 平台检查
        if self.platform != "all" and self.platform != msg.platform.value:
            return False
        # 消息类型检查
        if self.msg_type != msg.msg_type.value:
            return False
        # 冷却检查
        if self.cooldown > 0:
            elapsed = (time.time() - self.last_triggered) * 1000
            if elapsed < self.cooldown:
                return False
        # 数量检查
        if self.msg_type == "gift" and msg.gift_count < self.min_count:
            return False
        # 触发值匹配
        if not self.trigger_value and self.trigger_type != "like_count":
            return True  # 无触发值 = 匹配所有
        if self.trigger_type == "exact":
            return msg.content == self.trigger_value
        elif self.trigger_type == "contains":
            return self.trigger_value in msg.content
        elif self.trigger_type == "regex":
            import re
            try:
                return bool(re.search(self.trigger_value, msg.content))
            except re.error:
                return False
        elif self.trigger_type == "gift_name":
            return msg.content == self.trigger_value
        return False


@dataclass
class BluetoothConfig:
    """蓝牙配置"""
    connection_type: str = "serial"  # serial / ble
    port: str = ""                   # 串口端口 (COM3, /dev/ttyHC-05等)
    baudrate: int = 9600
    ble_address: str = ""            # BLE设备地址
    ble_service_uuid: str = ""
    ble_char_uuid: str = ""
    default_on_cmd: str = "A00101A2"   # 默认开启指令(hex)
    default_off_cmd: str = "A00100A1"  # 默认关闭指令(hex)
    channel_count: int = 4              # 继电器通道数

    def to_dict(self) -> dict:
        return {
            "connection_type": self.connection_type,
            "port": self.port,
            "baudrate": self.baudrate,
            "ble_address": self.ble_address,
            "ble_service_uuid": self.ble_service_uuid,
            "ble_char_uuid": self.ble_char_uuid,
            "default_on_cmd": self.default_on_cmd,
            "default_off_cmd": self.default_off_cmd,
            "channel_count": self.channel_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'BluetoothConfig':
        defaults = cls()
        return cls(
            connection_type=d.get("connection_type", defaults.connection_type),
            port=d.get("port", defaults.port),
            baudrate=d.get("baudrate", defaults.baudrate),
            ble_address=d.get("ble_address", defaults.ble_address),
            ble_service_uuid=d.get("ble_service_uuid", defaults.ble_service_uuid),
            ble_char_uuid=d.get("ble_char_uuid", defaults.ble_char_uuid),
            default_on_cmd=d.get("default_on_cmd", defaults.default_on_cmd),
            default_off_cmd=d.get("default_off_cmd", defaults.default_off_cmd),
            channel_count=d.get("channel_count", defaults.channel_count),
        )
