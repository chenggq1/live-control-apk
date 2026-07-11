# 直播互动蓝牙控制台 - Android APK

## 项目简介

完全在手机上独立运行的直播互动蓝牙控制应用。抓取抖音/快手/小红书/TikTok直播间的评论和礼物，通过指令规则触发蓝牙硬件开关。

## 项目结构

```
android_app/
├── main.py                  # Kivy移动端主应用（UI + 入口）
├── android_app.zip          # 打包好的项目压缩包（供Colab上传）
├── colab_build.py           # Google Colab云构建脚本
├── build_apk.sh             # WSL本地构建脚本
├── buildozer.spec           # APK构建配置
├── .github/workflows/
│   └── build-apk.yml        # GitHub Actions自动构建
├── bluetooth/
│   └── driver.py            # Android蓝牙驱动（pyjnius原生API）
├── engine/
│   ├── models.py            # 数据模型
│   └── command_engine.py    # 指令匹配引擎
├── platforms/
│   ├── base.py              # 平台基类
│   ├── douyin.py            # 抖音抓取
│   ├── tiktok.py            # TikTok抓取
│   ├── kuaishou.py          # 快手抓取
│   └── xiaohongshu.py       # 小红书抓取
├── config/
│   ├── settings.py          # 配置管理（Android适配）
│   └── database.py          # SQLite数据库（Android适配）
└── utils/
    ├── protobuf_lite.py     # Protobuf解析器
    └── logger.py            # 日志系统
```

## 构建APK（两种方式）

### 方式一：Google Colab云构建（推荐，无需安装任何环境）

1. 双击桌面 **「APK云构建.bat」**
2. 脚本会自动打包项目并打开Colab网页
3. 在Colab中上传 `colab_build.py` 作为笔记本
4. 运行所有单元格，上传 `android_app.zip`
5. 等待15-30分钟构建完成
6. APK自动下载到电脑

### 方式二：WSL2本地构建

1. **重启电脑**（已为你启用WSL功能，重启后生效）
2. 双击桌面 **「APK本地构建.bat」**
3. 脚本自动安装Ubuntu、buildozer、编译APK
4. 首次构建约需30-40分钟

### 方式三：GitHub Actions

1. 将 `android_app` 目录推送到GitHub仓库
2. GitHub Actions自动触发构建
3. 在Actions页面下载APK artifact

## 安装APK到手机

1. 将构建好的 `.apk` 文件传到手机
2. 手机设置中允许「安装未知来源应用」
3. 点击APK文件安装
4. 打开应用，授予蓝牙和网络权限

## 使用流程

1. **蓝牙设置页**：扫描已配对的蓝牙设备 → 选择设备 → 连接
2. **直播页**：输入直播间链接 → 连接（支持抖音/快手/小红书/TikTok）
3. **指令管理页**：新增指令规则（如评论"开灯"→发送蓝牙指令A00101A2）
4. **监控页**：实时查看弹幕消息和触发记录
5. **调试页**：查看系统日志、手动测试蓝牙指令

## 蓝牙模块兼容性

- **SPP串口模式**：HC-05、HC-06、JDY-31等SPP蓝牙模块
- **BLE模式**：支持BLE的蓝牙模块（需指定Service/Char UUID）
- **继电器控制**：支持十六进制指令控制多通道继电器

## 技术栈

- UI框架：Kivy (纯Python跨平台GUI)
- 蓝牙：pyjnius (Android原生API)
- 网络：websocket-client + requests
- 协议解析：自定义Protobuf解析器
- 数据存储：SQLite + JSON配置
- 构建：Buildozer + Python-for-Android
