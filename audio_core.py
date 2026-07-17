#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audio_core — 与界面无关的 DSP 核心。
采集(蓝牙)麦克风 -> FFT 分析低频段 -> 冲击判定。界面(Qt)只消费这里的指标。
"""

import os
import time
import threading
from collections import deque

import numpy as np
import sounddevice as sd
import soundfile as sf

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOUND = os.path.join(APP_DIR, "咚咚.wav")

# ---- DSP 参数 ----
BLOCK = 4096                    # 每帧样本数 (48kHz ≈ 85ms,足够分辨低频)
LOW_LO, LOW_HI = 20, 150        # 低频段 (楼上脚步/敲击)
FULL_LO, FULL_HI = 20, 8000     # 全频段 (算占比)
SHARP_LO = 2000                 # 尖锐度参考:2kHz 以上高频能量
BASELINE_ALPHA = 0.04           # 本底 EMA 更新速度 (越小越慢)
REFRACTORY = 0.35               # 不应期(秒):一次冲击后多久才能再记一次
CONFIRM_WINDOW = 4.0            # 确认窗口(秒)
NOISE_FLOOR = 1e-7              # 绝对能量地板,防止静音时比值炸掉


def synth_thump(sr=48000):
    """合成两声低频 '咚咚' 反击音 (70Hz + 45Hz,快起指数衰减)。"""
    def one(f0):
        n = int(sr * 0.22)
        t = np.arange(n) / sr
        env = np.exp(-t * 22.0)
        a = int(sr * 0.004)
        env[:a] *= np.linspace(0, 1, a)          # 软起音防爆音
        wave = (np.sin(2 * np.pi * f0 * t) * 0.9
                + np.sin(2 * np.pi * (f0 * 0.62) * t) * 0.5)
        return wave * env
    gap = np.zeros(int(sr * 0.06))
    sig = np.concatenate([one(72), gap, one(66)])
    sig = sig / np.max(np.abs(sig)) * 0.95
    return sig.astype(np.float32), sr


def ensure_default_sound():
    if not os.path.exists(DEFAULT_SOUND):
        sig, sr = synth_thump()
        sf.write(DEFAULT_SOUND, sig, sr)
    return DEFAULT_SOUND


class AudioMonitor:
    """音频线程里做采集 + 分析;冲击时间戳写入线程安全 deque 供界面消费。"""

    def __init__(self, log_fn):
        self.log = log_fn
        self.stream = None
        self.running = False

        self.sr = 48000
        self.sensitivity = 6           # 1=高(最灵敏) .. 10=低
        self._lock = threading.Lock()

        self.metrics = dict(low_db=0.0, sharp=0.0, low_ratio=0.0, score=0.0, level=0.0)
        self.wave = np.zeros(200, dtype=np.float32)   # 供界面画波形(降采样后)
        self.max_seen = 0.0            # 启动以来见过的最大样本幅度(判断是否真的在收音)
        self.impacts = deque()         # 冲击的 monotonic 时间戳
        self._last_impact_t = 0.0
        self._baseline = None
        self._freqs = None
        self._win = None
        self._low_idx = self._full_idx = self._sharp_idx = None

    def _prepare(self, n):
        self._freqs = np.fft.rfftfreq(n, 1.0 / self.sr)
        f = self._freqs
        self._low_idx = np.where((f >= LOW_LO) & (f <= LOW_HI))[0]
        self._full_idx = np.where((f >= FULL_LO) & (f <= FULL_HI))[0]
        self._sharp_idx = np.where((f >= SHARP_LO) & (f <= FULL_HI))[0]
        self._win = np.hanning(n).astype(np.float32)
        self._baseline = None

    def _trigger_ratio(self):
        s = self.sensitivity
        return 2.4 + (s - 1) / 9.0 * (11.0 - 2.4)   # 高->2.4×  低->11×

    def _abs_gate(self):
        s = self.sensitivity
        return NOISE_FLOOR * (3.0 + (s - 1) / 9.0 * 60.0)

    def _callback(self, indata, frames, time_info, status):
        if status:
            self.log(f"⚠️ 音频状态: {status}")
        try:
            x = indata[:, 0].astype(np.float32)
            if self._win is None or len(self._win) != len(x):
                self._prepare(len(x))
            xw = x * self._win
            spec = np.abs(np.fft.rfft(xw)) ** 2

            low_e = float(spec[self._low_idx].mean()) if len(self._low_idx) else 0.0
            full_e = float(spec[self._full_idx].mean()) + 1e-12
            high_e = float(spec[self._sharp_idx].mean()) if len(self._sharp_idx) else 0.0

            low_ratio = min(low_e / full_e, 1.0)
            sharp = min(high_e / (low_e + 1e-12), 4.0) / 4.0     # 0..1 越大越尖锐

            if self._baseline is None:
                self._baseline = low_e
            ratio = low_e / (self._baseline + 1e-12)
            trig = self._trigger_ratio()
            score = min(ratio / trig, 1.0)

            low_db = 10.0 * np.log10(low_e + 1e-12)
            low_db_norm = float(np.clip((low_db + 90) / 80.0, 0.0, 1.0))

            # 输入电平(全频 RMS)+ 降采样波形,供界面实时显示
            rms = float(np.sqrt(np.mean(x ** 2)) + 1e-9)
            level = float(np.clip((20.0 * np.log10(rms) + 60.0) / 60.0, 0.0, 1.0))
            step = max(1, len(x) // 200)
            wv = x[::step][:200].astype(np.float32)
            self.max_seen = max(self.max_seen, float(np.abs(x).max()))

            with self._lock:
                self.metrics = dict(low_db=low_db_norm, sharp=float(sharp),
                                    low_ratio=float(low_ratio), score=float(score),
                                    level=level)
                if len(wv) == len(self.wave):
                    self.wave = wv

            now = time.monotonic()
            is_impact = (
                ratio >= trig
                and low_e >= self._abs_gate()
                and low_ratio >= 0.30
                and sharp <= 0.65
            )
            if is_impact and (now - self._last_impact_t) >= REFRACTORY:
                self._last_impact_t = now
                with self._lock:
                    self.impacts.append(now)
                self.log(f"🔨 检测到低频冲击 (比值 {ratio:.1f}× / 阈值 {trig:.1f}×)")

            if not is_impact:
                self._baseline = (1 - BASELINE_ALPHA) * self._baseline + BASELINE_ALPHA * low_e
        except Exception as e:
            self.log(f"❌ 分析异常: {e}")

    def start(self, in_dev):
        info = sd.query_devices(in_dev)
        self.sr = int(info["default_samplerate"]) or 48000
        self._win = None
        self._baseline = None
        with self._lock:
            self.impacts.clear()
        self._last_impact_t = 0.0
        self.max_seen = 0.0
        self.stream = sd.InputStream(
            device=in_dev, channels=1, samplerate=self.sr,
            blocksize=BLOCK, dtype="float32", callback=self._callback,
        )
        self.stream.start()
        self.running = True
        self.log(f"🎧 开始监听 (设备 sr={self.sr}Hz,块={BLOCK},灵敏度 {self.sensitivity})")

    def stop(self):
        self.running = False
        if self.stream is not None:
            try:
                self.stream.stop(); self.stream.close()
            except Exception:
                pass
            self.stream = None

    def read_metrics(self):
        with self._lock:
            return dict(self.metrics)

    def get_wave(self):
        with self._lock:
            return self.wave.copy()

    def prune_and_count(self, window=CONFIRM_WINDOW):
        cutoff = time.monotonic() - window
        with self._lock:
            while self.impacts and self.impacts[0] < cutoff:
                self.impacts.popleft()
            return len(self.impacts)

    def clear_impacts(self):
        with self._lock:
            self.impacts.clear()
