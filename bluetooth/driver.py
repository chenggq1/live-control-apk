"""
Android蓝牙驱动 - 使用pyjnius访问Android原生Bluetooth API
支持SPP串口和BLE两种连接方式，控制物理继电器开关
"""
import threading
import time
from typing import Callable, Optional
from engine.models import BluetoothConfig
from utils.logger import get_logger

logger = get_logger().get_child('AndroidBT')

# 检测是否在Android环境
IS_ANDROID = False
try:
    from jnius import autoclass, cast, JavaClass, meta_method
    IS_ANDROID = True
    logger.info("pyjnius可用，运行在Android环境")
except ImportError:
    logger.warning("pyjnius不可用，蓝牙功能将受限")


class AndroidBluetoothDriver:
    """Android蓝牙驱动 - SPP + BLE"""

    def __init__(self, config: BluetoothConfig):
        self.config: BluetoothConfig = config
        self._connected: bool = False
        self._lock = threading.Lock()
        self._socket = None          # SPP BluetoothSocket
        self._output_stream = None
        self._input_stream = None
        self._gatt = None            # BLE BluetoothGatt
        self._gatt_callback = None
        self._ble_char = None
        self._connect_callback: Optional[Callable[[bool, str], None]] = None
        self._pulse_threads: list = []
        self._adapter = None
        self._device = None

        if IS_ANDROID:
            self._init_adapter()

    def _init_adapter(self):
        """初始化蓝牙适配器"""
        try:
            BluetoothManager = autoclass('android.bluetooth.BluetoothManager')
            context = autoclass('org.kivy.android.PythonActivity').mActivity
            manager = context.getSystemService(context.BLUETOOTH_SERVICE)
            self._adapter = manager.getAdapter()
            if self._adapter is None:
                logger.error("设备不支持蓝牙")
            elif not self._adapter.isEnabled():
                logger.warning("蓝牙未开启，尝试启用...")
                # 不能直接调用enable()，需要通过intent请求用户开启
            else:
                logger.info("蓝牙适配器就绪")
        except Exception as e:
            logger.error(f"初始化蓝牙适配器失败: {e}")

    @property
    def is_connected(self) -> bool:
        return self._connected

    def set_connect_callback(self, callback: Callable[[bool, str], None]):
        self._connect_callback = callback

    def _notify_connect(self, connected: bool, msg: str = ""):
        if self._connect_callback:
            try:
                self._connect_callback(connected, msg)
            except Exception:
                pass

    def request_enable_bluetooth(self) -> bool:
        """请求开启蓝牙"""
        if not IS_ANDROID or not self._adapter:
            return False
        try:
            if self._adapter.isEnabled():
                return True
            Intent = autoclass('android.content.Intent')
            context = autoclass('org.kivy.android.PythonActivity').mActivity
            intent = Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE)
            context.startActivityForResult(intent, 1)
            time.sleep(2)
            return self._adapter.isEnabled()
        except Exception as e:
            logger.error(f"请求开启蓝牙失败: {e}")
            return False

    def scan_paired_devices(self) -> list:
        """获取已配对设备列表"""
        devices = []
        if not IS_ANDROID or not self._adapter:
            logger.warning("蓝牙适配器不可用")
            return devices
        try:
            paired = self._adapter.getBondedDevices()
            for device in paired.toArray():
                devices.append({
                    'address': device.getAddress(),
                    'name': device.getName() or 'Unknown',
                })
            logger.info(f"找到 {len(devices)} 个已配对设备")
        except Exception as e:
            logger.error(f"扫描已配对设备失败: {e}")
        return devices

    def scan_ble_devices(self, timeout: float = 10.0) -> list:
        """扫描BLE设备"""
        devices = []
        if not IS_ANDROID or not self._adapter:
            return devices
        try:
            scanner = self._adapter.getBluetoothLeScanner()
            if scanner is None:
                logger.error("BLE扫描器不可用")
                return devices

            ScanSettings = autoclass('android.bluetooth.le.ScanSettings')
            ScanFilter = autoclass('android.bluetooth.le.ScanFilter')
            Builder = ScanSettings.Builder()
            builder = Builder.setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            settings = builder.build()

            found_devices = {}
            found_lock = threading.Lock()

            # 创建回调
            from jnius import PythonJavaClass, java_method

            class ScanCallback(PythonJavaClass):
                __javainterfaces__ = ['android/bluetooth/le/ScanCallback']
                __javacontext__ = 'app'

                @java_method('(Ljava/util/List;)V')
                def onScanResult(self, results):
                    try:
                        for result in results.toArray():
                            device = result.getDevice()
                            addr = device.getAddress()
                            name = device.getName() or 'Unknown'
                            with found_lock:
                                if addr not in found_devices:
                                    found_devices[addr] = {
                                        'address': addr,
                                        'name': name,
                                    }
                    except Exception as e:
                        logger.debug(f"扫描回调异常: {e}")

                @java_method('(I)V')
                def onScanFailed(self, errorCode):
                    logger.error(f"BLE扫描失败: {errorCode}")

            callback = ScanCallback()
            scanner.startScan(None, settings, callback)
            time.sleep(timeout)
            scanner.stopScan(callback)

            devices = list(found_devices.values())
            logger.info(f"BLE扫描找到 {len(devices)} 个设备")
        except Exception as e:
            logger.error(f"BLE扫描失败: {e}")
        return devices

    def connect(self) -> bool:
        """连接蓝牙设备"""
        with self._lock:
            if self._connected:
                logger.info("蓝牙已连接，跳过")
                return True

            if not IS_ANDROID:
                logger.error("非Android环境，无法连接蓝牙")
                self._notify_connect(False, "非Android环境")
                return False

            if not self._adapter or not self._adapter.isEnabled():
                if not self.request_enable_bluetooth():
                    self._notify_connect(False, "蓝牙未开启")
                    return False

            try:
                if self.config.connection_type == "serial":
                    return self._connect_spp()
                elif self.config.connection_type == "ble":
                    return self._connect_ble()
                else:
                    logger.error(f"未知连接类型: {self.config.connection_type}")
                    return False
            except Exception as e:
                logger.error(f"蓝牙连接失败: {e}")
                self._connected = False
                self._notify_connect(False, str(e))
                return False

    def _connect_spp(self) -> bool:
        """SPP串口连接 (HC-05/HC-06等)"""
        try:
            address = self.config.port  # 在Android上，port字段存设备MAC地址
            if not address:
                msg = "未设置蓝牙设备地址"
                logger.error(msg)
                self._notify_connect(False, msg)
                return False

            logger.info(f"正在连接SPP设备 {address}...")

            BluetoothDevice = autoclass('android.bluetooth.BluetoothDevice')
            UUID = autoclass('java.util.UUID')

            self._device = self._adapter.getRemoteDevice(address)
            if self._device is None:
                self._notify_connect(False, "设备不存在")
                return False

            # SPP UUID
            spp_uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
            self._socket = self._device.createRfcommSocketToServiceRecord(spp_uuid)

            # 取消扫描以加速连接
            try:
                self._adapter.cancelDiscovery()
            except Exception:
                pass

            self._socket.connect()

            # 获取IO流
            self._output_stream = self._socket.getOutputStream()
            self._input_stream = self._socket.getInputStream()

            self._connected = True
            device_name = self._device.getName() or address
            logger.info(f"SPP连接成功: {device_name}")
            self._notify_connect(True, f"已连接 {device_name}")
            return True

        except Exception as e:
            logger.error(f"SPP连接失败: {e}")
            self._connected = False
            self._notify_connect(False, f"SPP连接失败: {e}")
            self._close_socket()
            return False

    def _connect_ble(self) -> bool:
        """BLE连接"""
        try:
            address = self.config.ble_address
            if not address:
                msg = "未设置BLE设备地址"
                logger.error(msg)
                self._notify_connect(False, msg)
                return False

            logger.info(f"正在连接BLE设备 {address}...")

            BluetoothGattCallback = autoclass('android.bluetooth.BluetoothGattCallback')
            BluetoothGatt = autoclass('android.bluetooth.BluetoothGatt')
            BluetoothProfile = autoclass('android.bluetooth.BluetoothProfile')
            UUID = autoclass('java.util.UUID')

            self._device = self._adapter.getRemoteDevice(address)

            connected_event = threading.Event()
            connected_result = [False]

            from jnius import PythonJavaClass, java_method

            class GattCallback(PythonJavaClass):
                __javainterfaces__ = ['android/bluetooth/BluetoothGattCallback']
                __javacontext__ = 'app'

                @java_method('(Landroid/bluetooth/BluetoothGatt;II)V')
                def onConnectionStateChange(self, gatt, status, newState):
                    if newState == BluetoothProfile.STATE_CONNECTED:
                        logger.info("BLE已连接，发现服务...")
                        gatt.discoverServices()
                    elif newState == BluetoothProfile.STATE_DISCONNECTED:
                        logger.info("BLE已断开")
                        connected_result[0] = False
                        connected_event.set()

                @java_method('(Landroid/bluetooth/BluetoothGatt;I)V')
                def onServicesDiscovered(self, gatt, status):
                    logger.info(f"服务发现完成 status={status}")
                    if status == BluetoothGatt.GATT_SUCCESS:
                        connected_result[0] = True
                    else:
                        connected_result[0] = False
                    connected_event.set()

            self._gatt_callback = GattCallback()
            self._gatt = self._device.connectGatt(
                None, False, self._gatt_callback
            )

            # 等待连接和服务发现
            if connected_event.wait(timeout=15.0):
                if connected_result[0]:
                    # 查找特征值
                    service_uuid_str = self.config.ble_service_uuid or "0000ffe0-0000-1000-8000-00805f9b34fb"
                    char_uuid_str = self.config.ble_char_uuid or "0000ffe1-0000-1000-8000-00805f9b34fb"

                    services = self._gatt.getServices()
                    for service in services.toArray():
                        service_uuid = service.getUuid().toString().lower()
                        if service_uuid == service_uuid_str.lower():
                            chars = service.getCharacteristics()
                            for char in chars.toArray():
                                char_uuid = char.getUuid().toString().lower()
                                if char_uuid == char_uuid_str.lower():
                                    self._ble_char = char
                                    break
                            break

                    if self._ble_char is None:
                        # 取第一个可写特征
                        for service in services.toArray():
                            for char in service.getCharacteristics().toArray():
                                props = char.getProperties()
                                if props & 0x08:  # PROPERTY_WRITE
                                    self._ble_char = char
                                    break
                            if self._ble_char:
                                break

                    self._connected = True
                    logger.info(f"BLE连接成功: {address}")
                    self._notify_connect(True, f"已连接 {address}")
                    return True
                else:
                    self._notify_connect(False, "BLE服务发现失败")
                    return False
            else:
                self._notify_connect(False, "BLE连接超时")
                return False

        except Exception as e:
            logger.error(f"BLE连接失败: {e}")
            self._connected = False
            self._notify_connect(False, str(e))
            return False

    def _close_socket(self):
        """关闭SPP socket"""
        try:
            if self._socket:
                self._socket.close()
        except Exception:
            pass
        self._socket = None
        self._output_stream = None
        self._input_stream = None

    def disconnect(self):
        """断开连接"""
        with self._lock:
            self._connected = False

            for t in self._pulse_threads:
                if t.is_alive():
                    t.join(timeout=2.0)
            self._pulse_threads.clear()

            self._close_socket()

            if self._gatt:
                try:
                    self._gatt.disconnect()
                    self._gatt.close()
                except Exception:
                    pass
                self._gatt = None
                self._gatt_callback = None
                self._ble_char = None
                logger.info("BLE已断开")

            self._notify_connect(False, "已断开")

    def send_command(self, hex_cmd: str, channel: int = 1) -> bool:
        """发送蓝牙指令 (十六进制字符串)"""
        if not self._connected:
            logger.warning("蓝牙未连接，无法发送指令")
            return False

        try:
            cmd_bytes = bytes.fromhex(hex_cmd.replace(' ', ''))
        except ValueError as e:
            logger.error(f"无效的十六进制指令: {hex_cmd} - {e}")
            return False

        with self._lock:
            try:
                if self.config.connection_type == "serial" and self._output_stream:
                    # SPP: 通过OutputStream写入
                    Byte = autoclass('java.lang.Byte')
                    # 转为byte array
                    import array
                    arr = array.array('b', [b if b < 128 else b - 256 for b in cmd_bytes])
                    self._output_stream.write(cmd_bytes)
                    self._output_stream.flush()
                    logger.info(f"SPP发送指令: {hex_cmd} (通道{channel})")
                    return True

                elif self.config.connection_type == "ble" and self._gatt and self._ble_char:
                    # BLE: 写入特征值
                    BluetoothGattCharacteristic = autoclass('android.bluetooth.BluetoothGattCharacteristic')
                    # 设置特征值
                    self._ble_char.setValue(cmd_bytes)
                    self._ble_char.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE)
                    self._gatt.writeCharacteristic(self._ble_char)
                    logger.info(f"BLE发送指令: {hex_cmd} (通道{channel})")
                    return True
            except Exception as e:
                logger.error(f"发送指令失败: {e}")
                self._connected = False
                self._notify_connect(False, f"发送失败: {e}")
                return False
        return False

    def send_pulse(self, on_cmd: str, off_cmd: str, duration_ms: int, channel: int = 1):
        """脉冲模式: 开 -> 等待 -> 关"""
        def _pulse():
            logger.info(f"脉冲触发: 通道{channel}, 持续{duration_ms}ms")
            self.send_command(on_cmd, channel)
            time.sleep(duration_ms / 1000.0)
            self.send_command(off_cmd, channel)
            logger.info(f"脉冲完成: 通道{channel}")

        t = threading.Thread(target=_pulse, daemon=True)
        self._pulse_threads.append(t)
        t.start()

    def send_channel_on(self, channel: int = 1) -> bool:
        cmd = self.config.default_on_cmd
        return self.send_command(cmd, channel)

    def send_channel_off(self, channel: int = 1) -> bool:
        cmd = self.config.default_off_cmd
        return self.send_command(cmd, channel)

    def test_command(self, hex_cmd: str) -> bool:
        logger.info(f"[测试] 发送指令: {hex_cmd}")
        return self.send_command(hex_cmd)


# 兼容性别名 - 让command_engine可以无缝导入
BluetoothDriver = AndroidBluetoothDriver
