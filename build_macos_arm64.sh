#!/bin/bash
set -euo pipefail

# 构建仅适用于 Apple Silicon（M1/M2/M3/M4/M 系列）的 NoiseGuard.app 和 DMG。
cd "$(dirname "$0")" || exit 1

if [[ "$(uname -m)" != "arm64" ]]; then
    echo "错误：必须在 Apple Silicon Mac（arm64）上构建。" >&2
    exit 1
fi

VERSION="${VERSION:-1.0.0}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
BUILD_VENV=".build-venv"
APP_PATH="dist/NoiseGuard.app"
DMG_NAME="NoiseGuard-v${VERSION}-macOS-Apple-Silicon-arm64.dmg"
DMG_PATH="dist/${DMG_NAME}"
DMG_STAGING="build/dmg-arm64"
PLIST_PATH="${APP_PATH}/Contents/Info.plist"

"${PYTHON_BIN}" -m venv "${BUILD_VENV}"
"${BUILD_VENV}/bin/python" -m pip install --upgrade pip
"${BUILD_VENV}/bin/python" -m pip install -r requirements.txt "pyinstaller>=6.14,<7"

rm -rf build dist

"${BUILD_VENV}/bin/pyinstaller" \
    --noconfirm \
    --clean \
    --windowed \
    --name "NoiseGuard" \
    --target-architecture arm64 \
    --osx-bundle-identifier "io.github.zq500480.noiseguard" \
    noise_guard.py

/usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string NoiseGuard 需要使用麦克风检测低频噪音。" "${PLIST_PATH}" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :NSMicrophoneUsageDescription NoiseGuard 需要使用麦克风检测低频噪音。" "${PLIST_PATH}"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string ${VERSION}" "${PLIST_PATH}" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString ${VERSION}" "${PLIST_PATH}"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string ${VERSION}" "${PLIST_PATH}" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${VERSION}" "${PLIST_PATH}"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 14.0" "${PLIST_PATH}" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion 14.0" "${PLIST_PATH}"

# 无 Apple Developer 证书时使用 ad-hoc 签名，保证 App 内部代码签名结构完整。
codesign --force --deep --sign - "${APP_PATH}"

mkdir -p "${DMG_STAGING}"
ditto "${APP_PATH}" "${DMG_STAGING}/NoiseGuard.app"
ln -s /Applications "${DMG_STAGING}/Applications"
hdiutil create \
    -volname "NoiseGuard M芯片版" \
    -srcfolder "${DMG_STAGING}" \
    -ov \
    -format UDZO \
    "${DMG_PATH}"

echo "构建完成：${DMG_PATH}"
