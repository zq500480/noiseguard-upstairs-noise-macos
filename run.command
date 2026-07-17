#!/bin/bash
# 双击运行 NoiseGuard(楼上噪音 AI 反击)
cd "$(dirname "$0")"
exec ./.venv/bin/python noise_guard.py
