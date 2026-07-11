#!/usr/bin/env bash
# ============================================================
# APK构建脚本 - 在WSL2 Ubuntu中运行
# ============================================================
set -e

echo "=========================================="
echo "  直播互动蓝牙控制台 - APK构建脚本"
echo "=========================================="
echo ""

# 1. 安装系统依赖
echo "[1/6] 安装系统依赖..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git zip unzip openjdk-17-jdk autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev

# 2. 安装Buildozer
echo ""
echo "[2/6] 安装Buildozer..."
pip3 install --user buildozer Cython==0.29.36

# 3. 添加PATH
export PATH="$HOME/.local/bin:$PATH"
export JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"
export ANDROID_HOME="$HOME/.buildozer/android/platform/android-sdk"

# 4. 确保在正确目录
echo ""
echo "[3/6] 准备源码..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 5. 清理旧构建
echo ""
echo "[4/6] 清理旧构建文件..."
rm -rf .buildozer
rm -rf bin

# 6. 构建APK
echo ""
echo "[5/6] 开始构建APK (首次构建约需30-40分钟)..."
echo "  - 下载Android SDK/NDK"
echo "  - 编译Python for Android"
echo "  - 打包APK"
echo ""
buildozer -v android debug 2>&1 | tee build_log.txt

# 检查结果
echo ""
echo "[6/6] 检查构建结果..."
APK_FILE=$(ls bin/*.apk 2>/dev/null | head -1)
if [ -n "$APK_FILE" ]; then
    echo ""
    echo "=========================================="
    echo "  构建成功!"
    echo "=========================================="
    echo ""
    echo "APK文件: $APK_FILE"
    echo "文件大小: $(du -h "$APK_FILE" | cut -f1)"
    echo ""
    echo "将APK传输到手机安装即可。"
    echo "=========================================="
else
    echo ""
    echo "=========================================="
    echo "  构建失败 - 请查看 build_log.txt"
    echo "=========================================="
    exit 1
fi
