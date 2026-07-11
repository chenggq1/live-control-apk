# ============================================================
# Google Colab APK 构建脚本
# 使用方法:
#   1. 打开 https://colab.research.google.com
#   2. 上传此文件和 android_app.zip
#   3. 运行所有单元格
#   4. 下载生成的 APK
# ============================================================

# ====== 第1步: 安装构建依赖 ======
import subprocess
import os

print("=" * 50)
print("  第1步: 安装构建依赖...")
print("=" * 50)

subprocess.run(["apt-get", "update", "-qq"], check=True)
subprocess.run([
    "apt-get", "install", "-y", "-qq",
    "openjdk-17-jdk", "autoconf", "libtool", "pkg-config",
    "zlib1g-dev", "libncurses5-dev", "libncursesw5-dev",
    "libtinfo5", "cmake", "libffi-dev", "libssl-dev",
    "git", "zip", "unzip",
], check=True)

subprocess.run(["pip", "install", "buildozer", "Cython==0.29.36"], check=True)

os.environ['JAVA_HOME'] = '/usr/lib/jvm/java-17-openjdk-amd64'

print("\n依赖安装完成!\n")

# ====== 第2步: 上传项目文件 ======
print("=" * 50)
print("  第2步: 上传项目文件...")
print("  请选择 android_app.zip 文件上传")
print("=" * 50)

from google.colab import files
uploaded = files.upload()

zip_name = list(uploaded.keys())[0]
print(f"\n已上传: {zip_name}")

# 解压
subprocess.run(["unzip", "-o", zip_name, "-d", "/content/"], check=True)
print("解压完成!\n")

# ====== 第3步: 构建APK ======
print("=" * 50)
print("  第3步: 开始构建APK (约需15-30分钟)...")
print("=" * 50)

os.chdir('/content/android_app')

# 清理旧构建
subprocess.run(["rm", "-rf", ".buildozer", "bin"], cwd='/content/android_app')

# 运行buildozer
result = subprocess.run(
    ["buildozer", "-v", "android", "debug"],
    cwd='/content/android_app',
    capture_output=False,
)

# ====== 第4步: 下载APK ======
print("\n" + "=" * 50)
print("  第4步: 下载APK")
print("=" * 50)

import glob
apk_files = glob.glob('/content/android_app/bin/*.apk')

if apk_files:
    apk_path = apk_files[0]
    apk_size = os.path.getsize(apk_path) / (1024 * 1024)
    print(f"\n构建成功!")
    print(f"APK文件: {os.path.basename(apk_path)}")
    print(f"文件大小: {apk_size:.1f} MB")
    print(f"\n正在下载...")
    files.download(apk_path)
else:
    print("\n构建失败 - 请检查上方日志")
    print("常见问题:")
    print("  1. 确保上传的zip包含完整的android_app目录")
    print("  2. 检查buildozer.spec配置是否正确")
    print("  3. 尝试重新运行此单元格")
