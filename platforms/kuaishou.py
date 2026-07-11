"""
快手直播弹幕/礼物抓取
基于快手Web版WebSocket协议
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

logger = get_logger().get_child('Kuaishou')


class KuaishouPlatform(BasePlatform):
    """快手直播抓取"""

    PLATFORM = PlatformType.KUAISHOU
    DISPLAY_NAME = "快手"

    def __init__(self):
        super().__init__()
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://live.kuaishou.com/',
            'Origin': 'https://live.kuaishou.com',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
        }
        self._cookies = {}
        self._live_stream_id = ""
        self._room_id = ""
        self._ws_url = ""

    def connect(self, room_url_or_id: str) -> bool:
        self._room_url = room_url_or_id
        self._running = True
        self._reconnect_count = 0
        self.logger.info(f"正在连接快手直播间: {room_url_or_id}")

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
        match = re.search(r'live\.kuaishou\.com/u/(\w+)', url_or_id)
        if match:
            return match.group(1)
        match = re.search(r'live\.kuaishou\.com/(\w+)', url_or_id)
        if match:
            return match.group(1)
        return url_or_id

    def _fetch_room_info(self, room_id: str) -> bool:
        """获取快手直播间信息"""
        try:
            # 访问直播间页面获取cookie
            url = f"https://live.kuaishou.com/u/{room_id}"
            resp = requests.get(url, headers=self._headers, timeout=10)
            self._cookies = dict(resp.cookies)

            text = resp.text

            # 提取liveStreamId
            patterns = [
                r'"liveStreamId"\s*:\s*"([^"]+)"',
                r'"streamId"\s*:\s*"([^"]+)"',
                r'liveStreamId["\']?\s*[:=]\s*["\']([^"\']+)',
            ]
            for pat in patterns:
                match = re.search(pat, text)
                if match:
                    self._live_stream_id = match.group(1)
                    self.logger.info(f"liveStreamId: {self._live_stream_id}")
                    break

            # 尝试通过GraphQL API获取WebSocket地址
            if self._fetch_ws_url():
                return True

            # 使用默认WebSocket URL
            self._ws_url = f"wss://live-ws.kuaishou.com/live_ws"
            self.logger.info("使用默认WebSocket地址")
            return True

        except Exception as e:
            self.logger.error(f"获取房间信息失败: {e}")
            return False

    def _fetch_ws_url(self) -> bool:
        """通过GraphQL API获取WebSocket地址"""
        try:
            graphql_url = "https://live.kuaishou.com/live_graphql"
            query = {
                "operationName": "LiveDataCell",
                "variables": {
                    "principalId": self._room_id,
                },
                "query": """query LiveDataCell($principalId: String) {
                    liveDataCell(principalId: $principalId) {
                        result
                        liveStreamId
                        playUrls { url }
                        wsUrl
                    }
                }"""
            }

            resp = requests.post(
                graphql_url,
                json=query,
                headers={**self._headers, 'Content-Type': 'application/json'},
                cookies=self._cookies,
                timeout=10
            )

            if resp.status_code == 200:
                data = resp.json()
                live_data = data.get('data', {}).get('liveDataCell', {})
                if live_data:
                    self._live_stream_id = live_data.get('liveStreamId', self._live_stream_id)
                    ws_url = live_data.get('wsUrl', '')
                    if ws_url:
                        self._ws_url = ws_url
                        self.logger.info(f"获取到WebSocket地址: {ws_url}")
                        return True

        except Exception as e:
            self.logger.debug(f"GraphQL请求失败: {e}")

        return False

    def _ws_loop(self):
        """WebSocket连接主循环"""
        import websocket

        while self._running:
            try:
                ws_url = self._ws_url or "wss://live-ws.kuaishou.com/live_ws"
                self.logger.info(f"连接快手WebSocket: {ws_url}")

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
        self.logger.info("快手WebSocket连接成功")
        self._reconnect_count = 0
        self._emit_status(True, "快手直播间已连接")

        # 发送注册包
        try:
            register = self._build_register_packet()
            ws.send(register, opcode=0x1)  # text frame for kuaishou
            self.logger.info("已发送注册包")
        except Exception as e:
            self.logger.error(f"发送注册包失败: {e}")

    def _build_register_packet(self) -> str:
        """构建快手注册包 (JSON格式)"""
        register_msg = {
            "command": "register",
            "commandId": 100,
            "payload": json.dumps({
                "liveStreamId": self._live_stream_id,
                "pageId": str(uuid.uuid4()),
                "sessionId": str(uuid.uuid4()),
            }),
            "rid": str(int(time.time() * 1000)),
            "type": "command",
        }
        return json.dumps(register_msg)

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

        msg_type = data.get("command") or data.get("type", "")

        self._emit_raw({
            'platform': 'kuaishou',
            'msg_type': msg_type,
            'data': data,
        })

        # 快手的消息结构可能嵌套在payload中
        payload = data.get("data") or data.get("payload", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}

        if not isinstance(payload, dict):
            return

        # 根据消息类型解析
        self._dispatch_message(msg_type, payload)

    def _parse_binary_message(self, data: bytes):
        """解析二进制消息 (protobuf格式)"""
        fields = pb.parse_fields(data)

        # commandType (field 1)
        cmd_type = pb.get_field(fields, 1, 0)
        # payload (field 2)
        payload = pb.get_field(fields, 2)

        if not payload:
            return

        # 尝试解析payload为JSON
        try:
            payload_str = payload.decode('utf-8')
            payload_data = json.loads(payload_str)
            self._dispatch_message(str(cmd_type), payload_data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            # protobuf格式
            self._parse_proto_payload(cmd_type, payload)

    def _dispatch_message(self, cmd_type: str, payload: dict):
        """根据消息类型分发"""
        # 快手消息类型映射
        # 4001: 评论, 4003: 礼物, 4004: 点赞, 4006: 进场, 4005: 关注
        type_map = {
            '4001': 'comment',
            'comment': 'comment',
            '4003': 'gift',
            'gift': 'gift',
            '4004': 'like',
            'like': 'like',
            '4006': 'enter',
            'enter': 'enter',
            '4005': 'follow',
            'follow': 'follow',
        }

        msg_type_str = type_map.get(str(cmd_type), '')
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

    def _parse_proto_payload(self, cmd_type: int, data: bytes):
        """解析protobuf格式的payload"""
        fields = pb.parse_fields(data)

        # 通用结构: user信息通常在某个field中
        # 这里做通用提取
        user_name = ""
        user_id = ""
        content = ""

        # 尝试提取常见字段
        for field_num in [2, 3, 4, 5, 6, 7, 8]:
            val = pb.get_field(fields, field_num)
            if isinstance(val, bytes):
                try:
                    decoded = val.decode('utf-8')
                    if not content:
                        content = decoded
                except UnicodeDecodeError:
                    sub_fields = pb.parse_fields(val)
                    uid = pb.get_field(sub_fields, 1, 0)
                    if uid:
                        user_id = str(uid)
                    nick = pb.get_field(sub_fields, 2, b'')
                    if nick:
                        try:
                            user_name = nick.decode('utf-8')
                        except UnicodeDecodeError:
                            pass

        if content or user_name:
            if cmd_type in [4001, 101]:
                msg = self._create_message(
                    MessageType.COMMENT,
                    user_id=user_id, user_name=user_name, content=content,
                )
                self.logger.debug(f"[评论] {user_name}: {content}")
                self._emit_message(msg)

    def _parse_chat_json(self, data: dict):
        """解析JSON评论"""
        user = data.get('user', {})
        user_name = user.get('userName', data.get('userName', ''))
        user_id = str(user.get('userId', data.get('userId', '')))
        content = data.get('content', '')

        if content:
            msg = self._create_message(
                MessageType.COMMENT,
                user_id=user_id, user_name=user_name, content=content,
            )
            self.logger.debug(f"[评论] {user_name}: {content}")
            self._emit_message(msg)

    def _parse_gift_json(self, data: dict):
        """解析JSON礼物"""
        user = data.get('user', {})
        user_name = user.get('userName', '')
        user_id = str(user.get('userId', ''))

        gift_name = data.get('giftName', data.get('name', ''))
        gift_count = data.get('comboCount', data.get('count', 1))
        gift_id = str(data.get('giftId', data.get('id', '')))
        gift_value = data.get('diamondCount', data.get('value', 0))

        msg = self._create_message(
            MessageType.GIFT,
            user_id=user_id, user_name=user_name,
            content=gift_name, gift_id=gift_id,
            gift_count=gift_count, gift_value=gift_value,
        )
        self.logger.info(f"[礼物] {user_name} 送出 {gift_name} x{gift_count}")
        self._emit_message(msg)

    def _parse_like_json(self, data: dict):
        """解析JSON点赞"""
        user = data.get('user', {})
        user_name = user.get('userName', '')
        user_id = str(user.get('userId', ''))
        count = data.get('likeCount', 1)

        msg = self._create_message(
            MessageType.LIKE, user_id=user_id, user_name=user_name,
            content="点赞", gift_count=count,
        )
        self._emit_message(msg)

    def _parse_enter_json(self, data: dict):
        """解析JSON进场"""
        user = data.get('user', {})
        user_name = user.get('userName', '')
        user_id = str(user.get('userId', ''))

        msg = self._create_message(
            MessageType.ENTER, user_id=user_id, user_name=user_name,
            content="进入直播间",
        )
        self._emit_message(msg)

    def _parse_follow_json(self, data: dict):
        """解析JSON关注"""
        user = data.get('user', {})
        user_name = user.get('userName', '')
        user_id = str(user.get('userId', ''))

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
        self.logger.info("正在断开快手直播间...")
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._connected = False
        self._emit_status(False, "已断开")
