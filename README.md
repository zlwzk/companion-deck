# CompanionDeck（伴侣操控台）

> 在手机（或任何设备）上控制电脑上的软件——同一局域网即可，或通过 Tailscale 走互联网远程。首个适配目标：**Soundpad**。

打游戏时 Soundpad 藏在后台，想切歌、播放/暂停就得 Alt-Tab 切出去——CompanionDeck 让这一切发生在你的手机屏幕上：同一 Wi-Fi 下打开浏览器，大按钮点一下即可控制；装上 Tailscale 后，人在外面也能远程控制家里的电脑。

它不只是一个 Soundpad 遥控器，而是一个**适配器框架**：任何软件都可以通过「系统媒体键 / 自定义热键方案 / 编写适配器」三种方式接入，用手机控制。

## 特性

- 🎮 **Soundpad 原生控制**：通过官方 Remote Control 命名管道接口，支持播放/暂停、上一首/下一首、停止、音量、静音、播放进度、声音列表、按索引播放
- 📱 **Web 控制台**：手机浏览器即用，无需安装 App；暗色大按钮，适合游戏场景
- 🌍 **局域网 + 互联网远程**：同一 Wi-Fi 直接连；安装 ZeroTier（或 Tailscale）后可全球远程（私有加密组网，无需公网 IP 与端口转发）
- 🔌 **适配器框架**：能力声明式设计，UI 按能力自动渲染；新增软件三种接入路径（见 docs/DESIGN.md）
- 🔐 **访问口令**：首次运行自动生成 Token，远程访问同样受保护
- ⚡ **实时状态**：WebSocket 推送播放状态、音量、进度

## 快速开始（Windows）

1. 确认已安装 **Python 3.10+**，且已安装并运行 **Soundpad**
2. 安装依赖：

   ```bat
   py -3 -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```

   或直接双击 **`run.bat`**（自动完成以上两步）

3. 启动：

   ```bat
   .venv\Scripts\python -m deck
   ```

   终端会打印：
   - 本机访问地址 `http://127.0.0.1:8390`
   - 局域网访问地址 `http://<你的IP>:8390`（手机需连同一 Wi-Fi）
   - 互联网远程地址 `http://<组网IP>:8390`（装了 ZeroTier / Tailscale 才会显示，详见 docs/SETUP.md 第 8 节）
   - **访问口令**（首次运行自动生成）

4. 手机浏览器打开地址，输入口令即可控制（同一 Wi-Fi 用局域网地址；人在外面用 ZeroTier 远程地址）

> Soundpad 无需任何额外设置——Remote Control 接口是内建功能，只要 Soundpad 在运行即可。

## 适配器一览

| 适配器 | 说明 | 需要配置 |
| --- | --- | --- |
| `soundpad` | Soundpad 原生接口（推荐） | 无，开箱即用 |
| `mediakeys` | 系统媒体键，控制当前媒体会话（Spotify/浏览器等） | 无 |
| `profile` | 自定义热键方案，任意软件 | 在 config.json 中定义热键 |

## 声音面板

- 默认**自动从 Soundpad 声音列表生成**按钮，点击即播放对应声音
- 也可以在 `config.json` 的 `adapters.soundpad.sounds` 中自定义按钮（按索引播放或触发热键）：

```json
"sounds": [
  { "name": "大笑", "kind": "hotkey", "hotkey": ["ctrl", "alt", "1"] },
  { "name": "欢呼", "kind": "index", "index": 12 }
]
```

## 项目结构

```
companion-deck/
├── run.bat                # Windows 一键启动
├── deck/
│   ├── server.py          # FastAPI 服务（REST + WebSocket）
│   ├── pipe.py            # Soundpad 命名管道客户端（ctypes 零依赖）
│   ├── hotkeys.py         # SendInput 全局热键模拟
│   ├── config.py          # 配置加载（首次运行自动生成）
│   ├── core/              # 数据模型 + 适配器注册表
│   ├── adapters/          # soundpad / mediakeys / profile
│   └── web/               # 手机端 Web UI（无框架，单页）
├── docs/
│   ├── DESIGN.md          # 头脑风暴 + 架构 + 扩展指南（必读）
│   └── SETUP.md           # 安装/连接/配置/故障排查
├── config.example.json
└── tests/                 # API 冒烟测试
```

## 文档

- **设计文档（头脑风暴、架构、如何适配新软件）**：[docs/DESIGN.md](docs/DESIGN.md)
- **安装与使用手册**：[docs/SETUP.md](docs/SETUP.md)

## 技术要点

- 控制 Soundpad 的协议来自官方 [Remote Control Interface](https://www.leppsoft.com/soundpad/en/rc/)（命名管道 `\\.\pipe\sp_remote_control`），协议 v1.1.2，响应基于 HTTP 风格状态码
- 服务端仅依赖 `fastapi` + `uvicorn`；命名管道与 SendInput 均用 ctypes 实现，零额外依赖
- 鉴权默认开启；`config.json` 已被 `.gitignore` 忽略（含口令，勿提交）

## Roadmap

- ✅ **互联网远程（ZeroTier / Tailscale）**（已支持：启动自动检测组网地址，见 docs/SETUP.md）
- SMTC（Windows 系统媒体传输控制）适配器：读取任意媒体会话的曲目/歌手
- 系统托盘驻留、开机自启
- 二维码扫码连接、PWA 安装到手机桌面
- OBS / Spotify / 浏览器标签页等开箱适配器示例
- 适配器插件化（pip 安装即用）
