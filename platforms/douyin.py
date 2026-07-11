"""
抖音直播弹幕/礼物抓取
基于抖音Web版WebSocket协议
"""
import threading
import time
import re
import json
import uuid
import gzip
from typing import Optional

import requests

from platforms.base import BasePlatform
from engine.models import LiveMessage, MessageType, PlatformType
from utils import protobuf_lite as pb
from utils.logger import get_logger
from utils.network import safe_request_get, get_ws_sslopt

logger = get_logger().get_child('Douyin')


# 抖音消息类型常量
DOUYIN_MSG_TYPE = {
    2064: "chat",        # 评论
    2065: "member",      # 进场
    2066: "gift",        # 礼物
    2068: "social",      # 关注
    2069: "like",        # 点赞
    2070: "room_user_seq",  # 观众数
}


class DouyinPlatform(BasePlatform):
    """抖音直播抓取"""

    PLATFORM = PlatformType.DOUYIN
    DISPLAY_NAME = "抖音"

    def __init__(self):
        super().__init__()
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://live.douyin.com/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        self._cookies = {}
        self._ttwid = ""
        self._room_id_str = ""
        self._user_id = ""

    def connect(self, room_url_or_id: str) -> bool:
        """连接抖音直播间"""
        self._room_url = room_url_or_id
        self._running = True
        self._reconnect_count = 0
        self.logger.info(f"正在连接抖音直播间: {room_url_or_id}")

        try:
            # 获取房间ID
            room_id = self._extract_room_id(room_url_or_id)
            if not room_id:
                msg = f"无法解析房间ID: {room_url_or_id}"
                self.logger.error(msg)
                self._emit_status(False, msg)
                return False
            self._room_id_str = room_id
            self.logger.info(f"房间ID: {room_id}")

            # 获取页面和cookie
            if not self._fetch_room_info(room_id):
                msg = "获取房间信息失败"
                self.logger.error(msg)
                self._emit_status(False, msg)
                return False

            # 启动WebSocket连接线程
            self._thread = threading.Thread(target=self._ws_loop, daemon=True)
            self._thread.start()
            return True

        except Exception as e:
            self.logger.error(f"连接失败: {e}")
            self._emit_status(False, str(e))
            return False

    def _extract_room_id(self, url_or_id: str) -> str:
        """从URL或ID中提取房间ID"""
        url_or_id = url_or_id.strip()
        # 纯数字
        if url_or_id.isdigit():
            return url_or_id
        # URL: https://live.douyin.com/123456789
        match = re.search(r'live\.douyin\.com/(\d+)', url_or_id)
        if match:
            return match.group(1)
        # URL: https://live.douyin.com/{user_id}
        match = re.search(r'live\.douyin\.com/([a-zA-Z0-9_-]+)', url_or_id)
        if match:
            return match.group(1)
        return url_or_id

    def _fetch_room_info(self, room_id: str) -> bool:
        """获取房间信息和cookies"""
        try:
            url = f"https://live.douyin.com/{room_id}"
            resp = safe_request_get(url, headers=self._headers, timeout=15, allow_redirects=True)
            self._cookies = dict(resp.cookies)

            # 提取ttwid
            ttwid = resp.cookies.get('ttwid', '')
            if ttwid:
                self._ttwid = ttwid
                self._cookies['ttwid'] = ttwid

            # 从页面提取roomId（数字）
            text = resp.text
            # 尝试多种正则
            patterns = [
                r'"roomId"\s*:\s*"(\d+)"',
                r'"roomId"\s*:\s*(\d+)',
                r'roomId["\']?\s*[:=]\s*["\']?(\d{5,})',
                r'"room_id_str"\s*:\s*"(\d+)"',
            ]
            for pat in patterns:
                match = re.search(pat, text)
                if match:
                    self._room_id_str = match.group(1)
                    self.logger.info(f"提取到数字房间ID: {self._room_id_str}")
                    break

            # 提取用户ID
            user_match = re.search(r'"userIdStr"\s*:\s*"(\d+)"', text)
            if user_match:
                self._user_id = user_match.group(1)

            # 如果没有ttwid，生成一个
            if not self._ttwid:
                self._ttwid = self._generate_ttwid()
                self._cookies['ttwid'] = self._ttwid

            self.logger.info(f"房间信息获取成功, cookies数量: {len(self._cookies)}")
            return True

        except Exception as e:
            self.logger.error(f"获取房间信息失败: {e}")
            return False

    def _generate_ttwid(self) -> str:
        """生成ttwid cookie"""
        import base64
        import os
        data = os.urandom(32)
        return base64.b64encode(data).decode()

    def _build_ws_url(self) -> str:
        """构建WebSocket URL"""
        params = {
            'app_name': 'douyin_web',
            'version_code': '240400',
            'webcast_sdk_version': '240400',
            'update_version_code': '1',
            'compress': 'gzip',
            'device_platform': 'web',
            'cookie': f"ttwid={self._ttwid}",
            'room_id': self._room_id_str,
            'user_id': self._user_id,
            'live_id': '1',
            'did_rule': '3',
            'endpoint': 'live_h265',
            'identity': 'audience',
            'im_path': '/webcast/im/fetch/',
            'support_wrds': '1',
            'host': 'https://live.douyin.com',
            'aid': '6383',
            'device_id': str(uuid.uuid4().int)[:19],
            'response_format': 'json',
        }
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        return f"wss://webcast5-normal-c-hl.amemv.com/webcast/im/push/v2/?{query}"

    def _build_register_packet(self) -> bytes:
        """构建注册数据包"""
        # 抖音WebSocket注册包 - protobuf格式
        # 内层: RoomId message
        inner = (
            pb.encode_varint_field(1, int(self._room_id_str)) if self._room_id_str.isdigit()
            else pb.encode_length_delimited(1, self._room_id_str.encode())
        )

        # register包: method=1, payload=inner, msg_type=1
        register = (
            pb.encode_varint_field(1, 1) +           # method
            pb.encode_length_delimited(2, inner) +    # payload
            pb.encode_varint_field(3, 1)              # msg_type
        )

        # PushFrame包装
        return pb.build_pushframe(register, compression=1, seq=1)

    def _ws_loop(self):
        """WebSocket连接主循环"""
        import websocket

        while self._running:
            try:
                ws_url = self._build_ws_url()
                self.logger.info(f"连接WebSocket...")

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

            # 重连
            self._reconnect_count += 1
            if self._reconnect_count > self._max_reconnect:
                self.logger.error(f"超过最大重连次数({self._max_reconnect})，停止")
                self._emit_status(False, "超过最大重连次数")
                break

            self.logger.info(f"{self._reconnect_interval}秒后重连... ({self._reconnect_count}/{self._max_reconnect})")
            for _ in range(self._reconnect_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _on_ws_open(self, ws):
        self.logger.info("WebSocket连接成功")
        self._reconnect_count = 0
        self._emit_status(True, "抖音直播间已连接")

        # 发送注册包
        try:
            register = self._build_register_packet()
            ws.send(register, opcode=0x2)  # binary frame
            self.logger.info("已发送注册包")

            # 发送心跳/ack
            ack = self._build_ack_packet()
            if ack:
                ws.send(ack, opcode=0x2)
        except Exception as e:
            self.logger.error(f"发送注册包失败: {e}")

    def _build_ack_packet(self) -> Optional[bytes]:
        """构建ack包"""
        try:
            ack_inner = pb.encode_varint_field(1, 0)
            ack = (
                pb.encode_varint_field(1, 0) +           # payload_type
                pb.encode_varint_field(2, 0) +           # compression
                pb.encode_varint_field(3, 0) +           # sequence
                pb.encode_length_delimited(4, ack_inner)  # payload
            )
            return ack
        except Exception:
            return None

    def _on_ws_message(self, ws, message):
        """处理WebSocket消息"""
        if not isinstance(message, (bytes, bytearray)):
            return

        try:
            self._parse_pushframe(message)
        except Exception as e:
            self.logger.debug(f"消息解析异常: {e}")

    def _parse_pushframe(self, data: bytes):
        """解析PushFrame"""
        frame = pb.parse_fields(data)

        # payload (field 4)
        payload = pb.get_field(frame, 4)
        if not payload:
            return

        # compression_type (field 2)
        compression = pb.get_field(frame, 2, 1)
        if compression == 2:  # gzip
            payload = pb.decompress_gzip(payload)

        # 解析Response
        resp = pb.parse_fields(payload)

        # messages (field 1)
        messages = pb.get_all_fields(resp, 1)
        for msg_data in messages:
            self._parse_message(msg_data)

        # cursor (field 2) - 用于ack
        cursor = pb.get_field(resp, 2)
        if cursor:
            pass  # 抖音需要定期发送ack

    def _parse_message(self, msg_data: bytes):
        """解析单条消息"""
        msg_fields = pb.parse_fields(msg_data)

        # msg_type (field 4)
        msg_type_raw = pb.get_field(msg_fields, 4, 0)
        # payload (field 2)
        msg_payload = pb.get_field(msg_fields, 2)

        if not msg_payload:
            return

        msg_type_str = DOUYIN_MSG_TYPE.get(msg_type_raw)
        if not msg_type_str:
            return

        # 发送原始数据(调试)
        self._emit_raw({
            'platform': 'douyin',
            'msg_type': msg_type_raw,
            'type_str': msg_type_str,
            'payload_hex': msg_payload.hex()[:200],
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
        """解析评论消息"""
        fields = pb.parse_fields(data)
        # user (field 2)
        user_data = pb.get_field(fields, 2, b'')
        user_fields = pb.parse_fields(user_data) if user_data else {}
        user_id = str(pb.get_field(user_fields, 1, 0))
        nickname = pb.decode_string(pb.get_field(user_fields, 2, b''))

        # content (field 3)
        content = pb.decode_string(pb.get_field(fields, 3, b''))

        if content:
            msg = self._create_message(
                MessageType.COMMENT,
                user_id=user_id,
                user_name=nickname,
                content=content,
            )
            self.logger.debug(f"[评论] {nickname}: {content}")
            self._emit_message(msg)

    def _parse_gift(self, data: bytes):
        """解析礼物消息"""
        fields = pb.parse_fields(data)

        # gift_id (field 1)
        gift_id = str(pb.get_field(fields, 1, 0))

        # group_count (field 3)
        group_count = pb.get_field(fields, 3, 0)

        # repeat_count (field 4)
        repeat_count = pb.get_field(fields, 4, 1)

        # user (field 7)
        user_data = pb.get_field(fields, 7, b'')
        user_fields = pb.parse_fields(user_data) if user_data else {}
        user_id = str(pb.get_field(user_fields, 1, 0))
        nickname = pb.decode_string(pb.get_field(user_fields, 2, b''))

        # gift struct (field 15) -> name (field 16)
        gift_data = pb.get_field(fields, 15, b'')
        gift_name = ""
        if gift_data:
            gift_fields = pb.parse_fields(gift_data)
            gift_name = pb.decode_string(pb.get_field(gift_fields, 16, b''))

        # diamond_count (field 20 in gift struct)
        gift_value = 0
        if gift_data:
            gift_value = pb.get_field(gift_fields, 20, 0)

        msg = self._create_message(
            MessageType.GIFT,
            user_id=user_id,
            user_name=nickname,
            content=gift_name or f"礼物{gift_id}",
            gift_id=gift_id,
            gift_count=max(repeat_count, group_count, 1),
            gift_value=gift_value,
        )
        self.logger.info(f"[礼物] {nickname} 送出 {gift_name} x{msg.gift_count}")
        self._emit_message(msg)

    def _parse_like(self, data: bytes):
        """解析点赞消息"""
        fields = pb.parse_fields(data)
        # user (field 5)
        user_data = pb.get_field(fields, 5, b'')
        user_fields = pb.parse_fields(user_data) if user_data else {}
        user_id = str(pb.get_field(user_fields, 1, 0))
        nickname = pb.decode_string(pb.get_field(user_fields, 2, b''))

        # count (field 1)
        count = pb.get_field(fields, 1, 1)

        msg = self._create_message(
            MessageType.LIKE,
            user_id=user_id,
            user_name=nickname,
            content="点赞",
            gift_count=count,
        )
        self._emit_message(msg)

    def _parse_member(self, data: bytes):
        """解析进场消息"""
        fields = pb.parse_fields(data)
        # user (field 2)
        user_data = pb.get_field(fields, 2, b'')
        user_fields = pb.parse_fields(user_data) if user_data else {}
        user_id = str(pb.get_field(user_fields, 1, 0))
        nickname = pb.decode_string(pb.get_field(user_fields, 2, b''))

        msg = self._create_message(
            MessageType.ENTER,
            user_id=user_id,
            user_name=nickname,
            content="进入直播间",
        )
        self._emit_message(msg)

    def _parse_social(self, data: bytes):
        """解析关注消息"""
        fields = pb.parse_fields(data)
        # user (field 2)
        user_data = pb.get_field(fields, 2, b'')
        user_fields = pb.parse_fields(user_data) if user_data else {}
        user_id = str(pb.get_field(user_fields, 1, 0))
        nickname = pb.decode_string(pb.get_field(user_fields, 2, b''))

        msg = self._create_message(
            MessageType.FOLLOW,
            user_id=user_id,
            user_name=nickname,
            content="关注了主播",
        )
        self._emit_message(msg)

    def _on_ws_error(self, ws, error):
        self.logger.error(f"WebSocket错误: {error}")

    def _on_ws_close(self, ws, close_status_code, close_msg):
        self.logger.info(f"WebSocket关闭: {close_status_code} {close_msg}")
        self._emit_status(False, "连接已断开")

    def disconnect(self):
        """断开连接"""
        self._running = False
        self.logger.info("正在断开抖音直播间...")
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._connected = False
        self._emit_status(False, "已断开")
