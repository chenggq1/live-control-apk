[app]

# 应用信息
title = 直播互动蓝牙控制台
package.name = livecontrol
package.domain = org.livecontrol

# 源码目录
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

# 版本
version = 1.0.0

# 需求
requirements = python3,kivy,pyjnius,requests,websocket-client,sqlite3

# 方向
orientation = portrait

# 全屏
fullscreen = 0

# Android配置
android.api = 34
android.minapi = 24
android.arch = arm64-v8a,armeabi-v7a

# 权限
android.permissions = BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_CONNECT,BLUETOOTH_SCAN,INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,FOREGROUND_SERVICE

# 接收广播
android.browsable_categories = android.intent.category.BROWSABLE

# 预加载
android.allow_backup = True

# 图标 (可选，没有则使用默认)
# android.icon = icon.png

# 启动画面 (可选)
# presplash.filename = presplash.png

# 深色主题
android.allow_dark_theme = True

# 编译选项
python.cpython = auto

# 日志
log_level = 2

# 构建模式
android.debuggable = False

#.gradle版本
android.gradle_version = 7.6

#
# Buildozer特定配置
#

# 构建目录
build_dir = .buildozer

# 是否在构建时编译Python
no-compile-pyo = False

# 包含的私有文件
# private.imports = 

# JNIus配置
android.add_src = 

# Java编译
android.add_jars = 
android.add_aars = 

# 签名 (发布时需要设置)
# android.numeric_version = 1
# android.release_artifact = aab

[buildozer]

# 构建后自动清理
warn_on_root = 1
