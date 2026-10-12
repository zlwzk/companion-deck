# CompanionDeck 安装与使用手册

## 1. 环境要求

- Windows 10 / 11（需要 `.NET` 系统组件，Windows 自带）
- Python 3.10+（开发时使用 3.14 验证）
- 目标软件：Soundpad（推荐，原生接口）；或任意有全局热键/媒体会话的软件
- 控制端（手机/平板）与电脑的连通方式（全部为系统自带能力，**无需安装任何第三方软件**）：
  - **局域网**：同一 Wi-Fi / 同一路由器下
  - **电脑热点**：手机连电脑自带的「移动热点」，打游戏时最方便
  - **公网直连**：用家宽自带的 IPv6，或公网 IPv4 + 路由器端口转发（见第 8 节），人在外面也能控制

## 2. 安装

方式 A：双击 `run.bat`（首次自动创建虚拟环境并安装依赖）。

方式 B：手动安装

```bat
cd companion-deck
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## 3. 启动

```bat
.venv\Scripts\python -m deck
```

启动后终端显示类似（含 ASCII 二维码，可用手机相机扫码直连）：

```
============================================================
  CompanionDeck v0.1.0  伴侣操控台（局域网直连）
============================================================
  本机访问   : http://127.0.0.1:8390
  ★ 局域网  : http://192.168.1.5:8390   （手机连同一 Wi-Fi）
    电脑热点 : http://192.168.137.1:8390   （手机连电脑移动热点）
  访问口令   : aB3xYz9QkLmNpQrS
  扫码直连   : http://192.168.1.5:8390?token=aB3xYz9QkLmNpQrS  （手机相机扫码即可）
  当前适配器 : Soundpad（原生接口）（未运行/不可用）
  系统托盘   : 已启用
  开机自启   : 未启用（用 --autostart on/off 切换）
============================================================

  ██████████ ██████████ ██████████ ██████████ ...
  ↑ 用手机相机扫描即可连接（已包含口令）
```

> 提示：首次运行会自动生成 `config.json`（含口令）。显示「未运行/不可用」说明 Soundpad 没在运行，启动 Soundpad 后刷新页面即可。
>
> 打游戏时手机连电脑热点最方便；同一 Wi-Fi 用「局域网」地址或扫上方二维码即可。

## 4. 手机连接（局域网）

1. 手机连接与电脑相同的 Wi-Fi
2. **方式一（扫码直连，推荐）**：用手机相机或扫码 App 扫描终端里的 ASCII 二维码，自动打开 CompanionDeck 网页（口令已包含在 URL 中，免输入）
3. **方式二（手动）**：浏览器打开终端显示的「局域网访问」地址，输入终端里的「访问口令」
4. 页面自动连接，开始控制
5. **可选**：浏览器菜单选「添加到主屏」，下次像 App 一样从桌面打开（PWA 支持）

首次连接后口令保存在浏览器本地，下次免输入。

> 也可以在已连接的网页上点右上角「▦」按钮，弹窗里有一张更大的 SVG 二维码，给身边朋友扫码即连。

## 5. 防火墙

首次启动时 Windows 可能弹出防火墙提示，请勾选**专用网络**并允许访问。若手机无法打开页面：

```bat
:: 手动放行（管理员 PowerShell）
netsh advfirewall firewall add rule name="CompanionDeck" dir=in action=allow protocol=TCP localport=8390
```

> 说明：公网直连（IPv6/端口转发）走的入站流量同样由 Windows 防火墙控制，本条规则已覆盖 TCP 8390 的 IPv4 与 IPv6 入站。

## 6. 配置详解（config.json）

| 字段 | 说明 |
| --- | --- |
| `server.host` / `server.port` | 监听地址与端口（默认 0.0.0.0:8390） |
| `auth.enabled` / `auth.token` | 访问口令开关与口令（留空自动生成） |
| `active_adapter` | 启动时激活的适配器：`soundpad` / `mediakeys` / `profile` |
| `adapters.soundpad.sounds` | 声音面板按钮（留空则自动从 Soundpad 列表生成） |
| `adapters.profile.profiles` | 自定义热键方案列表 |
| `adapters.profile.active_profile` | 当前激活的热键方案 |

修改配置后重启服务生效。

### 声音按钮示例

```json
"adapters": {
  "soundpad": {
    "enabled": true,
    "sounds": [
      { "name": "大笑", "kind": "hotkey", "hotkey": ["ctrl", "alt", "1"] },
      { "name": "欢呼", "kind": "index",  "index": 3 }
    ]
  }
}
```

- `kind: "hotkey"`：触发一组组合键（需先在 Soundpad 里给该声音设置相同的全局热键）
- `kind: "index"`：按「所有声音」分类中的列表索引播放（对应 RC 接口 `DoPlaySound(index)`）

### 自定义热键方案示例（适配任意软件）

```json
"profiles": [
  {
    "name": "我的 OBS",
    "description": "OBS 全局热键",
    "hotkeys": {
      "play_pause": ["ctrl", "alt", "p"],
      "volume_up":   ["ctrl", "alt", "up"],
      "volume_down": ["ctrl", "alt", "down"]
    }
  }
]
```

支持的组合键：`ctrl` / `alt` / `shift` / `win`、字母、数字、`F1`-`F24`、`space` / `enter` / `esc` / `tab`、方向键、`media_play_pause` / `media_next` / `media_prev` / `media_stop` / `volume_up` / `volume_down` / `volume_mute` 等（详见 `deck/hotkeys.py` 的 `VK_MAP`）。

## 7. 安全说明

- **访问口令默认开启**：任何通道（含公网直连）没有口令都无法控制
- 公网直连时建议**换一个不常用的端口**（`config.json` 的 `server.port`，如 4 万以上），降低被扫描命中概率
- **只转发 CompanionDeck 这一个端口**，不要把整台电脑的其他端口（22/RDP 等）暴露到公网
- 若担心暴露面，可将 `auth.enabled` 保持开启 + 定期更换 `auth.token`（改完重启生效）
- `config.json` 含口令，已被 `.gitignore` 排除，**切勿提交仓库**

## 8. 手机控制（局域网直连，零第三方软件）

本项目**不依赖任何组网软件 / 隧道服务**。手机与电脑之间直接走网络：同一 Wi-Fi 或电脑热点即可（焦点场景）。如需人在外面也能控制，可选用 IPv6 直连或公网 IPv4 端口转发（可选通道）。启动时终端会列出当前可用的所有通道地址，按场景选择即可。

### 8.1 通道一：同一 Wi-Fi（零配置）

手机连与电脑相同的 Wi-Fi，打开终端显示的「局域网」地址即可。适合普通居家场景。

### 8.2 通道二：电脑移动热点（打游戏推荐）

打游戏时手机想低延迟、稳定控制，用 Windows 自带的「移动热点」：

1. 电脑设置 → 网络和 Internet → **移动热点** → 开启（无需下载任何软件）
2. 手机 Wi-Fi 列表连接这个热点
3. 打开终端显示的「电脑热点」地址（`192.168.137.1:8390`）即可

> 手机连电脑热点时走电脑的网络，稳定低延迟；控制 Soundpad 全程后台进行，不抢游戏焦点。

### 8.3 通道三：IPv6 直连（人在外面）

国内家宽普遍有公网 IPv6，手机流量网络也支持 IPv6——这是「人在外面也能控制」的零依赖方案：

1. **确认电脑有 IPv6**：终端横幅出现「IPv6 直连」行即代表已获得全局 IPv6 地址
2. **路由器放行一次**：登录路由器管理页，在防火墙 / IPv6 设置中**放行 TCP 8390 入站**（不同路由器菜单不同，一般叫「IPv6 防火墙」「端口放行」「入站规则」）
3. **Windows 防火墙**：第 5 节规则已覆盖 IPv6 入站，无需重复
4. 手机（用流量或任意网络）打开终端里的 `http://[IPv6地址]:8390` 即可

> 小提示：家庭 IPv6 前缀一般数小时到数天变化一次，重新启动 CompanionDeck 或看横幅即可拿到最新地址；若想长期固定，可在 Windows 网卡属性中手动配置一个固定 IPv6 地址（`netsh interface ipv6 add address`）。

### 8.4 通道四：公网 IPv4 + 路由器端口转发（可选）

如果宽带是**公网 IPv4**（不是大内网）：

1. 在路由器管理页找到「端口转发 / 虚拟服务器」，新增一条：**外部端口 8390 → 内网 IP（电脑的局域网地址）8390，协议 TCP**
2. 手机用任意网络打开 `http://<公网IP>:8390`（启动横幅会探测并提示本网络出口公网 IP）
3. 公网 IP 变化时可自行选用任意 DDNS 服务绑定域名（属可选优化，非本项目依赖）

> 如何判断是不是公网 IPv4：把路由器 WAN 口 IP 与启动横幅探测到的出口公网 IP 对比，一致即为公网。

### 8.5 故障排查（远程）

| 现象 | 原因与解决 |
| --- | --- |
| 横幅没有「IPv6 直连」 | 路由器未开启 IPv6 或运营商未下发；联系宽带运营商开启 IPv6 |
| 手机打不开 IPv6 地址 | 路由器未放行 TCP 8390 入站（见 8.3 第 2 步）；手机网络不支持 IPv6（换流量网络试试） |
| 打不开公网 IPv4 地址 | 宽带是大内网（无公网 IP）；或路由器未做端口转发；或防火墙未放行 |
| 热点通道连不上 | 确认手机连的是电脑热点而非家里 Wi-Fi；热点 IP 以横幅显示为准 |
| 提示「需要访问口令」 | 输入终端显示的口令；公网场景下口令必须保留开启 |
| 网址打不开但本机能开 | 端口被占用或防火墙拦截；检查 `netsh advfirewall` 规则与 `server.port` |

## 9. 常见问题排查（局域网 / 通用）

| 现象 | 原因与解决 |
| --- | --- |
| 页面打不开 | 手机与电脑不在同一网络；防火墙未放行（见第 5 节）；端口被占用（换 `server.port`） |
| 提示「需要访问口令」 | 输入终端显示的「访问口令」；口令在 `config.json` 的 `auth.token` |
| 显示「目标离线」 | Soundpad 未运行；或 Soundpad 版本过旧（RC 接口需 v1.0+，2019 年后版本均支持） |
| 切歌/播放无反应 | 确认当前激活适配器正确；`profile` 方案需对应软件已设置相同全局热键 |
| 声音面板为空 | Soundpad 声音列表为空；或列表超过 500 项只显示前 500 |
| 音量滑杆不出现 | 当前适配器不支持读取音量（如 `mediakeys` 只能 ± 不能读） |
| 端口被占用 | 修改 `config.json` 的 `server.port`，或用 `python -m deck --port 8391` 临时指定 |

## 10. 停止与卸载

- 停止：关闭运行窗口，或 Ctrl+C，或从系统托盘菜单选「退出」
- 卸载：删除整个 `companion-deck` 目录即可（配置与口令在其中，如需保留请先备份 `config.json`）
- 如已启用开机自启，先用 `.venv\Scripts\python -m deck --autostart off` 取消注册表项

## 11. 系统托盘与开机自启

启动时默认创建系统托盘图标（ ctypes 调 Shell_NotifyIcon，零第三方库）：

- **左键单击 / 双击**：打开本机浏览器
- **右键菜单**：「打开网页控制台」「退出」
- 用 `--no-tray` 启动可禁用托盘

开机自启通过注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\CompanionDeck` 实现：

```bat
:: 启用
.venv\Scripts\python -m deck --autostart on

:: 查询
.venv\Scripts\python -m deck --autostart status

:: 禁用
.venv\Scripts\python -m deck --autostart off
```

打包成 exe 后（见下一节），开机自启的命令行会自动指向 `CompanionDeck.exe`。

## 12. 打包为单文件 exe（PyInstaller）

```bat
build.bat
```

首次会自动创建虚拟环境并安装 `pyinstaller`，打包产物为 `dist\CompanionDeck.exe`：

- **双击即可运行**，无需安装 Python，可拷贝到任意 Windows 电脑
- 包含所有依赖（FastAPI / uvicorn / qrcode / PIL）
- 包含 Web 资源（HTML / CSS / JS / manifest / service worker）
- 当前为控制台程序（启动时能看到终端横幅与二维码）；如需完全无窗口，可改 `companion-deck.spec` 里 `console=False`

## 13. 分类树、随机播放与进度跳转（Soundpad 新能力）

| 功能 | 触发位置 | RC 协议命令 |
| --- | --- | --- |
| 按分类浏览声音 | 顶部 Tab | `GetCategories(true, false)` |
| 切换激活分类 | Tab 点击 / ‹ › 按钮 | `DoSelectCategory` / `DoSelectPreviousCategory` / `DoSelectNextCategory` |
| 按分类内位置播放 | 声音按钮 | `DoPlaySoundFromCategory(catIdx, soundPos, true, false)` |
| 全局随机播放 | 传输区「🎲」按钮 | `DoPlayRandomSound(true, false)` |
| 分类内随机播放 | 声音面板上方「🎲 当前分类随机」 | `DoPlayRandomSoundFromCategory(catIdx, true, false)` |
| 进度跳转 | 拖动进度条 | `DoSeekMs(pos)` |
| 相对跳转 | （API） | `DoJumpMs(delta)` |
| 重播当前 | （API） | `DoPlayCurrentSoundAgain()` |

> 当前播放声音的 artist / 标题 / 播放次数自动从 `GetSoundlist()` 元数据映射（按时长 + 播放次数模糊匹配）。

## 14. PWA（手机加桌面）

首次用浏览器打开页面后：

- **Chrome / Edge / Safari**：菜单 → 「添加到主屏幕」/「安装」
- 桌面会出现 CompanionDeck 图标，点开像独立 App 一样全屏运行
- service worker 缓存静态资源，断网时仍能打开页面（实时状态走 WebSocket，离线时会显示「目标离线」）
