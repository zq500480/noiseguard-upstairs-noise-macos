#!/bin/bash
# NoiseGuard 应用启动器
# 强制 arm64:双击经 LaunchServices 启动时,通用二进制默认会跑 x86_64 切片,
# 导致加载 arm64 原生扩展失败,这里用 arch -arm64 钉死架构。
cd "$HOME/noise-guard" || exit 1
exec arch -arm64 ./.venv/bin/python noise_guard.py
