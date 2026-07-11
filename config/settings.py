"""
应用配置管理 - JSON文件存储 (Android适配版)
"""
import json
import os
import sys
from typing import Optional
from engine.models import BluetoothConfig, CommandRule


def get_data_dir() -> str:
    """获取可写数据目录 - Android/桌面兼容"""
    # Android环境
    if 'android' in sys.modules or 'jnius' in sys.modules:
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            context = PythonActivity.mActivity
            files_dir = context.getFilesDir().getAbsolutePath()
            return files_dir
        except Exception:
            pass
    # 桌面环境
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AppSettings:
    """应用设置管理"""

    DEFAULT_SETTINGS = {
        "theme": "dark",
        "auto_connect_bluetooth": False,
        "bluetooth": BluetoothConfig().to_dict(),
        "commands": [],
    }

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(get_data_dir(), "settings.json")
        self.config_path = config_path
        self._data: dict = {}
        self.load()

    def load(self):
        """加载配置"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                # 合并默认值，防止新增字段缺失
                self._data = self._merge_defaults(self.DEFAULT_SETTINGS, loaded)
            except Exception:
                self._data = json.loads(json.dumps(self.DEFAULT_SETTINGS))
        else:
            self._data = json.loads(json.dumps(self.DEFAULT_SETTINGS))

    def _merge_defaults(self, defaults: dict, loaded: dict) -> dict:
        """递归合并默认值"""
        result = dict(defaults)
        for k, v in loaded.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._merge_defaults(result[k], v)
            else:
                result[k] = v
        return result

    def save(self):
        """保存配置"""
        try:
            os.makedirs(os.path.dirname(self.config_path) or '.', exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()

    @property
    def bluetooth_config(self) -> BluetoothConfig:
        return BluetoothConfig.from_dict(self._data.get("bluetooth", {}))

    @bluetooth_config.setter
    def bluetooth_config(self, cfg: BluetoothConfig):
        self._data["bluetooth"] = cfg.to_dict()
        self.save()

    @property
    def commands(self) -> list[CommandRule]:
        return [CommandRule.from_dict(c) for c in self._data.get("commands", [])]

    @commands.setter
    def commands(self, cmds: list[CommandRule]):
        self._data["commands"] = [c.to_dict() for c in cmds]
        self.save()

    def add_command(self, cmd: CommandRule):
        cmds = self._data.get("commands", [])
        cmds.append(cmd.to_dict())
        self._data["commands"] = cmds
        self.save()

    def update_command(self, cmd: CommandRule):
        cmds = self._data.get("commands", [])
        for i, c in enumerate(cmds):
            if c.get("id") == cmd.id:
                cmds[i] = cmd.to_dict()
                self._data["commands"] = cmds
                self.save()
                return
        # 不存在则新增
        self.add_command(cmd)

    def delete_command(self, cmd_id: str):
        cmds = self._data.get("commands", [])
        self._data["commands"] = [c for c in cmds if c.get("id") != cmd_id]
        self.save()

    def get_command(self, cmd_id: str) -> Optional[CommandRule]:
        for c in self._data.get("commands", []):
            if c.get("id") == cmd_id:
                return CommandRule.from_dict(c)
        return None
