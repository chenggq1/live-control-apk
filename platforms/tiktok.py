"""
TikTok直播弹幕/礼物抓取
基于TikTok Web版WebSocket协议 (与抖音类似但使用国际域名)
"""
import threading
import time
import re
import uuid
import json
from typing import Optional

import requests

from platforms.base import BasePlatform
from engine.models import LiveMessage, MessageType, PlatformType
from utils import protobuf_lite as pb
from utils.logger import get_logger
from utils.network import safe_request_get, get_ws_sslopt

logger = get_logger().get_child('TikTok')


# TikTok消息类型常量 (与抖音类似)
TIKTOK_MSG_TYPE = {
    2064: "chat",
    2065: "member",
    2066: "gift",
    2068: "social",
    2069: "like",
    2070: "room_user_seq",
}


class TiktokPlatform(BasePlatform):
    """TikTok直播抓取"""

    PLATFORM = PlatformType.TIKTOK
    DISPLAY_NAME = "TikTok"

    def __init__(self):
        super().__init__()
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.tiktok.com/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        self._cookies = {}
        self._room_id = ""
        self._username = ""

    def connect(self, room_url_or_id: str) -> bool:
        self._room_url = room_url_or_id
        self._running = True
        self._reconnect_count = 0
        self.logger.info(f"正在连接TikTok直播间: {room_url_or_id}")

        try:
            # 提取用户名或房间ID
            room_info = self._extract_room_info(room_url_or_id)
            if not room_info:
                msg = f"无法解析: {room_url_or_id}"
                self.logger.error(msg)
                self._emit_status(False, msg)
                return False

            self._username = room_info.get('username', '')
            self._room_id = room_info.get('room_id', '')

            # 获取房间ID
            if not self._room_id:
                if not self._fetch_room_id():
                    msg = "获取房间ID失败"
                    self.logger.error(msg)
                    self._emit_status(False, msg)
                    return False

            self.logger.info(f"TikTok房间ID: {self._room_id}")

            # 启动WebSocket
            self._thread = threading.Thread(target=self._ws_loop, daemon=True)
            self._thread.start()
            return True

        except Exception as e:
            self.logger.error(f"连接失败: {e}")
            self._emit_status(False, str(e))
            return False

    def _extract_room_info(self, url_or_id: str) -> Optional[dict]:
        """从URL中提取用户名或房间ID"""
        url_or_id = url_or_id.strip()
        info = {}

        # 纯数字 -> 房间ID
        if url_or_id.isdigit():
            info['room_id'] = url_or_id
            return info

        # https://www.tiktok.com/@username/live
        match = re.search(r'tiktok\.com/@([\w.]+)', url_or_id)
        if match:
            info['username'] = match.group(1)
            return info

        # https://www.tiktok.com/@username
        match = re.search(r'@([\w.]+)', url_or_id)
        if match:
            info['username'] = match.group(1)
            return info

        return info if info else None

    def _fetch_room_id(self) -> bool:
        """从TikTok页面获取房间ID"""
        try:
            url = f"https://www.tiktok.com/@{self._username}" if self._username else f"https://www.tiktok.com/"
            resp = safe_request_get(url, headers=self._headers, timeout=15)
            self._cookies = dict(resp.cookies)

            text = resp.text
            # 多种正则提取roomId
            patterns = [
                r'"roomId"\s*:\s*"?(\d+)"?',
                r'"liveRoomId"\s*:\s*"?(\d+)"?',
                r'"room_id"\s*:\s*"?(\d+)"?',
                r'"id"\s*:\s*"?(\d{15,})"?',
            ]
            for pat in patterns:
                match = re.search(pat, text)
                if match:
                    self._room_id = match.group(1)
                    return True

            # 尝试从SIGI_STATE / __UNIVERSAL_DATA JSON中提取
            for json_pattern in [r'<script id="SIGI_STATE"[^>]*>(.*?)</script>',
                                 r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>']:
                match = re.search(json_pattern, text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        # 尝试多种路径
                        room_id = self._deep_search_id(data, 'roomId')
                        if not room_id:
                            room_id = self._deep_search_id(data, 'liveRoomId')
                        if room_id:
                            self._room_id = str(room_id)
                            return True
                    except json.JSONDecodeError:
                        continue

            self.logger.warning("未能从页面提取房间ID")
            return False

        except Exception as e:
            self.logger.error(f"获取房间ID失败: {e}")
            return False

    def _deep_search_id(self, obj, key: str):
        """递归搜索JSON中的指定key"""
        if isinstance(obj, dict):
            if key in obj and obj[key]:
                return obj[key]
            for v in obj.values():
                result = self._deep_search_id(v, key)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._deep_search_id(item, key)
                if result:
                    return result
        return None

    def _build_ws_url(self) -> str:
        """构建WebSocket URL"""
        params = {
            'app_name': 'tiktok_web',
            'version_code': '290400',
            'webcast_sdk_version': '290400',
            'update_version_code': '1',
            'compress': 'gzip',
            'device_platform': 'web',
            'room_id': self._room_id,
            'live_id': '1',
            'did_rule': '3',
            'endpoint': 'live_h265',
            'identity': 'audience',
            'im_path': '/webcast/im/fetch/',
            'support_wrds': '1',
            'host': 'https://webcast.tiktok.com',
            'aid': '1988',
            'device_id': str(uuid.uuid4().int)[:19],
            'response_format': 'json',
        }
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        return f"wss://webcast.tiktok.com/webcast/im/push/v2/?{query}"

    def _build_register_packet(self) -> bytes:
        """构建注册数据包"""
        inner = pb.encode_varint_field(1, int(self._room_id))
        register = (
            pb.encode_varint_field(1, 1) +
            pb.encode_length_delimited(2, inner) +
            pb.encode_varint_field(3, 1)
        )
        return pb.build_pushframe(register, compression=1, seq=1)

    def _ws_loop(self):
        """WebSocket连接主循环"""
        import websocket

        while self._running:
            try:
                ws_url = self._build_ws_url()
                self.logger.info("连接TikTok WebSocket...")

                ws_headers = []
                for k, v in self._headers.items():
                    ws_headers.append(f"{k}: {v}")

                self._ws = websocket.WebSocketApp(
                    ws_url,
                    header=ws_headers,
                    cookie='; '.join(f'{k}={v}' for k, v in self._cookies.items()),
                    on_open=self._on_ws_open,
                    on_message=self._on_ws_message,
                    on_error=self._on_ws_error,
                    on_close=self._on_ws_close,
                )

                self._ws.run_forever(
                    ping_interval=10,
                    ping_timeout=5,
                    suppress_origin=True,
                    sslopt=get_ws_sslopt(),
                )

            except Exception as e:
                self.logger.error(f"WebSocket异常: {e}")

            if not self._running:
                break

            self._reconnect_count += 1
            if self._reconnect_count > self._max_reconnect:
                self.logger.error("超过最大重连次数")
                self._emit_status(False, "超过最大重连次数")
                break

            self.logger.info(f"{self._reconnect_interval}秒后重连... ({self._reconnect_count}/{self._max_reconnect})")
            for _ in range(self._reconnect_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _on_ws_open(self, ws):
        self.logger.info("TikTok WebSocket连接成功")
        self._reconnect_count = 0
        self._emit_status(True, "TikTok直播间已连接")

        try:
            register = self._build_register_packet()
            ws.send(register, opcode=0x2)
            self.logger.info("已发送注册包")
        except Exception as e:
            self.logger.error(f"发送注册包失败: {e}")

    def _on_ws_message(self, ws, message):
        if not isinstance(message, (bytes, bytearray)):
            return
        try:
            self._parse_pushframe(message)
        except Exception as e:
            self.logger.debug(f"消息解析异常: {e}")

    def _parse_pushframe(self, data: bytes):
        """解析PushFrame - 与抖音相同协议"""
        frame = pb.parse_fields(data)
        payload = pb.get_field(frame, 4)
        if not payload:
            return

        compression = pb.get_field(frame, 2, 1)
        if compression == 2:
            payload = pb.decompress_gzip(payload)

        resp = pb.parse_fields(payload)
        messages = pb.get_all_fields(resp, 1)
        for msg_data in messages:
            self._parse_message(msg_data)

    def _parse_message(self, msg_data: bytes):
        """解析单条消息 - 与抖音格式一致"""
        msg_fields = pb.parse_fields(msg_data)
        msg_type_raw = pb.get_field(msg_fields, 4, 0)
        msg_payload = pb.get_field(msg_fields, 2)

        if not msg_payload:
            return

        msg_type_str = TIKTOK_MSG_TYPE.get(msg_type_raw)
        if not msg_type_str:
            return

        self._emit_raw({
            'platform': 'tiktok',
            'msg_type': msg_type_raw,
            'type_str': msg_type_str,
        })

        if msg_type_str == "chat":
            self._parse_chat(msg_payload)
        elif msg_type_str == "gift":
            self._parse_gift(msg_payload)
        elif msg_type_str == "like":
            self._parse_like(msg_payload)
        elif msg_type_str == "member":
            self._parse_member(msg_payload)
        elif msg_type_str == "social":
            self._parse_social(msg_payload)

    def _parse_chat(self, data: bytes):
        fields = pb.parse_fields(data)
        user_data = pb.get_field(fields, 2, b'')
        user_fields = pb.parse_fields(user_data) if user_data else {}
        user_id = str(pb.get_field(user_fields, 1, 0))
        nickname = pb.decode_string(pb.get_field(user_fields, 2, b''))
        content = pb.decode_string(pb.get_field(fields, 3, b''))

        if content:
            msg = self._create_message(
                MessageType.COMMENT,
                user_id=user_id, user_name=nickname, content=content,
            )
            self.logger.debug(f"[评论] {nickname}: {content}")
            self._emit_message(msg)

    def _parse_gift(self, data: bytes):
        fields = pb.parse_fields(data)
        gift_id = str(pb.get_field(fields, 1, 0))
        repeat_count = pb.get_field(fields, 4, 1)
        group_count = pb.get_field(fields, 3, 0)

        user_data = pb.get_field(fields, 7, b'')
        user_fields = pb.parse_fields(user_data) if user_data else {}
        user_id = str(pb.get_field(user_fields, 1, 0))
        nickname = pb.decode_string(pb.get_field(user_fields, 2, b''))

        gift_data = pb.get_field(fields, 15, b'')
        gift_name = ""
        gift_value = 0
        if gift_data:
            gift_fields = pb.parse_fields(gift_data)
            gift_name = pb.decode_string(pb.get_field(gift_fields, 16, b''))
            gift_value = pb.get_field(gift_fields, 20, 0)

        msg = self._create_message(
            MessageType.GIFT,
            user_id=user_id, user_name=nickname,
            content=gift_name or f"Gift{gift_id}",
            gift_id=gift_id,
            gift_count=max(repeat_count, group_count, 1),
            gift_value=gift_value,
        )
        self.logger.info(f"[Gift] {nickname} sent {gift_name} x{msg.gift_count}")
        self._emit_message(msg)

    def _parse_like(self, data: bytes):
        fields = pb.parse_fields(data)
        user_data = pb.get_field(fields, 5, b'')
        user_fields = pb.parse_fields(user_data) if user_data else {}
        user_id = str(pb.get_field(user_fields, 1, 0))
        nickname = pb.decode_string(pb.get_field(user_fields, 2, b''))
        count = pb.get_field(fields, 1, 1)

        msg = self._create_message(
            MessageType.LIKE, user_id=user_id, user_name=nickname,
            content="like", gift_count=count,
        )
        self._emit_message(msg)

    def _parse_member(self, data: bytes):
        fields = pb.parse_fields(data)
        user_data = pb.get_field(fields, 2, b'')
        user_fields = pb.parse_fields(user_data) if user_data else {}
        user_id = str(pb.get_field(user_fields, 1, 0))
        nickname = pb.decode_string(pb.get_field(user_fields, 2, b''))

        msg = self._create_message(
            MessageType.ENTER, user_id=user_id, user_name=nickname,
            content="entered the room",
        )
        self._emit_message(msg)

    def _parse_social(self, data: bytes):
        fields = pb.parse_fields(data)
        user_data = pb.get_field(fields, 2, b'')
        user_fields = pb.parse_fields(user_data) if user_data else {}
        user_id = str(pb.get_field(user_fields, 1, 0))
        nickname = pb.decode_string(pb.get_field(user_fields, 2, b''))

        msg = self._create_message(
            MessageType.FOLLOW, user_id=user_id, user_name=nickname,
            content="followed the streamer",
        )
        self._emit_message(msg)

    def _on_ws_error(self, ws, error):
        self.logger.error(f"WebSocket错误: {error}")

    def _on_ws_close(self, ws, close_status_code, close_msg):
        self.logger.info(f"WebSocket关闭: {close_status_code} {close_msg}")
        self._emit_status(False, "连接已断开")

    def disconnect(self):
        self._running = False
        self.logger.info("正在断开TikTok直播间...")
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._connected = False
        self._emit_status(False, "已断开")
