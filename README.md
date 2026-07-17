# NoiseGuard · 楼上噪音 AI 反击

常驻 macOS 的小工具:用麦克风持续监听楼上传来的**低频"咚咚/跺脚"噪音**,当短时间内
连续检测到多次低频冲击时,自动往指定音响播放一段"反击"提示音。

> ⚠️ 仅供学习交流与自娱自乐。请遵守当地法律法规,理性维权、以和为贵,勿用于骚扰他人。

## 功能

- 🎙️ 选择任意输入麦克风 / 输出音响(支持蓝牙设备)
- 📊 每帧 FFT 分析 **20–150 Hz** 低频段,只认"低频主导 + 不尖锐"的冲击(排除说话/音乐/拍手)
- 🔁 **4 秒内连续 N 次**冲击才触发,带冷却期,避免误触发
- 🔊 反击音可用内置合成的低频"咚咚",也可选自己的 mp3/wav
- 📈 实时波形示波器 + 输入电平 + 低频能量/占比/尖锐度/综合评分
- 🎚️ 灵敏度、确认次数、冷却时间可调

## 安装 & 运行

需要 Python 3.9+(macOS 自带的 `/usr/bin/python3` 即可)。

```bash
git clone https://github.com/zq500480/noise-guard.git
cd noise-guard
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python noise_guard.py
```

或双击 `run.command`(需先 `chmod +x run.command`)。

## macOS 注意事项（重要）

1. **麦克风权限**:首次点「开始监听」时,若通过**终端 / run.command** 启动,系统会提示给「终端」
   麦克风权限,**允许**即可。若通过双击未签名 `.app` 启动,macOS 可能不弹授权框而直接给静音——
   建议用 `run.command`,或按下面"打包"一节做成签名 App。
2. **强制 arm64**:Apple Silicon 上系统 Python 是通用二进制,双击启动可能默认跑 x86_64 切片导致
   原生扩展加载失败;`run.command` 已用 `arch -arm64` 规避。
3. **别放外置硬盘**:放外置卷时双击启动的 App 可能因隐私限制读不到文件,建议放内置盘。

## 使用

1. 选好**输入麦克风**和**输出音响**,点「试听」确认音响正常。
2. 点「▶ 开始监听」,对着麦克风制造**低频闷响**(拳头捶桌 / 跺脚)测试——注意**拍手不算**(太尖锐,会被过滤)。
3. 调参建议:先把**灵敏度**调到 1~2、**确认次数**调到 1 方便测试,验证通过后再调回(灵敏度 6、确认 3)防误触发。

## 打包成独立 .app（可选，让麦克风权限更省心）

```bash
./.venv/bin/pip install pyinstaller
./.venv/bin/pyinstaller --windowed --name "NoiseGuard" \
    --osx-bundle-identifier com.example.noiseguard \
    noise_guard.py
codesign --force --deep --sign - "dist/NoiseGuard.app"   # ad-hoc 签名
```
> 打包时需要给生成的 `Info.plist` 加 `NSMicrophoneUsageDescription`(可用 `.spec` 的
> `info_plist` 字段注入),否则申请麦克风时可能被系统直接终止。

## 工作原理

每帧 4096 点 FFT → 取 20–150Hz 低频能量;低频占比 ≥30% 且尖锐度低才算"冲击";
自适应本底(EMA)判断"比平时响多少倍"(阈值由灵敏度决定);350ms 不应期去重;
4 秒窗口累积到 N 次 → 触发 → 冷却。详见 `audio_core.py`。

## License

MIT
