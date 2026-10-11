# CompanionDeck 安装与使用手册

## 1. 环境要求

- Windows 10 / 11（需要 `.NET` 系统组件，Windows 自带）
- Python 3.10+（开发时使用 3.14 验证）
- 目标软件：Soundpad（推荐，原生接口）；或任意有全局热键/媒体会话的软件
- 手机/平板与电脑处于**同一局域网**（同一 Wi-Fi）

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

启动后终端显示类似：

```
========================================================
  CompanionDeck v0.1.0  局域网伴侣操控台
========================================================
  本机访问   : http://127.0.0.1:8390
  局域网访问 : http://192.168.1.5:8390   （手机需与电脑在同一网络）
  访问口令   : aB3xYz9QkLmNpQrS
  当前适配器 : Soundpad（原生接口）（未运行/不可用）
========================================================
```

> 提示：首次运行会自动生成 `config.json`（含口令）。显示「未运行/不可用」说明 Soundpad 没在运行，启动 Soundpad 后刷新页面即可。

## 4. 手机连接

1. 手机连接与电脑相同的 Wi-Fi
2. 浏览器打开终端显示的「局域网访问」地址
3. 输入终端里的「访问口令」
4. 页面自动连接，开始控制

首次连接后口令保存在浏览器本地，下次免输入。

## 5. 防火墙

首次启动时 Windows 可能弹出防火墙提示，请勾选**专用网络**并允许访问。若手机无法打开页面：

```bat
:: 手动放行（管理员 PowerShell）
netsh advfirewall firewall add rule name="CompanionDeck" dir=in action=allow protocol=TCP localport=8390
```

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

## 7. 常见问题排查

| 现象 | 原因与解决 |
| --- | --- |
| 页面打不开 | 手机与电脑不在同一网络；防火墙未放行（见第 5 节）；端口被占用（换 `server.port`） |
| 提示「需要访问口令」 | 输入终端显示的「访问口令」；口令在 `config.json` 的 `auth.token` |
| 显示「目标离线」 | Soundpad 未运行；或 Soundpad 版本过旧（RC 接口需 v1.0+，2019 年后版本均支持） |
| 切歌/播放无反应 | 确认当前激活适配器正确；`profile` 方案需对应软件已设置相同全局热键 |
| 声音面板为空 | Soundpad 声音列表为空；或列表超过 500 项只显示前 500 |
| 音量滑杆不出现 | 当前适配器不支持读取音量（如 `mediakeys` 只能 ± 不能读） |
| 端口被占用 | 修改 `config.json` 的 `server.port`，或用 `python -m deck --port 8391` 临时指定 |

## 8. 停止与卸载

- 停止：关闭运行窗口，或 Ctrl+C
- 卸载：删除整个 `companion-deck` 目录即可（配置与口令在其中，如需保留请先备份 `config.json`）
