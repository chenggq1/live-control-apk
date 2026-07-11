"""
直播互动蓝牙控制台 - Android移动端主应用
KivyMD Material Design UI
"""
import os
import sys
import json
import time
import traceback
import threading

# 确保项目根目录在path中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.switch import Switch
from kivy.uix.popup import Popup
from kivy.uix.gridlayout import GridLayout
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty

# ===== 注册中文字体，解决Android中文乱码 =====
def _register_chinese_font():
    """注册中文字体，解决Android上中文显示为方块/乱码的问题"""
    _app_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. 优先使用打包在APK中的字体
    bundled_font = os.path.join(_app_dir, 'simhei.ttf')
    if os.path.exists(bundled_font):
        LabelBase.register('Roboto', bundled_font)
        print(f"[FONT] 使用打包中文字体: {bundled_font}")
        return True

    # 2. 尝试Android系统自带中文字体
    system_fonts = [
        '/system/fonts/DroidSansFallback.ttf',
        '/system/fonts/NotoSansCJK-Regular.ttc',
        '/system/fonts/NotoSansSC-Regular.otf',
        '/system/fonts/SourceHanSansCN-Regular.otf',
    ]
    for fp in system_fonts:
        if os.path.exists(fp):
            LabelBase.register('Roboto', fp)
            print(f"[FONT] 使用系统中文字体: {fp}")
            return True

    print("[FONT] 警告: 未找到中文字体，中文可能显示乱码")
    return False

_register_chinese_font()
# ===== 中文字体注册结束 =====

# 尝试导入KivyMD，失败则使用纯Kivy
try:
    from kivymd.app import MDApp
    from kivymd.uix.bottomnavigation import MDBottomNavigation, MDBottomNavigationItem
    from kivymd.uix.screen import MDScreen
    from kivymd.uix.card import MDCard
    from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDRoundFlatButton
    from kivymd.uix.textfield import MDTextField
    from kivymd.uix.label import MDLabel
    from kivymd.uix.list import MDList, OneLineListItem, TwoLineListItem, ThreeLineListItem
    from kivymd.uix.dialog import MDDialog
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.scrollview import MDScrollView
    from kivymd.uix.snackbar import Snackbar
    from kivymd.uix.spinner import MDSpinner
    from kivymd.uix.chip import MDChip
    KIVYMD = True
except ImportError:
    KIVYMD = False

# 延迟导入项目模块 - 避免启动时崩溃
_settings = None
_db = None
_engine = None
_platforms_mod = {}
_bluetooth_driver = None
_models = {}

def _init_modules():
    """延迟初始化所有项目模块"""
    global _settings, _db, _engine, _bluetooth_driver, _models
    try:
        from config.settings import AppSettings
        from config.database import Database
        from engine.models import (LiveMessage, CommandRule, BluetoothConfig,
                                   MessageType, PlatformType, TriggerType)
        from engine.command_engine import CommandEngine
        from bluetooth.driver import AndroidBluetoothDriver
        from utils.logger import get_logger

        _settings = AppSettings()
        _db = Database()
        _engine = CommandEngine(_settings, _db)
        _engine.start()
        _bluetooth_driver = AndroidBluetoothDriver
        _models = {
            'LiveMessage': LiveMessage,
            'CommandRule': CommandRule,
            'BluetoothConfig': BluetoothConfig,
            'MessageType': MessageType,
            'PlatformType': PlatformType,
            'TriggerType': TriggerType,
        }
    except Exception as e:
        traceback.print_exc()
        raise

def _import_platforms():
    """延迟导入平台模块"""
    global _platforms_mod
    if _platforms_mod:
        return
    try:
        from platforms.douyin import DouyinPlatform
        from platforms.tiktok import TiktokPlatform
        from platforms.kuaishou import KuaishouPlatform
        from platforms.xiaohongshu import XiaohongshuPlatform
        _platforms_mod = {
            'douyin': ('抖音', DouyinPlatform),
            'kuaishou': ('快手', KuaishouPlatform),
            'xiaohongshu': ('小红书', XiaohongshuPlatform),
            'tiktok': ('TikTok', TiktokPlatform),
        }
    except Exception as e:
        traceback.print_exc()
        raise

logger = None

# 颜色主题
COLORS = {
    'bg': (0.12, 0.12, 0.15, 1),
    'card': (0.18, 0.18, 0.22, 1),
    'primary': (0.25, 0.60, 0.95, 1),
    'accent': (0.95, 0.40, 0.45, 1),
    'success': (0.30, 0.75, 0.45, 1),
    'warning': (0.95, 0.75, 0.30, 1),
    'text': (0.92, 0.92, 0.95, 1),
    'text_dim': (0.60, 0.60, 0.65, 1),
    'divider': (0.25, 0.25, 0.30, 1),
}

# 平台注册 - 延迟加载
PLATFORMS = {}


class ColoredLabel(Label):
    """带背景色的标签"""
    def __init__(self, text='', bg_color=None, text_color=None, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.color = text_color or COLORS['text']
        self.size_hint_y = None
        self.height = dp(40)
        self.padding = (dp(15), dp(10))
        self.valign = 'middle'
        with self.canvas.before:
            Color(*((bg_color or COLORS['card'])[:3]), 1)
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size


class CardLayout(BoxLayout):
    """卡片容器"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = dp(15)
        self.spacing = dp(8)
        self.size_hint_y = None
        self.height = dp(120)
        with self.canvas.before:
            Color(*COLORS['card'][:3], 1)
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size


class PlatformTab(BoxLayout):
    """平台连接页"""
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'
        self.padding = dp(15)
        self.spacing = dp(12)
        self.platform_instances = {}

        # 标题
        title = Label(
            text='[b]直播平台连接[/b]',
            markup=True, color=COLORS['text'],
            size_hint_y=None, height=dp(45),
            font_size=sp(20), halign='left', valign='middle',
        )
        title.bind(size=lambda *x: title.setter('text_size')(title, title.size))
        self.add_widget(title)

        # 滚动区域
        scroll = ScrollView(size_hint=(1, 1))
        container = BoxLayout(orientation='vertical', spacing=dp(12), size_hint_y=None)
        container.bind(minimum_height=container.setter('height'))

        # 确保平台模块已加载
        _import_platforms()
        for key, (name, cls) in PLATFORMS.items():
            card = self._build_platform_card(key, name)
            container.add_widget(card)

        scroll.add_widget(container)
        self.add_widget(scroll)

    def _build_platform_card(self, key, name):
        card = CardLayout(height=dp(165))
        # 平台名称行
        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(35))
        status_label = Label(
            text='● 未连接',
            color=COLORS['text_dim'], font_size=sp(13),
            size_hint_x=0.6, halign='right', valign='middle',
        )
        header.add_widget(Label(
            text=f'[b]{name}[/b]', markup=True,
            color=COLORS['text'], font_size=sp(17),
            size_hint_x=0.4, halign='left', valign='middle',
        ))
        header.add_widget(status_label)

        # URL输入
        url_input = TextInput(
            hint_text=f'输入{name}直播间链接或ID',
            size_hint_y=None, height=dp(40),
            background_color=COLORS['bg'],
            foreground_color=COLORS['text'],
            hint_text_color=COLORS['text_dim'],
            font_size=sp(14),
            multiline=False,
            padding=(dp(10), dp(10)),
        )

        # 按钮行
        btn_row = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(42))

        connect_btn = Button(
            text='连接', size_hint_x=0.5,
            background_color=COLORS['primary'],
            color=(1, 1, 1, 1), font_size=sp(15),
            background_normal='', background_down='',
        )
        disconnect_btn = Button(
            text='断开', size_hint_x=0.5,
            background_color=COLORS['accent'],
            color=(1, 1, 1, 1), font_size=sp(15),
            background_normal='', background_down='',
        )

        connect_btn.bind(on_release=lambda btn, k=key, u=url_input: self._on_connect(k, u, status_label))
        disconnect_btn.bind(on_release=lambda btn, k=key: self._on_disconnect(k, status_label))

        btn_row.add_widget(connect_btn)
        btn_row.add_widget(disconnect_btn)

        card.clear_widgets()
        card.add_widget(header)
        card.add_widget(url_input)
        card.add_widget(btn_row)

        # 保存引用
        if not hasattr(self.app, 'platform_status_labels'):
            self.app.platform_status_labels = {}
        self.app.platform_status_labels[key] = status_label

        return card

    def _on_connect(self, key, url_input, status_label):
        url = url_input.text.strip()
        if not url:
            self.app.show_snack('请输入直播间链接')
            return

        status_label.text = '● 连接中...'
        status_label.color = COLORS['warning']

        def _do_connect():
            try:
                cls = PLATFORMS[key][1]
                platform = cls()
                platform.add_message_callback(self.app.on_platform_message)
                platform.add_status_callback(
                    lambda connected, msg, k=key, sl=status_label:
                    Clock.schedule_once(lambda dt: self._on_status(k, connected, msg, sl), 0)
                )
                platform.connect(url)
                self.platform_instances[key] = platform
            except Exception as e:
                Clock.schedule_once(lambda dt: (
                    setattr(status_label, 'text', f'● 连接失败'),
                    setattr(status_label, 'color', COLORS['accent']),
                    self.app.show_snack(f'连接失败: {e}')
                ), 0)

        threading.Thread(target=_do_connect, daemon=True).start()

    def _on_status(self, key, connected, msg, status_label):
        if connected:
            status_label.text = f'● {msg}'
            status_label.color = COLORS['success']
        else:
            status_label.text = f'● {msg}'
            status_label.color = COLORS['text_dim']

    def _on_disconnect(self, key, status_label):
        if key in self.platform_instances:
            self.platform_instances[key].disconnect()
            del self.platform_instances[key]
        status_label.text = '● 未连接'
        status_label.color = COLORS['text_dim']
        self.app.show_snack('已断开连接')


class BluetoothTab(BoxLayout):
    """蓝牙设置页"""
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'
        self.padding = dp(15)
        self.spacing = dp(12)

        title = Label(
            text='[b]蓝牙设置[/b]', markup=True,
            color=COLORS['text'], font_size=sp(20),
            size_hint_y=None, height=dp(45),
            halign='left', valign='middle',
        )
        title.bind(size=lambda *x: title.setter('text_size')(title, title.size))
        self.add_widget(title)

        scroll = ScrollView(size_hint=(1, 1))
        container = BoxLayout(orientation='vertical', spacing=dp(12), size_hint_y=None)
        container.bind(minimum_height=container.setter('height'))

        # 连接类型
        type_card = CardLayout(height=dp(80))
        type_label = Label(text='连接类型', color=COLORS['text'], font_size=sp(15),
                          size_hint_y=None, height=dp(30), halign='left', valign='middle')
        type_label.bind(size=lambda *x: type_label.setter('text_size')(type_label, type_label.size))
        type_row = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(40))
        self.type_spinner = Spinner(
            text='SPP串口 (HC-05/HC-06)',
            values=['SPP串口 (HC-05/HC-06)', 'BLE蓝牙'],
            size_hint_x=1, background_color=COLORS['bg'],
            color=COLORS['text'], font_size=sp(14),
            sync_height=True,
        )
        type_row.add_widget(self.type_spinner)
        type_card.clear_widgets()
        type_card.add_widget(type_label)
        type_card.add_widget(type_row)
        container.add_widget(type_card)

        # 设备地址输入
        addr_card = CardLayout(height=dp(80))
        addr_label = Label(text='设备MAC地址', color=COLORS['text'], font_size=sp(15),
                          size_hint_y=None, height=dp(30), halign='left', valign='middle')
        addr_label.bind(size=lambda *x: addr_label.setter('text_size')(addr_label, addr_label.size))
        self.addr_input = TextInput(
            hint_text='输入蓝牙MAC地址 (如 XX:XX:XX:XX:XX:XX)',
            size_hint_y=None, height=dp(40),
            background_color=COLORS['bg'],
            foreground_color=COLORS['text'],
            hint_text_color=COLORS['text_dim'],
            font_size=sp(14), multiline=False,
            padding=(dp(10), dp(10)),
        )
        addr_card.clear_widgets()
        addr_card.add_widget(addr_label)
        addr_card.add_widget(self.addr_input)
        container.add_widget(addr_card)

        # BLE配置（可选）
        ble_card = CardLayout(height=dp(120))
        ble_label = Label(text='BLE配置 (BLE模式可选)', color=COLORS['text_dim'], font_size=sp(14),
                         size_hint_y=None, height=dp(30), halign='left', valign='middle')
        ble_label.bind(size=lambda *x: ble_label.setter('text_size')(ble_label, ble_label.size))
        self.service_uuid_input = TextInput(
            hint_text='Service UUID (默认: 0000ffe0-...)',
            size_hint_y=None, height=dp(36),
            background_color=COLORS['bg'], foreground_color=COLORS['text'],
            hint_text_color=COLORS['text_dim'], font_size=sp(13),
            multiline=False, padding=(dp(10), dp(8)),
        )
        self.char_uuid_input = TextInput(
            hint_text='Char UUID (默认: 0000ffe1-...)',
            size_hint_y=None, height=dp(36),
            background_color=COLORS['bg'], foreground_color=COLORS['text'],
            hint_text_color=COLORS['text_dim'], font_size=sp(13),
            multiline=False, padding=(dp(10), dp(8)),
        )
        ble_card.clear_widgets()
        ble_card.add_widget(ble_label)
        ble_card.add_widget(self.service_uuid_input)
        ble_card.add_widget(self.char_uuid_input)
        container.add_widget(ble_card)

        # 默认指令
        cmd_card = CardLayout(height=dp(120))
        cmd_label = Label(text='默认蓝牙指令 (十六进制)', color=COLORS['text'], font_size=sp(15),
                         size_hint_y=None, height=dp(30), halign='left', valign='middle')
        cmd_label.bind(size=lambda *x: cmd_label.setter('text_size')(cmd_label, cmd_label.size))
        self.on_cmd_input = TextInput(
            hint_text='开指令 (如 A00101A2)',
            size_hint_y=None, height=dp(36),
            background_color=COLORS['bg'], foreground_color=COLORS['text'],
            hint_text_color=COLORS['text_dim'], font_size=sp(13),
            multiline=False, padding=(dp(10), dp(8)),
        )
        self.off_cmd_input = TextInput(
            hint_text='关指令 (如 A00100A1)',
            size_hint_y=None, height=dp(36),
            background_color=COLORS['bg'], foreground_color=COLORS['text'],
            hint_text_color=COLORS['text_dim'], font_size=sp(13),
            multiline=False, padding=(dp(10), dp(8)),
        )
        cmd_card.clear_widgets()
        cmd_card.add_widget(cmd_label)
        cmd_card.add_widget(self.on_cmd_input)
        cmd_card.add_widget(self.off_cmd_input)
        container.add_widget(cmd_card)

        # 操作按钮
        btn_card = CardLayout(height=dp(100))
        btn_row1 = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(42))
        scan_btn = Button(text='扫描已配对设备', background_color=COLORS['primary'],
                         color=(1,1,1,1), font_size=sp(14), background_normal='', background_down='')
        connect_btn = Button(text='连接蓝牙', background_color=COLORS['success'],
                           color=(1,1,1,1), font_size=sp(14), background_normal='', background_down='')
        btn_row1.add_widget(scan_btn)
        btn_row1.add_widget(connect_btn)

        btn_row2 = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(42))
        test_btn = Button(text='测试发送', background_color=COLORS['warning'],
                         color=(1,1,1,1), font_size=sp(14), background_normal='', background_down='')
        disconnect_btn = Button(text='断开蓝牙', background_color=COLORS['accent'],
                              color=(1,1,1,1), font_size=sp(14), background_normal='', background_down='')
        btn_row2.add_widget(test_btn)
        btn_row2.add_widget(disconnect_btn)

        scan_btn.bind(on_release=self._on_scan)
        connect_btn.bind(on_release=self._on_connect)
        test_btn.bind(on_release=self._on_test)
        disconnect_btn.bind(on_release=self._on_disconnect)

        btn_card.clear_widgets()
        btn_card.add_widget(btn_row1)
        btn_card.add_widget(btn_row2)
        container.add_widget(btn_card)

        # 状态显示
        self.status_label = Label(
            text='蓝牙状态: 未连接',
            color=COLORS['text_dim'], font_size=sp(14),
            size_hint_y=None, height=dp(40),
            halign='center', valign='middle',
        )
        self.status_label.bind(size=lambda *x: self.status_label.setter('text_size')(self.status_label, self.status_label.size))
        container.add_widget(self.status_label)

        scroll.add_widget(container)
        self.add_widget(scroll)

        # 加载已保存的配置
        self._load_config()

    def _load_config(self):
        cfg = self.app.settings.bluetooth_config
        if cfg.connection_type == 'ble':
            self.type_spinner.text = 'BLE蓝牙'
        self.addr_input.text = cfg.ble_address or cfg.port or ''
        self.service_uuid_input.text = cfg.ble_service_uuid or ''
        self.char_uuid_input.text = cfg.ble_char_uuid or ''
        self.on_cmd_input.text = cfg.default_on_cmd or ''
        self.off_cmd_input.text = cfg.default_off_cmd or ''

    def _save_config(self):
        is_ble = 'BLE' in self.type_spinner.text
        BluetoothConfig = _models['BluetoothConfig']
        cfg = BluetoothConfig(
            connection_type='ble' if is_ble else 'serial',
            port=self.addr_input.text.strip(),
            ble_address=self.addr_input.text.strip(),
            ble_service_uuid=self.service_uuid_input.text.strip(),
            ble_char_uuid=self.char_uuid_input.text.strip(),
            default_on_cmd=self.on_cmd_input.text.strip() or 'A00101A2',
            default_off_cmd=self.off_cmd_input.text.strip() or 'A00100A1',
        )
        self.app.settings.bluetooth_config = cfg
        return cfg

    def _on_scan(self, btn):
        self.app.show_snack('正在扫描已配对设备...')
        def _scan():
            driver = _bluetooth_driver(self._save_config())
            devices = driver.scan_paired_devices()
            if devices:
                Clock.schedule_once(lambda dt: self._show_device_list(devices), 0)
            else:
                Clock.schedule_once(lambda dt: self.app.show_snack('未找到已配对设备'), 0)
        threading.Thread(target=_scan, daemon=True).start()

    def _show_device_list(self, devices):
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(10))
        scroll = ScrollView()
        list_layout = BoxLayout(orientation='vertical', spacing=dp(8), size_hint_y=None)
        list_layout.bind(minimum_height=list_layout.setter('height'))

        for dev in devices:
            btn = Button(
                text=f"{dev['name']}\n{dev['address']}",
                size_hint_y=None, height=dp(55),
                background_color=COLORS['card'],
                color=COLORS['text'], font_size=sp(13),
                background_normal='', background_down='',
                halign='center', valign='middle',
            )
            btn.bind(on_release=lambda b, addr=dev['address']: self._select_device(addr))
            list_layout.add_widget(btn)

        scroll.add_widget(list_layout)
        content.add_widget(scroll)

        close_btn = Button(text='关闭', size_hint_y=None, height=dp(45),
                          background_color=COLORS['accent'], color=(1,1,1,1),
                          background_normal='', background_down='')
        content.add_widget(close_btn)

        popup = Popup(title='选择蓝牙设备', content=content,
                     size_hint=(0.9, 0.7))
        close_btn.bind(on_release=popup.dismiss)
        popup.open()

    def _select_device(self, address):
        self.addr_input.text = address
        self.app.show_snack(f'已选择: {address}')

    def _on_connect(self, btn):
        addr = self.addr_input.text.strip()
        if not addr:
            self.app.show_snack('请输入设备地址')
            return
        self.status_label.text = '蓝牙状态: 连接中...'
        self.status_label.color = COLORS['warning']

        def _connect():
            cfg = self._save_config()
            self.app.engine.init_bluetooth()
            success = self.app.engine.bluetooth.connect()
            Clock.schedule_once(lambda dt: self._on_connect_result(success), 0)

        threading.Thread(target=_connect, daemon=True).start()

    def _on_connect_result(self, success):
        if success:
            self.status_label.text = '蓝牙状态: 已连接'
            self.status_label.color = COLORS['success']
            self.app.show_snack('蓝牙连接成功')
        else:
            self.status_label.text = '蓝牙状态: 连接失败'
            self.status_label.color = COLORS['accent']
            self.app.show_snack('蓝牙连接失败')

    def _on_disconnect(self, btn):
        if self.app.engine.bluetooth:
            self.app.engine.bluetooth.disconnect()
        self.status_label.text = '蓝牙状态: 未连接'
        self.status_label.color = COLORS['text_dim']
        self.app.show_snack('蓝牙已断开')

    def _on_test(self, btn):
        if not self.app.engine.bluetooth or not self.app.engine.bluetooth.is_connected:
            self.app.show_snack('请先连接蓝牙')
            return
        cmd = self.on_cmd_input.text.strip() or 'A00101A2'
        success = self.app.engine.bluetooth.test_command(cmd)
        if success:
            self.app.show_snack(f'指令已发送: {cmd}')
        else:
            self.app.show_snack('发送失败')


class CommandTab(BoxLayout):
    """指令管理页"""
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'
        self.padding = dp(15)
        self.spacing = dp(12)

        title = Label(
            text='[b]指令管理[/b]', markup=True,
            color=COLORS['text'], font_size=sp(20),
            size_hint_y=None, height=dp(45),
            halign='left', valign='middle',
        )
        title.bind(size=lambda *x: title.setter('text_size')(title, title.size))
        self.add_widget(title)

        # 新增按钮
        add_btn = Button(
            text='+ 新增指令规则',
            size_hint_y=None, height=dp(45),
            background_color=COLORS['primary'],
            color=(1,1,1,1), font_size=sp(16),
            background_normal='', background_down='',
        )
        add_btn.bind(on_release=self._show_add_dialog)
        self.add_widget(add_btn)

        # 指令列表
        self.scroll = ScrollView(size_hint=(1, 1))
        self.list_container = BoxLayout(orientation='vertical', spacing=dp(10), size_hint_y=None)
        self.list_container.bind(minimum_height=self.list_container.setter('height'))
        self.scroll.add_widget(self.list_container)
        self.add_widget(self.scroll)

        self.refresh_list()

    def refresh_list(self):
        self.list_container.clear_widgets()
        commands = self.app.settings.commands
        if not commands:
            empty = Label(
                text='暂无指令规则\n点击上方按钮新增',
                color=COLORS['text_dim'], font_size=sp(15),
                size_hint_y=None, height=dp(100),
                halign='center', valign='middle',
            )
            empty.bind(size=lambda *x: empty.setter('text_size')(empty, empty.size))
            self.list_container.add_widget(empty)
            return

        for cmd in commands:
            card = self._build_command_card(cmd)
            self.list_container.add_widget(card)

    def _build_command_card(self, cmd):
        card = CardLayout(height=dp(180))

        # 名称行
        name_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(35))
        name_label = Label(
            text=f'[b]{cmd.name}[/b]', markup=True,
            color=COLORS['text'], font_size=sp(16),
            size_hint_x=0.6, halign='left', valign='middle',
        )
        name_label.bind(size=lambda *x: name_label.setter('text_size')(name_label, name_label.size))

        enable_switch = Switch(
            active=cmd.enabled,
            size_hint_x=0.4,
        )
        enable_switch.bind(active=lambda sw, val, c=cmd: self._toggle_command(c, val))

        name_row.add_widget(name_label)
        name_row.add_widget(enable_switch)

        # 详情
        platform_name = {'all': '所有平台', 'douyin': '抖音', 'kuaishou': '快手',
                        'xiaohongshu': '小红书', 'tiktok': 'TikTok'}.get(cmd.platform, cmd.platform)
        msg_type_name = {'comment': '评论', 'gift': '礼物', 'like': '点赞',
                        'follow': '关注', 'enter': '进场'}.get(cmd.msg_type, cmd.msg_type)
        trigger_name = {'exact': '精确匹配', 'contains': '包含', 'regex': '正则',
                       'gift_name': '礼物名称', 'gift_count': '礼物数量'}.get(cmd.trigger_type, cmd.trigger_type)

        detail_text = (f'平台: {platform_name} | 类型: {msg_type_name}\n'
                       f'触发: [{trigger_name}] "{cmd.trigger_value}"\n'
                       f'指令: {cmd.bluetooth_command} | 通道: {cmd.bluetooth_channel}')

        detail_label = Label(
            text=detail_text,
            color=COLORS['text_dim'], font_size=sp(13),
            size_hint_y=None, height=dp(75),
            halign='left', valign='top',
        )
        detail_label.bind(size=lambda *x: detail_label.setter('text_size')(detail_label, detail_label.size))

        # 按钮行
        btn_row = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(40))
        trigger_btn = Button(text='手动触发', size_hint_x=0.34,
                           background_color=COLORS['success'], color=(1,1,1,1),
                           font_size=sp(13), background_normal='', background_down='')
        edit_btn = Button(text='编辑', size_hint_x=0.33,
                        background_color=COLORS['primary'], color=(1,1,1,1),
                        font_size=sp(13), background_normal='', background_down='')
        del_btn = Button(text='删除', size_hint_x=0.33,
                       background_color=COLORS['accent'], color=(1,1,1,1),
                       font_size=sp(13), background_normal='', background_down='')

        trigger_btn.bind(on_release=lambda b, c=cmd: self._manual_trigger(c))
        edit_btn.bind(on_release=lambda b, c=cmd: self._show_edit_dialog(c))
        del_btn.bind(on_release=lambda b, c=cmd: self._delete_command(c))

        btn_row.add_widget(trigger_btn)
        btn_row.add_widget(edit_btn)
        btn_row.add_widget(del_btn)

        card.clear_widgets()
        card.add_widget(name_row)
        card.add_widget(detail_label)
        card.add_widget(btn_row)
        return card

    def _toggle_command(self, cmd, enabled):
        cmd.enabled = enabled
        self.app.settings.update_command(cmd)
        self.app.engine.reload_rules()

    def _manual_trigger(self, cmd):
        self.app.engine.manual_trigger(cmd)
        self.app.show_snack(f'已手动触发: {cmd.name}')

    def _delete_command(self, cmd):
        self.app.settings.delete_command(cmd.id)
        self.app.engine.reload_rules()
        self.refresh_list()
        self.app.show_snack(f'已删除: {cmd.name}')

    def _show_add_dialog(self, btn):
        self._show_edit_dialog(None)

    def _show_edit_dialog(self, cmd):
        is_edit = cmd is not None
        CommandRule = _models['CommandRule']

        content = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(15))
        scroll = ScrollView(size_hint=(1, 1))
        form = BoxLayout(orientation='vertical', spacing=dp(8), size_hint_y=None)
        form.bind(minimum_height=form.setter('height'))

        # 表单字段
        name_input = TextInput(hint_text='规则名称', size_hint_y=None, height=dp(40),
                              background_color=COLORS['bg'], foreground_color=COLORS['text'],
                              hint_text_color=COLORS['text_dim'], font_size=sp(14),
                              multiline=False, padding=(dp(10), dp(10)))
        name_input.text = cmd.name if is_edit else ''

        platform_spinner = Spinner(
            text='所有平台' if (not is_edit or cmd.platform == 'all') else PLATFORMS.get(cmd.platform, ('',''))[0],
            values=['所有平台', '抖音', '快手', '小红书', 'TikTok'],
            size_hint_y=None, height=dp(40),
            background_color=COLORS['bg'], color=COLORS['text'], font_size=sp(14),
            sync_height=True,
        )

        msg_type_spinner = Spinner(
            text='评论' if (not is_edit or cmd.msg_type == 'comment') else
                  {'gift': '礼物', 'like': '点赞', 'follow': '关注', 'enter': '进场'}.get(cmd.msg_type, '评论'),
            values=['评论', '礼物', '点赞', '关注', '进场'],
            size_hint_y=None, height=dp(40),
            background_color=COLORS['bg'], color=COLORS['text'], font_size=sp(14),
            sync_height=True,
        )

        trigger_spinner = Spinner(
            text='精确匹配' if (not is_edit or cmd.trigger_type == 'exact') else
                  {'contains': '包含', 'regex': '正则', 'gift_name': '礼物名称', 'gift_count': '礼物数量'}.get(cmd.trigger_type, '精确匹配'),
            values=['精确匹配', '包含', '正则', '礼物名称', '礼物数量'],
            size_hint_y=None, height=dp(40),
            background_color=COLORS['bg'], color=COLORS['text'], font_size=sp(14),
            sync_height=True,
        )

        trigger_input = TextInput(hint_text='触发值 (如: 开灯)', size_hint_y=None, height=dp(40),
                                 background_color=COLORS['bg'], foreground_color=COLORS['text'],
                                 hint_text_color=COLORS['text_dim'], font_size=sp(14),
                                 multiline=False, padding=(dp(10), dp(10)))
        trigger_input.text = cmd.trigger_value if is_edit else ''

        bt_cmd_input = TextInput(hint_text='蓝牙指令(hex, 如 A00101A2)', size_hint_y=None, height=dp(40),
                                background_color=COLORS['bg'], foreground_color=COLORS['text'],
                                hint_text_color=COLORS['text_dim'], font_size=sp(14),
                                multiline=False, padding=(dp(10), dp(10)))
        bt_cmd_input.text = cmd.bluetooth_command if is_edit else ''

        channel_input = TextInput(hint_text='通道号 (1-8)', size_hint_y=None, height=dp(40),
                                 background_color=COLORS['bg'], foreground_color=COLORS['text'],
                                 hint_text_color=COLORS['text_dim'], font_size=sp(14),
                                 multiline=False, padding=(dp(10), dp(10)))
        channel_input.text = str(cmd.bluetooth_channel) if is_edit else '1'

        action_spinner = Spinner(
            text='单次发送' if (not is_edit or cmd.action_type == 'send_once') else
                  {'pulse': '脉冲', 'toggle': '切换'}.get(cmd.action_type, '单次发送'),
            values=['单次发送', '脉冲', '切换'],
            size_hint_y=None, height=dp(40),
            background_color=COLORS['bg'], color=COLORS['text'], font_size=sp(14),
            sync_height=True,
        )

        min_count_input = TextInput(hint_text='最小数量(礼物模式, 如1)', size_hint_y=None, height=dp(40),
                                   background_color=COLORS['bg'], foreground_color=COLORS['text'],
                                   hint_text_color=COLORS['text_dim'], font_size=sp(14),
                                   multiline=False, padding=(dp(10), dp(10)))
        min_count_input.text = str(cmd.min_count) if is_edit else '1'

        cooldown_input = TextInput(hint_text='冷却时间(ms, 0=不限制)', size_hint_y=None, height=dp(40),
                                  background_color=COLORS['bg'], foreground_color=COLORS['text'],
                                  hint_text_color=COLORS['text_dim'], font_size=sp(14),
                                  multiline=False, padding=(dp(10), dp(10)))
        cooldown_input.text = str(cmd.cooldown) if is_edit else '0'

        form.add_widget(Label(text='规则名称', color=COLORS['text'], size_hint_y=None, height=dp(25),
                             font_size=sp(13), halign='left', valign='middle'))
        form.add_widget(name_input)
        form.add_widget(Label(text='平台', color=COLORS['text'], size_hint_y=None, height=dp(25),
                             font_size=sp(13), halign='left', valign='middle'))
        form.add_widget(platform_spinner)
        form.add_widget(Label(text='消息类型', color=COLORS['text'], size_hint_y=None, height=dp(25),
                             font_size=sp(13), halign='left', valign='middle'))
        form.add_widget(msg_type_spinner)
        form.add_widget(Label(text='触发方式', color=COLORS['text'], size_hint_y=None, height=dp(25),
                             font_size=sp(13), halign='left', valign='middle'))
        form.add_widget(trigger_spinner)
        form.add_widget(Label(text='触发值', color=COLORS['text'], size_hint_y=None, height=dp(25),
                             font_size=sp(13), halign='left', valign='middle'))
        form.add_widget(trigger_input)
        form.add_widget(Label(text='蓝牙指令(hex)', color=COLORS['text'], size_hint_y=None, height=dp(25),
                             font_size=sp(13), halign='left', valign='middle'))
        form.add_widget(bt_cmd_input)
        form.add_widget(Label(text='通道号', color=COLORS['text'], size_hint_y=None, height=dp(25),
                             font_size=sp(13), halign='left', valign='middle'))
        form.add_widget(channel_input)
        form.add_widget(Label(text='动作类型', color=COLORS['text'], size_hint_y=None, height=dp(25),
                             font_size=sp(13), halign='left', valign='middle'))
        form.add_widget(action_spinner)
        form.add_widget(Label(text='最小数量(礼物模式)', color=COLORS['text'], size_hint_y=None, height=dp(25),
                             font_size=sp(13), halign='left', valign='middle'))
        form.add_widget(min_count_input)
        form.add_widget(Label(text='冷却时间(ms)', color=COLORS['text'], size_hint_y=None, height=dp(25),
                             font_size=sp(13), halign='left', valign='middle'))
        form.add_widget(cooldown_input)

        scroll.add_widget(form)
        content.add_widget(scroll)

        btn_row = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(45))
        save_btn = Button(text='保存', size_hint_x=0.5,
                         background_color=COLORS['success'], color=(1,1,1,1),
                         font_size=sp(15), background_normal='', background_down='')
        cancel_btn = Button(text='取消', size_hint_x=0.5,
                           background_color=COLORS['accent'], color=(1,1,1,1),
                           font_size=sp(15), background_normal='', background_down='')
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        content.add_widget(btn_row)

        popup = Popup(
            title='新增指令' if not is_edit else '编辑指令',
            content=content, size_hint=(0.95, 0.85)
        )

        def _save(instance):
            # 映射
            platform_map = {'所有平台': 'all', '抖音': 'douyin', '快手': 'kuaishou',
                           '小红书': 'xiaohongshu', 'TikTok': 'tiktok'}
            msg_type_map = {'评论': 'comment', '礼物': 'gift', '点赞': 'like',
                           '关注': 'follow', '进场': 'enter'}
            trigger_map = {'精确匹配': 'exact', '包含': 'contains', '正则': 'regex',
                          '礼物名称': 'gift_name', '礼物数量': 'gift_count'}
            action_map = {'单次发送': 'send_once', '脉冲': 'pulse', '切换': 'toggle'}

            rule = CommandRule(
                id=cmd.id if is_edit else None,
                name=name_input.text.strip() or '未命名规则',
                enabled=cmd.enabled if is_edit else True,
                platform=platform_map.get(platform_spinner.text, 'all'),
                msg_type=msg_type_map.get(msg_type_spinner.text, 'comment'),
                trigger_type=trigger_map.get(trigger_spinner.text, 'exact'),
                trigger_value=trigger_input.text.strip(),
                bluetooth_command=bt_cmd_input.text.strip(),
                bluetooth_channel=int(channel_input.text.strip() or '1'),
                action_type=action_map.get(action_spinner.text, 'send_once'),
                min_count=int(min_count_input.text.strip() or '1'),
                cooldown=int(cooldown_input.text.strip() or '0'),
            )
            self.app.settings.update_command(rule)
            self.app.engine.reload_rules()
            self.refresh_list()
            popup.dismiss()
            self.app.show_snack(f'已{"更新" if is_edit else "新增"}指令: {rule.name}')

        save_btn.bind(on_release=_save)
        cancel_btn.bind(on_release=popup.dismiss)
        popup.open()


class MonitorTab(BoxLayout):
    """实时监控页"""
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'
        self.padding = dp(15)
        self.spacing = dp(10)

        title = Label(
            text='[b]实时监控[/b]', markup=True,
            color=COLORS['text'], font_size=sp(20),
            size_hint_y=None, height=dp(40),
            halign='left', valign='middle',
        )
        title.bind(size=lambda *x: title.setter('text_size')(title, title.size))
        self.add_widget(title)

        # 统计栏
        self.stats_label = Label(
            text='消息: 0 | 触发: 0 | 错误: 0',
            color=COLORS['text_dim'], font_size=sp(14),
            size_hint_y=None, height=dp(35),
            halign='center', valign='middle',
        )
        self.stats_label.bind(size=lambda *x: self.stats_label.setter('text_size')(self.stats_label, self.stats_label.size))
        self.add_widget(self.stats_label)

        # 清除按钮
        clear_btn = Button(
            text='清空消息',
            size_hint_y=None, height=dp(38),
            background_color=COLORS['accent'],
            color=(1,1,1,1), font_size=sp(14),
            background_normal='', background_down='',
        )
        clear_btn.bind(on_release=self._clear_messages)
        self.add_widget(clear_btn)

        # 消息列表
        self.scroll = ScrollView(size_hint=(1, 1))
        self.msg_container = BoxLayout(orientation='vertical', spacing=dp(6), size_hint_y=None)
        self.msg_container.bind(minimum_height=self.msg_container.setter('height'))
        self.scroll.add_widget(self.msg_container)
        self.add_widget(self.scroll)

        # 定时刷新统计
        Clock.schedule_interval(self._update_stats, 2.0)

    def add_message(self, msg):
        """添加消息到列表 (主线程调用)"""
        # 限制显示条数
        if len(self.msg_container.children) > 200:
            self.msg_container.remove_widget(self.msg_container.children[-1])

        MessageType = _models['MessageType']
        color_map = {
            MessageType.COMMENT: COLORS['text'],
            MessageType.GIFT: COLORS['warning'],
            MessageType.LIKE: COLORS['primary'],
            MessageType.FOLLOW: COLORS['success'],
            MessageType.ENTER: COLORS['text_dim'],
            MessageType.SYSTEM: COLORS['accent'],
        }
        text_color = color_map.get(msg.msg_type, COLORS['text'])

        msg_label = Label(
            text=msg.display_text,
            color=text_color, font_size=sp(13),
            size_hint_y=None, height=dp(32),
            halign='left', valign='middle',
            text_size=(None, dp(32)),
        )
        msg_label.bind(size=lambda *x: msg_label.setter('text_size')(msg_label, (msg_label.width - dp(20), dp(32))))
        self.msg_container.add_widget(msg_label)

        # 滚动到底部
        Clock.schedule_once(lambda dt: setattr(self.scroll, 'scroll_y', 0), 0)

    def _update_stats(self, dt):
        stats = self.app.engine.get_stats()
        self.stats_label.text = (f'消息: {stats["total_messages"]} | '
                                f'触发: {stats["total_triggers"]} | '
                                f'错误: {stats["total_errors"]}')

    def _clear_messages(self, btn):
        self.msg_container.clear_widgets()


class DebugTab(BoxLayout):
    """调试日志页"""
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'
        self.padding = dp(15)
        self.spacing=dp(10)

        title = Label(
            text='[b]调试日志[/b]', markup=True,
            color=COLORS['text'], font_size=sp(20),
            size_hint_y=None, height=dp(40),
            halign='left', valign='middle',
        )
        title.bind(size=lambda *x: title.setter('text_size')(title, title.size))
        self.add_widget(title)

        # Tab切换: 日志/触发记录/指令测试
        self.tab_panel = TabbedPanel(size_hint=(1, 1))
        self.tab_panel.do_default_tab = False

        # 日志tab
        log_tab = TabbedPanelItem(text='系统日志')
        log_tab.content = self._build_log_panel()
        self.tab_panel.add_widget(log_tab)

        # 触发记录tab
        trigger_tab = TabbedPanelItem(text='触发记录')
        trigger_tab.content = self._build_trigger_panel()
        self.tab_panel.add_widget(trigger_tab)

        # 指令测试tab
        test_tab = TabbedPanelItem(text='指令测试')
        test_tab.content = self._build_test_panel()
        self.tab_panel.add_widget(test_tab)

        self.tab_panel.default_tab = log_tab
        self.add_widget(self.tab_panel)

        # 定时刷新日志
        Clock.schedule_interval(self._refresh_log, 1.0)
        Clock.schedule_interval(self._refresh_triggers, 3.0)

    def _build_log_panel(self):
        layout = BoxLayout(orientation='vertical', spacing=dp(8))
        self.log_scroll = ScrollView(size_hint=(1, 1))
        self.log_container = BoxLayout(orientation='vertical', spacing=dp(4), size_hint_y=None)
        self.log_container.bind(minimum_height=self.log_container.setter('height'))
        self.log_scroll.add_widget(self.log_container)
        layout.add_widget(self.log_scroll)

        btn_row = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(40))
        clear_btn = Button(text='清空', size_hint_x=0.5,
                          background_color=COLORS['accent'], color=(1,1,1,1),
                          font_size=sp(14), background_normal='', background_down='')
        refresh_btn = Button(text='刷新', size_hint_x=0.5,
                            background_color=COLORS['primary'], color=(1,1,1,1),
                            font_size=sp(14), background_normal='', background_down='')
        clear_btn.bind(on_release=lambda b: self.log_container.clear_widgets())
        refresh_btn.bind(on_release=lambda b: self._refresh_log(0))
        btn_row.add_widget(clear_btn)
        btn_row.add_widget(refresh_btn)
        layout.add_widget(btn_row)
        return layout

    def _build_trigger_panel(self):
        layout = BoxLayout(orientation='vertical', spacing=dp(8))
        self.trigger_scroll = ScrollView(size_hint=(1, 1))
        self.trigger_container = BoxLayout(orientation='vertical', spacing=dp(6), size_hint_y=None)
        self.trigger_container.bind(minimum_height=self.trigger_container.setter('height'))
        self.trigger_scroll.add_widget(self.trigger_container)
        layout.add_widget(self.trigger_scroll)

        refresh_btn = Button(text='刷新触发记录', size_hint_y=None, height=dp(40),
                            background_color=COLORS['primary'], color=(1,1,1,1),
                            font_size=sp(14), background_normal='', background_down='')
        refresh_btn.bind(on_release=lambda b: self._refresh_triggers(0))
        layout.add_widget(refresh_btn)
        return layout

    def _build_test_panel(self):
        layout = BoxLayout(orientation='vertical', spacing=dp(12), padding=dp(10))

        layout.add_widget(Label(text='手动发送蓝牙指令', color=COLORS['text'],
                               font_size=sp(16), size_hint_y=None, height=dp(35)))

        cmd_input = TextInput(
            hint_text='十六进制指令 (如 A00101A2)',
            size_hint_y=None, height=dp(45),
            background_color=COLORS['bg'], foreground_color=COLORS['text'],
            hint_text_color=COLORS['text_dim'], font_size=sp(15),
            multiline=False, padding=(dp(10), dp(12)),
        )
        layout.add_widget(cmd_input)

        channel_input = TextInput(
            hint_text='通道号 (默认1)',
            size_hint_y=None, height=dp(45),
            background_color=COLORS['bg'], foreground_color=COLORS['text'],
            hint_text_color=COLORS['text_dim'], font_size=sp(15),
            multiline=False, padding=(dp(10), dp(12)),
        )
        channel_input.text = '1'
        layout.add_widget(channel_input)

        send_btn = Button(
            text='发送指令',
            size_hint_y=None, height=dp(48),
            background_color=COLORS['success'], color=(1,1,1,1),
            font_size=sp(16), background_normal='', background_down='',
        )

        def _send(bt):
            cmd = cmd_input.text.strip()
            if not cmd:
                self.app.show_snack('请输入指令')
                return
            ch = int(channel_input.text.strip() or '1')
            if self.app.engine.bluetooth and self.app.engine.bluetooth.is_connected:
                success = self.app.engine.bluetooth.send_command(cmd, ch)
                self.app.show_snack(f'发送{"成功" if success else "失败"}: {cmd}')
            else:
                self.app.show_snack('蓝牙未连接')

        send_btn.bind(on_release=_send)
        layout.add_widget(send_btn)

        # 快捷指令按钮
        layout.add_widget(Label(text='快捷指令', color=COLORS['text_dim'],
                               font_size=sp(14), size_hint_y=None, height=dp(30)))

        quick_btns = BoxLayout(orientation='horizontal', spacing=dp(8), size_hint_y=None, height=dp(45))
        on_btn = Button(text='全开', background_color=COLORS['success'], color=(1,1,1,1),
                       font_size=sp(14), background_normal='', background_down='')
        off_btn = Button(text='全关', background_color=COLORS['accent'], color=(1,1,1,1),
                        font_size=sp(14), background_normal='', background_down='')
        ch1_btn = Button(text='通道1', background_color=COLORS['primary'], color=(1,1,1,1),
                        font_size=sp(14), background_normal='', background_down='')
        ch2_btn = Button(text='通道2', background_color=COLORS['primary'], color=(1,1,1,1),
                        font_size=sp(14), background_normal='', background_down='')

        def _send_on(bt):
            if self.app.engine.bluetooth and self.app.engine.bluetooth.is_connected:
                cfg = self.app.settings.bluetooth_config
                self.app.engine.bluetooth.send_command(cfg.default_on_cmd, 1)
                self.app.show_snack(f'发送: {cfg.default_on_cmd}')
            else:
                self.app.show_snack('蓝牙未连接')

        def _send_off(bt):
            if self.app.engine.bluetooth and self.app.engine.bluetooth.is_connected:
                cfg = self.app.settings.bluetooth_config
                self.app.engine.bluetooth.send_command(cfg.default_off_cmd, 1)
                self.app.show_snack(f'发送: {cfg.default_off_cmd}')
            else:
                self.app.show_snack('蓝牙未连接')

        on_btn.bind(on_release=_send_on)
        off_btn.bind(on_release=_send_off)

        quick_btns.add_widget(on_btn)
        quick_btns.add_widget(off_btn)
        quick_btns.add_widget(ch1_btn)
        quick_btns.add_widget(ch2_btn)
        layout.add_widget(quick_btns)

        return layout

    def _refresh_log(self, dt):
        from utils.logger import get_logger
        history = get_logger().get_history()
        if not history:
            return

        current_count = len(self.log_container.children)
        # 只添加新日志
        if len(history) > current_count:
            new_logs = history[current_count:]
            for entry in new_logs[-50:]:  # 最多显示50条
                level = entry.get('level', 'INFO')
                color_map = {
                    'DEBUG': COLORS['text_dim'],
                    'INFO': COLORS['text'],
                    'WARNING': COLORS['warning'],
                    'ERROR': COLORS['accent'],
                    'CRITICAL': COLORS['accent'],
                }
                text_color = color_map.get(level, COLORS['text'])
                log_label = Label(
                    text=f"[{entry.get('time', '')}] {entry.get('message', '')}",
                    color=text_color, font_size=sp(12),
                    size_hint_y=None, height=dp(28),
                    halign='left', valign='middle',
                )
                log_label.bind(size=lambda *x: log_label.setter('text_size')(log_label, (log_label.width - dp(15), dp(28))))
                self.log_container.add_widget(log_label)

            # 滚动到底部
            Clock.schedule_once(lambda dt: setattr(self.log_scroll, 'scroll_y', 0), 0)

    def _refresh_triggers(self, dt):
        self.trigger_container.clear_widgets()
        triggers = self.app.db.get_recent_triggers(30)
        if not triggers:
            empty = Label(text='暂无触发记录', color=COLORS['text_dim'],
                         font_size=sp(14), size_hint_y=None, height=dp(50))
            self.trigger_container.add_widget(empty)
            return

        status_colors = {
            'SUCCESS': COLORS['success'],
            'FAILED': COLORS['accent'],
            'PULSE': COLORS['warning'],
            'TOGGLE_ON': COLORS['success'],
            'TOGGLE_OFF': COLORS['text_dim'],
            'SKIPPED': COLORS['text_dim'],
            'ERROR': COLORS['accent'],
        }

        for t in triggers:
            color = status_colors.get(t['status'], COLORS['text'])
            text = (f"[{t.get('datetime', '')}] {t.get('rule_name', '')}\n"
                    f"  消息: {t.get('trigger_message', '')[:40]}\n"
                    f"  指令: {t.get('bluetooth_command', '')} | 通道: {t.get('channel', '')}\n"
                    f"  状态: {t.get('status', '')} | {t.get('detail', '')[:30]}")
            label = Label(
                text=text, color=color, font_size=sp(12),
                size_hint_y=None, height=dp(80),
                halign='left', valign='top',
            )
            label.bind(size=lambda *x: label.setter('text_size')(label, (label.width - dp(15), dp(80))))
            self.trigger_container.add_widget(label)


class CrashScreen(BoxLayout):
    """崩溃错误显示页"""
    def __init__(self, error_text, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = dp(20)
        self.spacing = dp(10)

        title = Label(
            text='[b]应用启动出错[/b]',
            markup=True, color=COLORS['accent'],
            font_size=sp(22), size_hint_y=None, height=dp(50),
            halign='center', valign='middle',
        )
        title.bind(size=lambda *x: title.setter('text_size')(title, title.size))
        self.add_widget(title)

        info = Label(
            text='以下是错误信息，请截图反馈：',
            color=COLORS['text_dim'], font_size=sp(14),
            size_hint_y=None, height=dp(30),
            halign='center', valign='middle',
        )
        info.bind(size=lambda *x: info.setter('text_size')(info, info.size))
        self.add_widget(info)

        scroll = ScrollView(size_hint=(1, 1))
        error_label = Label(
            text=error_text,
            color=COLORS['text'], font_size=sp(12),
            size_hint_y=None,
            halign='left', valign='top',
            markup=False,
        )
        error_label.bind(
            width=lambda *x: error_label.setter('text_size')(error_label, (error_label.width - dp(10), None)),
            texture_size=lambda *x: setattr(error_label, 'height', error_label.texture_size[1])
        )
        scroll.add_widget(error_label)
        self.add_widget(scroll)


class LiveControlApp(App):
    """直播互动蓝牙控制台 - Android主应用"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def build(self):
        # 全局错误捕获
        try:
            return self._build_app()
        except Exception as e:
            err = traceback.format_exc()
            print(f"[FATAL] {err}", file=sys.stderr)
            return CrashScreen(f"{type(e).__name__}: {e}\n\n{err}")

    def _build_app(self):
        # 初始化核心模块（延迟导入）
        _init_modules()

        # 导入平台模块
        global PLATFORMS
        _import_platforms()
        PLATFORMS = _platforms_mod

        # 设置全局变量
        self.settings = _settings
        self.db = _db
        self.engine = _engine
        self.platform_status_labels = {}

        # 设置窗口
        Window.clearcolor = COLORS['bg']

        # 主布局 - 底部导航
        root = BoxLayout(orientation='vertical')

        # 内容区域
        self.content_area = BoxLayout(orientation='vertical', size_hint=(1, 0.92))

        # 默认显示平台页
        self.current_tab = 'platform'
        self.tabs = {}
        self._show_tab('platform')
        root.add_widget(self.content_area)

        # 底部导航栏
        nav_bar = BoxLayout(orientation='horizontal', size_hint=(1, 0.08),
                           spacing=1)
        nav_items = [
            ('platform', '📡 直播'),
            ('bluetooth', '📶 蓝牙'),
            ('command', '⚡ 指令'),
            ('monitor', '📊 监控'),
            ('debug', '🔧 调试'),
        ]
        for key, label in nav_items:
            btn = Button(
                text=label,
                background_color=COLORS['card'] if key != 'platform' else COLORS['primary'],
                color=(1, 1, 1, 1),
                font_size=sp(13),
                background_normal='', background_down='',
            )
            btn.bind(on_release=lambda b, k=key: self._show_tab(k))
            nav_bar.add_widget(btn)

        root.add_widget(nav_bar)
        return root

    def _show_tab(self, tab_key):
        """切换标签页"""
        self.content_area.clear_widgets()

        if tab_key not in self.tabs:
            if tab_key == 'platform':
                self.tabs[tab_key] = PlatformTab(self)
            elif tab_key == 'bluetooth':
                self.tabs[tab_key] = BluetoothTab(self)
            elif tab_key == 'command':
                self.tabs[tab_key] = CommandTab(self)
            elif tab_key == 'monitor':
                self.tabs[tab_key] = MonitorTab(self)
            elif tab_key == 'debug':
                self.tabs[tab_key] = DebugTab(self)

        self.content_area.add_widget(self.tabs[tab_key])
        self.current_tab = tab_key

    def on_platform_message(self, msg):
        """平台消息回调 (子线程调用)"""
        # 转发到引擎
        self.engine.on_message(msg)
        # 更新监控页UI
        Clock.schedule_once(lambda dt: self._update_monitor(msg), 0)

    def _update_monitor(self, msg):
        """更新监控页 (主线程)"""
        if 'monitor' in self.tabs:
            self.tabs['monitor'].add_message(msg)

    def show_snack(self, message):
        """显示提示消息"""
        Clock.schedule_once(lambda dt: self._show_snack_ui(message), 0)

    def _show_snack_ui(self, message):
        """在底部显示临时消息"""
        # 创建简单的弹出提示
        content = Label(text=message, color=COLORS['text'],
                       font_size=sp(14), size_hint_y=None, height=dp(50),
                       halign='center', valign='middle')
        content.bind(size=lambda *x: content.setter('text_size')(content, content.size))

        popup = Popup(content=content, size_hint=(0.7, 0.12),
                     auto_dismiss=True, separator_color=COLORS['primary'])
        popup.open()
        Clock.schedule_once(lambda dt: popup.dismiss(), 2.0)

    def on_stop(self):
        """应用退出清理"""
        try:
            self.engine.stop()
            if self.engine.bluetooth:
                self.engine.bluetooth.disconnect()
            for tab in self.tabs.values():
                if isinstance(tab, PlatformTab):
                    for platform in tab.platform_instances.values():
                        platform.disconnect()
        except Exception:
            pass


def main():
    app = LiveControlApp()
    app.run()


if __name__ == '__main__':
    main()
