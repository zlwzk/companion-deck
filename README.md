# CompanionDeck（伴侣操控台）

## 📣 v0.6.0 发布公告

**CompanionDeck** 是一个 Soundpad 局域网伴侣操控台：电脑上运行一个小程序，
手机扫码打开网页，就能远程点播你 Soundpad 里的所有声音 —— 不装任何 App，
不走公网，局域网直连，延迟低到像在手机本地操作。

**本次更新亮点**：

- ⏱ **松键延迟尾巴**：声音结束后语音键多按 300~1000ms 再松开（滑杆自由调节），盖住游戏语音的收尾截断；连播时自动保持不松
- 🎚 **提前量 / 点按时长可配**：按键提前量 0~500ms、点按时长 0~500ms 滑杆调节，适配不同游戏的语音通道建立速度
- 🟢 **PTT 状态指示**：面板顶栏小圆点实时显示「语音键按住中」（呼吸高亮），一眼确认半自动播放已生效
- 🔊 **试按一下**：设置页新增测试按钮，不用进游戏就能验证按键配置是否正确
- 🩹 **修复「正在播放」信息不同步**：点播新声音后页头立即切换为新声音并平滑滚动回顶部，方便随时暂停
- ♻ **v0.5.0 全部能力保留**：游戏语音自动按键 / 全新图标 / 版本号常驻 / USB 一键修复 / 单文件 exe

👉 **Windows 用户直接 [下载 CompanionDeck.exe](../../releases/latest) 即可使用**；
遇到问题欢迎提 [Issue](../../issues)。

> 🪞 **Gitee 镜像**: https://gitee.com/zlwzk/companion-deck (由 GitHub Actions 自动同步，代码与 Release 附件保持一致)

> 在手机（或任何设备）上控制电脑上的软件 —— 同一 Wi-Fi、电脑移动热点即可，
>
> **全部使用系统自带能力，无需安装任何第三方软件**。首个适配目标：**Soundpad**。

打游戏时 Soundpad 藏在后台，想切歌、播放 / 暂停就得 Alt-Tab 切出去 ——CompanionDeck 让这一切发生在你的手机屏幕上：同一 Wi-Fi 下打开浏览器，大按钮点一下即可控制；打游戏时手机连电脑自带的移动热点，不影响前台游戏。打开右上角「扫码」按钮，手机相机扫一下就能连，连口令都免输。

它不只是一个 Soundpad 遥控器，而是一个**适配器框架**：任何软件都可以通过「系统媒体键 / 自定义热键方案 / 编写适配器」三种方式接入，用手机控制。

## 特性

* 🎮 **Soundpad 原生控制**：通过官方 Remote Control 命名管道接口，支持播放 / 暂停、上一首 / 下一首、停止、音量、静音、播放进度、声音列表、按索引播放
* 🗂️ **分类树（Tab 切换）**：自动读取 Soundpad 的 `GetCategories()`，按真实分类树（含嵌套子分类）展示，分类间 Tab 横向切换；当前分类可一键随机播放
* 🎲 **随机播放**：全局随机 + 分类内随机（`DoPlayRandomSound` / `DoPlayRandomSoundFromCategory`）
* ⏩ **进度跳转**：进度条可拖动跳转（`DoSeekMs` / `DoJumpMs`），还有「重播当前」（`DoPlayCurrentSoundAgain`）
* 🎙 **游戏语音自动按键（PTT）**：播放时自动按下游戏「按键说话」键，长按 / 点按可选，按键可自定义，设置面板一键开关
* 📱 **Web 控制台**：手机浏览器即用，无需安装 App；暗色大按钮，适合游戏场景
* 📲 **扫码直连 + PWA**：服务端生成二维码（含口令），手机相机扫码即连；支持「添加到主屏」像 App 一样
* 🌍 **局域网直连（零第三方软件）**：同一 Wi-Fi 或电脑移动热点 —— 焦点放在局域网，启动自动检测并列出当前可用地址
* 🖧 **系统托盘驻留**：后台静默运行，托盘菜单「打开 / 退出」，关闭主窗口不影响控制
* � **开机自启**：用 `--autostart on` 一键写入注册表 Run 键，开机自动驻留
* �🔌 **适配器框架**：能力声明式设计，UI 按能力自动渲染；新增软件三种接入路径（见 docs/DESIGN.md）
* 🔐 **访问口令**：首次运行自动生成 Token，远程访问同样受保护
* ⚡ **实时状态**：WebSocket 推送播放状态、音量、进度、当前声音（含 artist / 标题 / 播放次数）
* 📦 **一键打包 exe**：`build.bat` 用 PyInstaller 打成单文件 exe，拷贝即用

## 快速开始（Windows）

1. 确认已安装 **Python 3.10+**，且已安装并运行 **Soundpad**
2. 安装依赖：

```
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

或直接双击 `run.bat`（自动完成以上两步）

3. 启动：

```
.venv\Scripts\python -m deck
```

终端会打印当前可用的全部通道地址、二维码（ASCII）与访问口令：

* 本机访问地址 `http://127.0.0.1:8390`
* 局域网地址 `http://<你的IP>:8390`（手机连同一 Wi-Fi，扫终端二维码即可）
* 电脑热点地址（手机连电脑移动热点）
* **访问口令**（首次运行自动生成）

4. 手机浏览器打开地址，输入口令即可控制（或点击右上角「▦」按钮扫码直连）

> Soundpad 无需任何额外设置 —— Remote Control 接口是内建功能，只要 Soundpad 在运行即可。

## 适配器一览

| 适配器         | 说明                             | 需要配置                |
| ------------ | ------------------------------ | ------------------- |
| `soundpad`  | Soundpad 原生接口（推荐）              | 无，开箱即用              |
| `mediakeys` | 系统媒体键，控制当前媒体会话（Spotify / 浏览器等） | 无                   |
| `profile`   | 自定义热键方案，任意软件                   | 在 config.json 中定义热键 |

## 声音面板（分类 Tab）

- **自动读取 Soundpad 真实分类**：不再是一股脑的扁平列表，按分类 Tab 切换浏览
- 顶部 Tab 横向滑动，带分类内声音数显示
- Tab 切换会调用 `DoSelectCategory` 同步 Soundpad 主窗口
- 当前分类一键「🎲 当前分类随机」
- 在 `config.json` 的 `adapters.soundpad.sounds` 中也可手动覆盖按钮：

```json
"sounds": [
  { "name": "大笑", "kind": "hotkey", "hotkey": ["ctrl", "alt", "1"] },
  { "name": "欢呼", "kind": "index", "index": 12 }
]
```

## 系统托盘与开机自启

```bat
:: 启用开机自启
.venv\Scripts\python -m deck --autostart on

:: 查询当前状态
.venv\Scripts\python -m deck --autostart status

:: 禁用开机自启
.venv\Scripts\python -m deck --autostart off

:: 不创建系统托盘（命令行模式）
.venv\Scripts\python -m deck --no-tray
```

## 打包为 exe（PyInstaller）

```bat
build.bat
:: 产物：dist\CompanionDeck.exe（双击即可运行，无需安装 Python）
```

## 项目结构

```
companion-deck/
├── run.bat                # Windows 一键启动
├── build.bat              # PyInstaller 打包脚本
├── companion-deck.spec    # PyInstaller 配置
├── deck/
│   ├── server.py          # FastAPI 服务（REST + WebSocket + 新端点）
│   ├── pipe.py            # Soundpad 命名管道客户端（ctypes 零依赖）
│   ├── hotkeys.py         # SendInput 全局热键模拟
│   ├── qrcode.py          # 二维码生成（依赖 qrcode 库）
│   ├── tray.py            # 系统托盘（ctypes Shell_NotifyIcon）
│   ├── autostart.py       # 开机自启（注册表 Run 键）
│   ├── lan.py             # 局域网地址发现
│   ├── config.py          # 配置加载（首次运行自动生成）
│   ├── core/              # 数据模型 + 适配器注册表
│   ├── adapters/          # soundpad / mediakeys / profile
│   └── web/               # 手机端 Web UI（含 manifest.json + sw.js）
├── docs/
│   ├── DESIGN.md          # 头脑风暴 + 架构 + 扩展指南（必读）
│   └── SETUP.md           # 安装/连接/配置/故障排查
├── config.example.json
└── tests/                 # API 冒烟测试 + 分类解析测试
```

## 文档

* **设计文档（头脑风暴、架构、如何适配新软件）**：[docs/DESIGN.md](docs/DESIGN.md)
* **安装与使用手册**：[docs/SETUP.md](docs/SETUP.md)

## 技术要点

* 控制 Soundpad 的协议来自官方 [Remote Control Interface](https://www.leppsoft.com/soundpad/en/rc/)（命名管道 `\\.\pipe\sp_remote_control`），协议 v1.1.2，响应基于 HTTP 风格状态码
* **分类读取使用 `GetCategories(true, false)`**（v1.1.0+），返回完整 XML 树含嵌套 `<Category>` 与 `<Sound>`；旧实现误用 `GetSoundlist()`，那个命令只返回扁平的 "All sounds" 隐藏分类
* 随机播放、按分类播放、进度跳转均使用 v1.1.0+ 新增命令
* 服务端依赖 `fastapi` + `uvicorn` + `qrcode`；命名管道 / SendInput / 托盘 / 注册表均用 ctypes/winreg 实现，零额外系统依赖
* 鉴权默认开启；`config.json` 已被 `.gitignore` 忽略（含口令，勿提交）

## Roadmap

* ✅ **多通道直连**（局域网 / 电脑热点 / IPv6 直连 / 公网 IPv4 转发，零第三方软件，见 docs/SETUP.md）
* ✅ **Soundpad 分类树 + 随机 + 跳转 + 托盘 + 自启 + 扫码 + PWA + 打包**
* SMTC（Windows 系统媒体传输控制）适配器：读取任意媒体会话的曲目 / 歌手
* OBS / Spotify / 浏览器标签页等开箱适配器示例
* 适配器插件化（pip 安装即用）
* 多设备会话：多个手机同时连接、状态同步
