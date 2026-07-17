# NoiseGuard for macOS · 楼上低频噪音检测与反击提示

当楼上的跺脚、拖拽和低频“咚咚”声一次次穿过天花板，打断睡眠、工作与难得的安静，
那种无法躲开、又很难向别人证明的持续折磨，只有真正经历过的人才明白。NoiseGuard
希望用可观察、可调节的技术手段，给长期承受楼上低频噪音的人一点掌控感。

这是一个常驻 **macOS** 的楼上噪音检测工具：用麦克风持续监听**低频“咚咚 / 跺脚 / 撞击”**，
短时间内确认多次低频冲击后，通过指定音响播放用户选择的提示音。

> [!CAUTION]
> **本仓库仅供娱乐爱好、技术学习与日常研究。严禁用于任何非法目的，严禁用于骚扰、恐吓、
> 报复或伤害他人，也不得连接可能危及人身与财产安全的设备。** 请遵守当地法律法规、物业规定
> 与安静时段要求；遇到真实噪音纠纷，应优先沟通、留存证据并通过物业或合法渠道解决。

## 搜索关键词 / Keywords

楼上噪音、低频噪音、跺脚声、咚咚声、噪音检测、声音检测、macOS 噪音工具、
upstairs noise、low-frequency noise、footstep noise、impact sound detection、
audio DSP、FFT detector、PySide6、Python、sounddevice。

## 功能

- 🎙️ 选择任意输入麦克风 / 输出音响(支持蓝牙设备)
- 📊 每帧 FFT 分析 **20–150 Hz** 低频段,只认"低频主导 + 不尖锐"的冲击(排除说话/音乐/拍手)
- 🔁 **4 秒内连续 N 次**冲击才触发,带冷却期,避免误触发
- 🔊 反击音可用内置合成的低频"咚咚",也可选自己的 mp3/wav
- 📈 实时波形示波器 + 输入电平 + 低频能量/占比/尖锐度/综合评分
- 🎚️ 灵敏度、确认次数、冷却时间可调

## 下载 macOS M 芯片安装包

前往 [GitHub Releases](https://github.com/zq500480/noiseguard-upstairs-noise-macos/releases/latest)
下载文件名包含 **`macOS-Apple-Silicon-arm64.dmg`** 的安装包。

> **此安装包仅适用于 macOS 14 及以上的 Apple Silicon（M1 / M2 / M3 / M4 及后续 M 系列芯片），
> 不支持 Intel Mac。**

打开 DMG 后，将 `NoiseGuard.app` 拖入 `Applications`。当前公开安装包采用 ad-hoc 签名，
未使用付费 Apple Developer 证书公证；若 macOS 首次阻止启动，请在 Finder 中右键 App →
“打开”→“仍要打开”，并在系统设置中允许麦克风权限。

## 安装 & 运行

需要 Python 3.9+(macOS 自带的 `/usr/bin/python3` 即可)。

```bash
git clone https://github.com/zq500480/noiseguard-upstairs-noise-macos.git
cd noiseguard-upstairs-noise-macos
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

## 自行构建 M 芯片安装包

```bash
chmod +x build_macos_arm64.sh
./build_macos_arm64.sh
```

构建脚本只允许在原生 `arm64` Mac 上运行，并会自动写入麦克风权限说明、执行 ad-hoc 签名，
最终输出 `dist/NoiseGuard-v版本-macOS-Apple-Silicon-arm64.dmg`。

## 工作原理

每帧 4096 点 FFT → 取 20–150Hz 低频能量;低频占比 ≥30% 且尖锐度低才算"冲击";
自适应本底(EMA)判断"比平时响多少倍"(阈值由灵敏度决定);350ms 不应期去重;
4 秒窗口累积到 N 次 → 触发 → 冷却。详见 `audio_core.py`。

## License

MIT。使用、修改或分发本项目时，使用者须自行确保用途合法合规；作者不对滥用行为承担责任。
