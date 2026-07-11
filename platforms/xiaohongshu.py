"""
小红书直播弹幕/礼物抓取
基于小红书Web版WebSocket协议
"""
import threading
import time
import re
import json
import uuid
from typing import Optional

import requests

from platforms.base import BasePlatform
from engine.models import LiveMessage, MessageType, PlatformType
from utils import protobuf_lite as pb
from utils.logger import get_logger
from utils.network import safe_request_get, get_ws_sslopt

logger = get_logger().get_child('Xiaohongshu')


class XiaohongshuPlatform(BasePlatform):
    """小红书直播抓取"""

    PLATFORM = PlatformType.XIAOHONGSHU
    DISPLAY_NAME = "小红书"

    def __init__(self):
        super().__init__()
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.xiaohongshu.com/',
            'Origin': 'https://www.xiaohongshu.com',
            'Accept': 'application/json, text/plain, */*',
        }
        self._cookies = {}
        self._room_id = ""
        self._ws_url = ""
        self._token = ""

    def connect(self, room_url_or_id: str) -> bool:
        self._room_url = room_url_or_id
        self._running = True
        self._reconnect_count = 0
        self.logger.info(f"正在连接小红书直播间: {room_url_or_id}")

        try:
            room_id = self._extract_room_id(room_url_or_id)
            if not room_id:
                msg = f"无法解析房间ID: {room_url_or_id}"
                self.logger.error(msg)
                self._emit_status(False, msg)
                return False
            self._room_id = room_id

            if not self._fetch_room_info(room_id):
                msg = "获取房间信息失败"
                self.logger.error(msg)
                self._emit_status(False, msg)
                return False

            self._thread = threading.Thread(target=self._ws_loop, daemon=True)
            self._thread.start()
            return True

        except Exception as e:
            self.logger.error(f"连接失败: {e}")
            self._emit_status(False, str(e))
            return False

    def _extract_room_id(self, url_or_id: str) -> str:
        url_or_id = url_or_id.strip()
        if url_or_id.isdigit():
            return url_or_id
        # https://www.xiaohongshu.com/live_room/{room_id}
        match = re.search(r'xiaohongshu\.com/live_room/(\w+)', url_or_id)
        if match:
            return match.group(1)
        # https://www.xiaohongshu.com/live/{room_id}
        match = re.search(r'xiaohongshu\.com/live/(\w+)', url_or_id)
        if match:
            return match.group(1)
        return url_or_id

    def _fetch_room_info(self, room_id: str) -> bool:
        """获取小红书直播间信息"""
        try:
            url = f"https://www.xiaohongshu.com/live_room/{room_id}"
            resp = safe_request_get(url, headers=self._headers, timeout=15)
            self._cookies = dict(resp.cookies)

            text = resp.text

            # 提取直播间信息 (小红书页面中嵌入JSON)
            # 尝试多种pattern
            patterns = [
                r'"roomId"\s*:\s*"([^"]+)"',
                r'"liveRoomId"\s*:\s*"([^"]+)"',
                r'"room_id"\s*:\s*"([^"]+)"',
            ]
            for pat in patterns:
                match = re.search(pat, text)
                if match:
                    self._room_id = match.group(1)
                    break

            # 提取WebSocket地址
            ws_patterns = [
                r'"wsUrl"\s*:\s*"([^"]+)"',
                r'"websocketUrl"\s*:\s*"([^"]+)"',
                r'"wssUrl"\s*:\s*"([^"]+)"',
            ]
            for pat in ws_patterns:
                match = re.search(pat, text)
                if match:
                    self._ws_url = match.group(1).replace('\\u002F', '/')
                    break

            # 提取token
            token_patterns = [
                r'"token"\s*:\s*"([^"]+)"',
                r'"liveToken"\s*:\s*"([^"]+)"',
            ]
            for pat in token_patterns:
                match = re.search(pat, text)
                if match:
                    self._token = match.group(1)
                    break

            # 如果没获取到WebSocket地址，使用默认
            if not self._ws_url:
                self._ws_url = f"wss://live-room.xiaohongshu.com/live/ws/{self._room_id}"

            self.logger.info(f"房间ID: {self._room_id}, WebSocket地址: {self._ws_url}")
            return True

        except Exception as e:
            self.logger.error(f"获取房间信息失败: {e}")
            return False

    def _ws_loop(self):
        """WebSocket连接主循环"""
        import websocket

        while self._running:
            try:
                ws_url = self._ws_url
                self.logger.info(f"连接小红书WebSocket: {ws_url}")

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
                    ping_interval=15,
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

            self.logger.info(f"{self._reconnect_interval}秒后重连...")
            for _ in range(self._reconnect_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _on_ws_open(self, ws):
        self.logger.info("小红书WebSocket连接成功")
        self._reconnect_count = 0
        self._emit_status(True, "小红书直播间已连接")

        # 发送注册包
        try:
            register = self._build_register_packet()
            ws.send(register, opcode=0x1)
            self.logger.info("已发送注册包")
        except Exception as e:
            self.logger.error(f"发送注册包失败: {e}")

    def _build_register_packet(self) -> str:
        """构建注册包 (JSON)"""
        register = {
            "type": "register",
            "roomId": self._room_id,
            "token": self._token,
            "clientId": str(uuid.uuid4()),
        }
        return json.dumps(register)

    def _on_ws_message(self, ws, message):
        """处理WebSocket消息"""
        try:
            if isinstance(message, (bytes, bytearray)):
                self._parse_binary_message(message)
            elif isinstance(message, str):
                self._parse_text_message(message)
        except Exception as e:
            self.logger.debug(f"消息解析异常: {e}")

    def _parse_text_message(self, text: str):
        """解析JSON文本消息"""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return

        # 小红书消息格式: {type: "...", data: {...}}
        msg_type = data.get("type", data.get("cmd", ""))
        payload = data.get("data", data.get("payload", data))

        self._emit_raw({
            'platform': 'xiaohongshu',
            'msg_type': msg_type,
            'data': data,
        })

        self._dispatch_message(msg_type, payload)

    def _parse_binary_message(self, data: bytes):
        """解析二进制消息"""
        try:
            text = data.decode('utf-8')
            self._parse_text_message(text)
        except UnicodeDecodeError:
            # protobuf格式
            fields = pb.parse_fields(data)
            cmd_type = pb.get_field(fields, 1, 0)
            payload = pb.get_field(fields, 2)
            if payload:
                try:
                    payload_data = json.loads(payload.decode('utf-8'))
                    self._dispatch_message(str(cmd_type), payload_data)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass

    def _dispatch_message(self, msg_type: str, payload):
        """根据消息类型分发"""
        if not isinstance(payload, dict):
            return

        # 小红书消息类型映射
        type_map = {
            'comment': 'comment',
            'COMMENT': 'comment',
            'gift': 'gift',
            'GIFT': 'gift',
            'like': 'like',
            'LIKE': 'like',
            'enter': 'enter',
            'ENTER': 'enter',
            'follow': 'follow',
            'FOLLOW': 'follow',
            'message': 'comment',
        }

        msg_type_str = type_map.get(str(msg_type), '')
        if not msg_type_str:
            # 尝试从payload中获取type
            inner_type = payload.get('type', payload.get('bizType', ''))
            msg_type_str = type_map.get(str(inner_type), '')

        if not msg_type_str:
            return

        if msg_type_str == 'comment':
            self._parse_chat_json(payload)
        elif msg_type_str == 'gift':
            self._parse_gift_json(payload)
        elif msg_type_str == 'like':
            self._parse_like_json(payload)
        elif msg_type_str == 'enter':
            self._parse_enter_json(payload)
        elif msg_type_str == 'follow':
            self._parse_follow_json(payload)

    def _parse_chat_json(self, data: dict):
        """解析评论"""
        user = data.get('user', data.get('userInfo', {}))
        user_name = user.get('nickname', user.get('name', ''))
        user_id = str(user.get('userId', user.get('id', '')))
        content = data.get('content', data.get('text', data.get('message', '')))

        if content:
            msg = self._create_message(
                MessageType.COMMENT,
                user_id=user_id, user_name=user_name, content=content,
            )
            self.logger.debug(f"[评论] {user_name}: {content}")
            self._emit_message(msg)

    def _parse_gift_json(self, data: dict):
        """解析礼物"""
        user = data.get('user', data.get('userInfo', {}))
        user_name = user.get('nickname', user.get('name', ''))
        user_id = str(user.get('userId', user.get('id', '')))

        gift_name = data.get('giftName', data.get('name', ''))
        gift_count = data.get('count', data.get('comboCount', 1))
        gift_id = str(data.get('giftId', data.get('id', '')))
        gift_value = data.get('price', data.get('diamondCount', 0))

        msg = self._create_message(
            MessageType.GIFT,
            user_id=user_id, user_name=user_name,
            content=gift_name, gift_id=gift_id,
            gift_count=gift_count, gift_value=gift_value,
        )
        self.logger.info(f"[礼物] {user_name} 送出 {gift_name} x{gift_count}")
        self._emit_message(msg)

    def _parse_like_json(self, data: dict):
        """解析点赞"""
        user = data.get('user', data.get('userInfo', {}))
        user_name = user.get('nickname', user.get('name', ''))
        user_id = str(user.get('userId', user.get('id', '')))
        count = data.get('count', data.get('likeCount', 1))

        msg = self._create_message(
            MessageType.LIKE, user_id=user_id, user_name=user_name,
            content="点赞", gift_count=count,
        )
        self._emit_message(msg)

    def _parse_enter_json(self, data: dict):
        """解析进场"""
        user = data.get('user', data.get('userInfo', {}))
        user_name = user.get('nickname', user.get('name', ''))
        user_id = str(user.get('userId', user.get('id', '')))

        msg = self._create_message(
            MessageType.ENTER, user_id=user_id, user_name=user_name,
            content="进入直播间",
        )
        self._emit_message(msg)

    def _parse_follow_json(self, data: dict):
        """解析关注"""
        user = data.get('user', data.get('userInfo', {}))
        user_name = user.get('nickname', user.get('name', ''))
        user_id = str(user.get('userId', user.get('id', '')))

        msg = self._create_message(
            MessageType.FOLLOW, user_id=user_id, user_name=user_name,
            content="关注了主播",
        )
        self._emit_message(msg)

    def _on_ws_error(self, ws, error):
        self.logger.error(f"WebSocket错误: {error}")

    def _on_ws_close(self, ws, close_status_code, close_msg):
        self.logger.info(f"WebSocket关闭: {close_status_code} {close_msg}")
        self._emit_status(False, "连接已断开")

    def disconnect(self):
        self._running = False
        self.logger.info("正在断开小红书直播间...")
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._connected = False
        self._emit_status(False, "已断开")
