"""
SQLite数据库 - 存储消息历史和触发日志 (Android适配版)
"""
import sqlite3
import os
import sys
import json
from datetime import datetime
from typing import Optional


def _get_data_dir() -> str:
    """获取可写数据目录"""
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        context = PythonActivity.mActivity
        return context.getFilesDir().getAbsolutePath()
    except Exception:
        pass
    if 'ANDROID_APP_PATH' in os.environ:
        return os.environ['ANDROID_APP_PATH']
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Database:
    """消息历史和触发记录数据库"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(_get_data_dir(), "live_control.db")
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    datetime TEXT,
                    platform TEXT,
                    msg_type TEXT,
                    user_id TEXT,
                    user_name TEXT,
                    content TEXT,
                    gift_id TEXT,
                    gift_count INTEGER,
                    gift_value INTEGER,
                    raw_data TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS triggers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    datetime TEXT,
                    rule_id TEXT,
                    rule_name TEXT,
                    trigger_message TEXT,
                    bluetooth_command TEXT,
                    channel INTEGER,
                    status TEXT,
                    detail TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_triggers_ts ON triggers(timestamp)
            """)
            conn.commit()

    def log_message(self, msg):
        """记录直播消息"""
        from engine.models import LiveMessage
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO messages (timestamp, datetime, platform, msg_type, user_id,
                    user_name, content, gift_id, gift_count, gift_value, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                msg.timestamp,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                msg.platform.value,
                msg.msg_type.value,
                msg.user_id,
                msg.user_name,
                msg.content,
                msg.gift_id,
                msg.gift_count,
                msg.gift_value,
                json.dumps(msg.raw_data, ensure_ascii=False),
            ))
            conn.commit()

    def log_trigger(self, rule_id: str, rule_name: str, trigger_msg: str,
                    bt_cmd: str, channel: int, status: str, detail: str = ""):
        """记录触发日志"""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO triggers (timestamp, datetime, rule_id, rule_name,
                    trigger_message, bluetooth_command, channel, status, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().timestamp(),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                rule_id, rule_name, trigger_msg, bt_cmd, channel, status, detail,
            ))
            conn.commit()

    def get_recent_messages(self, limit: int = 100) -> list:
        """获取最近的消息"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_triggers(self, limit: int = 50) -> list:
        """获取最近的触发记录"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM triggers ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def clear_messages(self):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM messages")
            conn.commit()

    def clear_triggers(self):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM triggers")
            conn.commit()
