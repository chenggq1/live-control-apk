"""
指令引擎 - 核心调度中心
接收直播消息 -> 匹配指令规则 -> 触发蓝牙动作
"""
import threading
import time
from typing import Callable, Optional
from collections import deque

from engine.models import LiveMessage, CommandRule, MessageType, BluetoothConfig
from bluetooth.driver import BluetoothDriver
from config.database import Database
from config.settings import AppSettings
from utils.logger import get_logger

logger = get_logger().get_child('Engine')


class CommandEngine:
    """指令匹配与执行引擎"""

    def __init__(self, settings: AppSettings, db: Database):
        self.settings = settings
        self.db = db
        self.bluetooth: Optional[BluetoothDriver] = None
        self._rules: list[CommandRule] = []
        self._lock = threading.Lock()
        self._running = bool = False
        self._message_queue: deque = deque(maxlen=1000)
        self._engine_thread: Optional[threading.Thread] = None

        # 回调
        self._trigger_callbacks: list[Callable] = []  # 触发回调
        self._message_callbacks: list[Callable] = []  # 消息回调
        self._queue_callbacks: list[Callable] = []    # 队列状态回调

        # 统计
        self.stats = {
            'total_messages': 0,
            'total_triggers': 0,
            'total_errors': 0,
            'messages_by_type': {},
            'triggers_by_rule': {},
        }

    @property
    def rules(self) -> list[CommandRule]:
        return self._rules

    def reload_rules(self):
        """重新加载规则"""
        with self._lock:
            self._rules = self.settings.commands
        logger.info(f"已加载 {len(self._rules)} 条指令规则")

    def add_trigger_callback(self, callback: Callable):
        self._trigger_callbacks.append(callback)

    def add_message_callback(self, callback: Callable):
        self._message_callbacks.append(callback)

    def add_queue_callback(self, callback: Callable):
        self._queue_callbacks.append(callback)

    def init_bluetooth(self):
        """初始化蓝牙驱动"""
        bt_config = self.settings.bluetooth_config
        self.bluetooth = BluetoothDriver(bt_config)
        logger.info(f"蓝牙驱动已初始化: {bt_config.connection_type}, 端口={bt_config.port}")

    def on_message(self, msg: LiveMessage):
        """平台消息入口 - 线程安全"""
        self._message_queue.append(msg)
        self.stats['total_messages'] += 1
        msg_type = msg.msg_type.value
        self.stats['messages_by_type'][msg_type] = \
            self.stats['messages_by_type'].get(msg_type, 0) + 1

        # 通知消息回调
        for cb in self._message_callbacks:
            try:
                cb(msg)
            except Exception as e:
                logger.error(f"消息回调异常: {e}")

        # 通知队列回调
        for cb in self._queue_callbacks:
            try:
                cb(len(self._message_queue))
            except Exception:
                pass

    def start(self):
        """启动引擎"""
        self._running = True
        self.reload_rules()
        self._engine_thread = threading.Thread(target=self._engine_loop, daemon=True)
        self._engine_thread.start()
        logger.info("指令引擎已启动")

    def stop(self):
        """停止引擎"""
        self._running = False
        if self._engine_thread and self._engine_thread.is_alive():
            self._engine_thread.join(timeout=3)
        logger.info("指令引擎已停止")

    def _engine_loop(self):
        """引擎主循环 - 处理消息队列"""
        while self._running:
            try:
                if self._message_queue:
                    msg = self._message_queue.popleft()
                    self._process_message(msg)
                    # 通知队列更新
                    for cb in self._queue_callbacks:
                        try:
                            cb(len(self._message_queue))
                        except Exception:
                            pass
                else:
                    time.sleep(0.05)
            except Exception as e:
                logger.error(f"引擎处理异常: {e}")
                self.stats['total_errors'] += 1

    def _process_message(self, msg: LiveMessage):
        """处理单条消息 - 匹配规则并执行"""
        # 记录到数据库
        try:
            self.db.log_message(msg)
        except Exception as e:
            logger.debug(f"消息入库失败: {e}")

        # 匹配规则
        matched_rules = []
        with self._lock:
            for rule in self._rules:
                try:
                    if rule.matches(msg):
                        matched_rules.append(rule)
                except Exception as e:
                    logger.error(f"规则匹配异常 ({rule.name}): {e}")

        # 执行匹配的规则
        for rule in matched_rules:
            self._execute_rule(rule, msg)

    def _execute_rule(self, rule: CommandRule, msg: LiveMessage):
        """执行指令规则"""
        rule.last_triggered = time.time()
        self.stats['total_triggers'] += 1
        self.stats['triggers_by_rule'][rule.name] = \
            self.stats['triggers_by_rule'].get(rule.name, 0) + 1

        trigger_text = f"{rule.name} <- {msg.display_text}"
        logger.info(f"[触发] {trigger_text}")

        # 通知触发回调
        for cb in self._trigger_callbacks:
            try:
                cb(rule, msg)
            except Exception as e:
                logger.error(f"触发回调异常: {e}")

        # 执行蓝牙动作
        if self.bluetooth and self.bluetooth.is_connected:
            self._send_bluetooth_command(rule, msg)
        else:
            logger.warning(f"蓝牙未连接，规则 '{rule.name}' 触发但未执行蓝牙指令")
            self.db.log_trigger(
                rule.id, rule.name, msg.display_text,
                rule.bluetooth_command, rule.bluetooth_channel,
                "SKIPPED", "蓝牙未连接"
            )

    def _send_bluetooth_command(self, rule: CommandRule, msg: LiveMessage):
        """发送蓝牙指令"""
        try:
            cmd = rule.bluetooth_command
            channel = rule.bluetooth_channel

            if rule.action_type == "send_once":
                # 单次发送
                success = self.bluetooth.send_command(cmd, channel)
                status = "SUCCESS" if success else "FAILED"
                self.db.log_trigger(
                    rule.id, rule.name, msg.display_text,
                    cmd, channel, status, f"send_once: {cmd}"
                )

            elif rule.action_type == "pulse":
                # 脉冲模式: 开 -> 等待 -> 关
                bt_config = self.settings.bluetooth_config
                on_cmd = cmd if cmd else bt_config.default_on_cmd
                off_cmd = bt_config.default_off_cmd
                self.bluetooth.send_pulse(on_cmd, off_cmd, rule.pulse_duration, channel)
                status = "PULSE"
                self.db.log_trigger(
                    rule.id, rule.name, msg.display_text,
                    f"{on_cmd} -> {off_cmd}", channel, status,
                    f"pulse {rule.pulse_duration}ms"
                )

            elif rule.action_type == "toggle":
                # 切换模式 (需要状态追踪)
                if not hasattr(self, '_toggle_states'):
                    self._toggle_states = {}
                key = f"ch_{channel}"
                current = self._toggle_states.get(key, False)
                bt_config = self.settings.bluetooth_config
                if current:
                    cmd = bt_config.default_off_cmd
                    self._toggle_states[key] = False
                else:
                    cmd = cmd if cmd else bt_config.default_on_cmd
                    self._toggle_states[key] = True
                success = self.bluetooth.send_command(cmd, channel)
                status = "TOGGLE_ON" if self._toggle_states[key] else "TOGGLE_OFF"
                self.db.log_trigger(
                    rule.id, rule.name, msg.display_text,
                    cmd, channel, status, f"toggle -> {self._toggle_states[key]}"
                )

        except Exception as e:
            logger.error(f"蓝牙指令发送失败: {e}")
            self.db.log_trigger(
                rule.id, rule.name, msg.display_text,
                rule.bluetooth_command, rule.bluetooth_channel,
                "ERROR", str(e)
            )

    def get_stats(self) -> dict:
        """获取统计数据"""
        return dict(self.stats)

    def reset_stats(self):
        """重置统计"""
        self.stats = {
            'total_messages': 0,
            'total_triggers': 0,
            'total_errors': 0,
            'messages_by_type': {},
            'triggers_by_rule': {},
        }

    def manual_trigger(self, rule: CommandRule):
        """手动触发规则 (调试用)"""
        fake_msg = LiveMessage(
            msg_type=MessageType.SYSTEM,
            platform=rule.platform if hasattr(rule, 'platform') else None,
            user_name="手动触发",
            content="manual_trigger",
        )
        # 找一个有效的platform
        from engine.models import PlatformType
        if rule.platform != "all":
            try:
                fake_msg.platform = PlatformType(rule.platform)
            except ValueError:
                fake_msg.platform = PlatformType.DOUYIN
        else:
            fake_msg.platform = PlatformType.DOUYIN

        logger.info(f"[手动触发] {rule.name}")
        if self.bluetooth and self.bluetooth.is_connected:
            self._send_bluetooth_command(rule, fake_msg)
        else:
            logger.warning("蓝牙未连接")
