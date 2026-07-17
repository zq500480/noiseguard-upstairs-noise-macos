#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
楼上噪音 AI 反击 · NoiseGuard  (PySide6 / Qt 界面)
====================================================
常驻 macOS 的小工具:一个(蓝牙)麦克风持续监听楼上低频"咚咚",
连续确认 N 次后,自动往一个(蓝牙)音响播放反击提示音。

运行: ./.venv/bin/python noise_guard.py
"""

import os
import queue
import time
from datetime import datetime

import sounddevice as sd
import soundfile as sf

from PySide6 import QtCore, QtGui, QtWidgets

import audio_core as core

QSS = """
QWidget { font-family: 'PingFang SC','Helvetica Neue',sans-serif; font-size: 14px; color: #1d1d1f; }
QLabel#Section { font-size: 16px; font-weight: 600; color: #111; margin-top: 6px; }
QFrame#Card { background: #f5f5f7; border-radius: 12px; }
QComboBox, QPushButton { padding: 6px 10px; border: 1px solid #d0d0d5; border-radius: 8px; background: #fff; }
QPushButton { background: #fff; }
QPushButton:hover { background: #f0f0f3; }
QPushButton#Primary { background: #0a84ff; color: #fff; border: none; font-weight: 600; }
QPushButton#Primary:hover { background: #0071e3; }
QPushButton#Primary:disabled { background: #a9d2ff; }
QPushButton#Danger { background: #ff453a; color: #fff; border: none; font-weight: 600; }
QPushButton#Danger:disabled { background: #f0b3af; }
QProgressBar { border: none; background: #e6e6ea; border-radius: 5px; height: 10px; text-align: center; }
QProgressBar::chunk { background: #0a84ff; border-radius: 5px; }
QPlainTextEdit { background: #1e1e1e; color: #d0d0d0; border-radius: 10px;
                 font-family: 'Menlo','SF Mono',monospace; font-size: 12px; padding: 8px; }
QLabel#State { font-size: 15px; font-weight: 600; }
"""


class WaveformWidget(QtWidgets.QWidget):
    """实时波形示波器:随任何声音跳动,直观确认麦克风在收音。"""
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(70)
        self._wave = None

    def set_wave(self, w):
        self._wave = w
        self.update()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = self.rect()
        p.fillRect(r, QtGui.QColor("#101418"))
        mid = r.height() / 2
        # 中线
        p.setPen(QtGui.QPen(QtGui.QColor("#2a2f36"), 1))
        p.drawLine(0, int(mid), r.width(), int(mid))
        w = self._wave
        if w is None or len(w) < 2:
            return
        n = len(w)
        gain = mid * 3.0                      # 放大,让小声音也看得见
        path = QtGui.QPainterPath()
        for i, v in enumerate(w):
            x = i / (n - 1) * r.width()
            y = mid - max(-1.0, min(1.0, float(v) * gain / mid)) * (mid - 4)
            path.lineTo(x, y) if i else path.moveTo(x, y)
        p.setPen(QtGui.QPen(QtGui.QColor("#0a84ff"), 1.6))
        p.drawPath(path)


class Card(QtWidgets.QFrame):
    """圆角灰底分组卡片。"""
    def __init__(self, title):
        super().__init__()
        self.setObjectName("Card")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(10)
        head = QtWidgets.QLabel(title); head.setObjectName("Section")
        outer.addWidget(head)
        self.body = QtWidgets.QGridLayout()
        self.body.setHorizontalSpacing(10)
        self.body.setVerticalSpacing(10)
        outer.addLayout(self.body)


class App(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("楼上噪音 AI 反击 · NoiseGuard")
        self.resize(720, 720)
        self.setMinimumSize(420, 320)      # 允许拉到很小
        self.setStyleSheet(QSS)

        self.log_q = queue.Queue()
        self.monitor = core.AudioMonitor(self._enqueue_log)

        self.sound_path = core.ensure_default_sound()
        self.sound_data = None
        self.sound_sr = None
        self._load_sound(self.sound_path)

        self.trigger_count = 0
        self.start_time = None
        self.cooldown_until = 0.0
        self.inputs = []
        self.outputs = []

        self._build_ui()
        self._refresh_devices()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(60)

    # ---------------- UI ----------------
    def _build_ui(self):
        # 整个内容放进可滚动区域:窗口可随意缩小,内容超出时上下滚动
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        content = QtWidgets.QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        root = QtWidgets.QVBoxLayout(content)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        title = QtWidgets.QLabel("楼上噪音 AI 反击")
        title.setStyleSheet("font-size:22px;font-weight:700;")
        root.addWidget(title)

        # ---- 设备设置 ----
        c = Card("设备设置"); g = c.body
        g.addWidget(QtWidgets.QLabel("输入设备 (麦克风):"), 0, 0)
        self.in_combo = QtWidgets.QComboBox(); g.addWidget(self.in_combo, 0, 1)
        g.addWidget(QtWidgets.QLabel("输出设备 (音箱):"), 1, 0)
        self.out_combo = QtWidgets.QComboBox(); g.addWidget(self.out_combo, 1, 1)
        refresh = QtWidgets.QPushButton("刷新设备"); refresh.clicked.connect(self._refresh_devices)
        g.addWidget(refresh, 0, 2, 2, 1)
        g.setColumnStretch(1, 1)
        root.addWidget(c)

        # ---- 反击音频 ----
        c = Card("反击音频"); g = c.body
        self.sound_lbl = QtWidgets.QLabel(os.path.basename(self.sound_path))
        g.addWidget(self.sound_lbl, 0, 0)
        prev = QtWidgets.QPushButton("试听"); prev.clicked.connect(lambda: self._play_counter(True))
        choose = QtWidgets.QPushButton("选择文件"); choose.clicked.connect(self._choose_sound)
        g.addWidget(prev, 0, 1); g.addWidget(choose, 0, 2)
        g.setColumnStretch(0, 1)
        root.addWidget(c)

        # ---- 参数调节 ----
        c = Card("参数调节"); g = c.body
        # 灵敏度
        g.addWidget(QtWidgets.QLabel("灵敏度:"), 0, 0)
        g.addWidget(QtWidgets.QLabel("高"), 0, 1)
        self.sens = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.sens.setRange(1, 10); self.sens.setValue(6)
        self.sens.valueChanged.connect(self._on_sens); g.addWidget(self.sens, 0, 2)
        g.addWidget(QtWidgets.QLabel("低"), 0, 3)
        self.sens_val = QtWidgets.QLabel("6"); self.sens_val.setMinimumWidth(70)
        g.addWidget(self.sens_val, 0, 4)
        # 确认次数
        g.addWidget(QtWidgets.QLabel("确认次数:"), 1, 0)
        self.confirm = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.confirm.setRange(1, 6); self.confirm.setValue(3)
        self.confirm.valueChanged.connect(self._on_params); g.addWidget(self.confirm, 1, 2)
        self.confirm_val = QtWidgets.QLabel("3次/4秒"); g.addWidget(self.confirm_val, 1, 4)
        # 冷却时间
        g.addWidget(QtWidgets.QLabel("冷却时间:"), 2, 0)
        self.cooldown = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.cooldown.setRange(1, 30); self.cooldown.setValue(5)
        self.cooldown.valueChanged.connect(self._on_params); g.addWidget(self.cooldown, 2, 2)
        self.cooldown_val = QtWidgets.QLabel("5秒"); g.addWidget(self.cooldown_val, 2, 4)
        g.setColumnStretch(2, 1)
        root.addWidget(c)

        # ---- 控制按钮 ----
        row = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("▶  开始监听"); self.start_btn.setObjectName("Primary")
        self.start_btn.setMinimumHeight(42); self.start_btn.clicked.connect(self._start)
        self.stop_btn = QtWidgets.QPushButton("■  停止"); self.stop_btn.setObjectName("Danger")
        self.stop_btn.setMinimumHeight(42); self.stop_btn.setEnabled(False); self.stop_btn.clicked.connect(self._stop)
        row.addWidget(self.start_btn); row.addWidget(self.stop_btn)
        root.addLayout(row)

        # ---- 运行状态 ----
        c = Card("运行状态"); g = c.body
        self.state_lbl = QtWidgets.QLabel("待机中…"); self.state_lbl.setObjectName("State")
        g.addWidget(self.state_lbl, 0, 0, 1, 4)

        # 实时波形 + 输入电平(随任何声音跳动,用来确认麦克风在收音)
        self.wave_widget = WaveformWidget()
        g.addWidget(self.wave_widget, 1, 0, 1, 4)
        g.addWidget(QtWidgets.QLabel("输入电平:"), 2, 0)
        self.level_bar = QtWidgets.QProgressBar(); self.level_bar.setRange(0, 100); self.level_bar.setTextVisible(False)
        g.addWidget(self.level_bar, 2, 1, 1, 3)

        self.bars = {}
        def add_bar(r, col, name):
            g.addWidget(QtWidgets.QLabel(name + ":"), r, col)
            pb = QtWidgets.QProgressBar(); pb.setRange(0, 100); pb.setTextVisible(False)
            g.addWidget(pb, r, col + 1); self.bars[name] = pb
        add_bar(3, 0, "低频能量"); add_bar(3, 2, "低频占比")
        add_bar(4, 0, "尖锐度");   add_bar(4, 2, "综合评分")

        g.addWidget(QtWidgets.QLabel("冲击累积:"), 5, 0)
        self.accum_lbl = QtWidgets.QLabel("0/3"); g.addWidget(self.accum_lbl, 5, 1)
        g.addWidget(QtWidgets.QLabel("触发次数:"), 5, 2)
        self.count_lbl = QtWidgets.QLabel("0"); g.addWidget(self.count_lbl, 5, 3)
        g.addWidget(QtWidgets.QLabel("运行时长:"), 6, 0)
        self.uptime_lbl = QtWidgets.QLabel("00:00:00"); g.addWidget(self.uptime_lbl, 6, 1)
        g.setColumnStretch(1, 1); g.setColumnStretch(3, 1)
        root.addWidget(c)

        # ---- 日志 ----
        head = QtWidgets.QLabel("日志"); head.setObjectName("Section"); root.addWidget(head)
        self.log_view = QtWidgets.QPlainTextEdit(); self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(150); root.addWidget(self.log_view, 1)
        self._enqueue_log("已就绪。选择输入/输出设备后点击「开始监听」。")

    # ---------------- 设备 ----------------
    def _refresh_devices(self):
        devs = sd.query_devices()
        self.inputs = [(i, d["name"]) for i, d in enumerate(devs) if d["max_input_channels"] > 0]
        self.outputs = [(i, d["name"]) for i, d in enumerate(devs) if d["max_output_channels"] > 0]
        cur_in = self.in_combo.currentIndex()
        cur_out = self.out_combo.currentIndex()
        self.in_combo.clear(); self.out_combo.clear()
        self.in_combo.addItems([f"[{i}] {n}" for i, n in self.inputs])
        self.out_combo.addItems([f"[{i}] {n}" for i, n in self.outputs])
        try:
            din, dout = sd.default.device
        except Exception:
            din = dout = -1
        if cur_in >= 0:
            self.in_combo.setCurrentIndex(min(cur_in, len(self.inputs) - 1))
        else:
            k = next((j for j, (i, _) in enumerate(self.inputs) if i == din), 0)
            self.in_combo.setCurrentIndex(k)
        if cur_out >= 0:
            self.out_combo.setCurrentIndex(min(cur_out, len(self.outputs) - 1))
        else:
            k = next((j for j, (i, _) in enumerate(self.outputs) if i == dout), 0)
            self.out_combo.setCurrentIndex(k)
        self._enqueue_log(f"设备已刷新:{len(self.inputs)} 输入 / {len(self.outputs)} 输出")

    def _sel_input(self):
        i = self.in_combo.currentIndex()
        return self.inputs[i][0] if 0 <= i < len(self.inputs) else None

    def _sel_output(self):
        i = self.out_combo.currentIndex()
        return self.outputs[i][0] if 0 <= i < len(self.outputs) else None

    # ---------------- 音频文件 ----------------
    def _load_sound(self, path):
        try:
            data, sr = sf.read(path, dtype="float32", always_2d=False)
            if getattr(data, "ndim", 1) > 1:
                data = data.mean(axis=1)
            self.sound_data, self.sound_sr, self.sound_path = data, sr, path
            return True
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "读取失败", f"无法读取音频:\n{e}")
            return False

    def _choose_sound(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择反击提示音", "",
            "音频 (*.wav *.mp3 *.flac *.aiff *.m4a *.ogg);;全部 (*.*)")
        if p and self._load_sound(p):
            self.sound_lbl.setText(os.path.basename(p))
            self._enqueue_log(f"已选择音频: {os.path.basename(p)}")

    def _play_counter(self, preview=False):
        out = self._sel_output()
        if out is None or self.sound_data is None:
            return
        try:
            sd.play(self.sound_data, self.sound_sr, device=out)
            if preview:
                self._enqueue_log("🔊 试听反击音…")
        except Exception as e:
            self._enqueue_log(f"❌ 播放失败: {e}")

    # ---------------- 参数 ----------------
    def _on_sens(self):
        v = self.sens.value()
        self.sens_val.setText(str(v))
        self.monitor.sensitivity = v

    def _on_params(self):
        self.confirm_val.setText(f"{self.confirm.value()}次/{int(core.CONFIRM_WINDOW)}秒")
        self.cooldown_val.setText(f"{self.cooldown.value()}秒")

    # ---------------- 启停 ----------------
    def _start(self):
        in_dev = self._sel_input()
        if in_dev is None:
            QtWidgets.QMessageBox.warning(self, "提示", "请先选择输入麦克风设备。")
            return
        self.monitor.sensitivity = self.sens.value()
        try:
            self.monitor.start(in_dev)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "启动失败", str(e))
            return
        # 调试日志:记录一次启动与所选设备
        try:
            with open(os.path.expanduser("~/noiseguard_debug.log"), "a") as fp:
                fp.write(f"[{datetime.now():%H:%M:%S}] START in_dev={in_dev} "
                         f"name={sd.query_devices(in_dev)['name']} sr={self.monitor.sr}\n")
        except Exception:
            pass
        self._warned_silent = False
        self.trigger_count = 0
        self.cooldown_until = 0.0
        self.start_time = time.monotonic()
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        self.count_lbl.setText("0")
        self.state_lbl.setText("监听中…")

    def _stop(self):
        self.monitor.stop()
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        self.state_lbl.setText("已停止")
        for pb in self.bars.values():
            pb.setValue(0)
        self.level_bar.setValue(0)
        import numpy as _np
        self.wave_widget.set_wave(_np.zeros(200, dtype=_np.float32))
        self._enqueue_log("⏹ 已停止监听。")

    # ---------------- 轮询 ----------------
    def _poll(self):
        try:
            while True:
                line = self.log_q.get_nowait()
                self.log_view.appendPlainText(line)
        except queue.Empty:
            pass

        if not self.monitor.running:
            return

        m = self.monitor.read_metrics()
        self.wave_widget.set_wave(self.monitor.get_wave())
        self.level_bar.setValue(int(m.get("level", 0.0) * 100))
        self.bars["低频能量"].setValue(int(m["low_db"] * 100))
        self.bars["尖锐度"].setValue(int(m["sharp"] * 100))
        self.bars["低频占比"].setValue(int(m["low_ratio"] * 100))
        self.bars["综合评分"].setValue(int(m["score"] * 100))

        n_need = self.confirm.value()
        cnt = self.monitor.prune_and_count(core.CONFIRM_WINDOW)
        self.accum_lbl.setText(f"{cnt}/{n_need}")

        now = time.monotonic()
        if now < self.cooldown_until:
            self.state_lbl.setText(f"冷却中… {self.cooldown_until - now:.0f}s")
        else:
            self.state_lbl.setText("监听中…")
            if cnt >= n_need:
                self._fire()

        if self.start_time:
            el = int(now - self.start_time)
            self.uptime_lbl.setText(f"{el//3600:02d}:{(el%3600)//60:02d}:{el%60:02d}")
            # 启动 2 秒后仍几乎收不到任何声音 → 极可能是麦克风权限没给
            if not getattr(self, "_warned_silent", True) and el >= 2:
                if self.monitor.max_seen < 0.0008:
                    self._warned_silent = True
                    self.state_lbl.setText("⚠️ 收不到声音——请检查麦克风权限/设备")
                    self._enqueue_log("⚠️ 2秒内几乎无输入信号。请到 系统设置→隐私与安全性→麦克风 "
                                      "勾选「楼上反击」;或换一个输入设备。")
                    try:
                        with open(os.path.expanduser("~/noiseguard_debug.log"), "a") as fp:
                            fp.write(f"[{datetime.now():%H:%M:%S}] SILENT max_seen={self.monitor.max_seen:.5f}\n")
                    except Exception:
                        pass
                else:
                    self._warned_silent = True
                    try:
                        with open(os.path.expanduser("~/noiseguard_debug.log"), "a") as fp:
                            fp.write(f"[{datetime.now():%H:%M:%S}] OK max_seen={self.monitor.max_seen:.5f}\n")
                    except Exception:
                        pass

    def _fire(self):
        self.trigger_count += 1
        cd = self.cooldown.value()
        self.cooldown_until = time.monotonic() + cd
        self.monitor.clear_impacts()
        self.count_lbl.setText(str(self.trigger_count))
        self._enqueue_log(
            f"💥 [{datetime.now():%H:%M:%S}] 触发反击 #{self.trigger_count} → 播放提示音,冷却 {cd}s")
        self._play_counter()

    # ---------------- 杂项 ----------------
    def _enqueue_log(self, msg):
        self.log_q.put(f"[{datetime.now():%H:%M:%S}] {msg}")

    def closeEvent(self, ev):
        try:
            self.monitor.stop()
        except Exception:
            pass
        ev.accept()


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setApplicationName("NoiseGuard")
    w = App(); w.show()
    app.exec()


if __name__ == "__main__":
    main()
