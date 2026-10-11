# CompanionDeck 安装与使用手册

## 1. 环境要求

- Windows 10 / 11（需要 `.NET` 系统组件，Windows 自带）
- Python 3.10+（开发时使用 3.14 验证）
- 目标软件：Soundpad（推荐，原生接口）；或任意有全局热键/媒体会话的软件
- 控制端（手机/平板）与电脑的连通方式二选一：
  - **局域网**：同一 Wi-Fi / 同一路由器下
  - **互联网**：通过 ZeroTier（或 Tailscale）组网（推荐，见第 8 节），人在外面也能控制

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
  CompanionDeck v0.1.0  伴侣操控台（局域网 / 互联网）
========================================================
  本机访问   : http://127.0.0.1:8390
  局域网访问 : http://192.168.1.5:8390   （手机需与电脑在同一网络）
  互联网远程 : http://100.64.2.18:8390   （Tailscale，全球可访问）
  远程域名   : http://mypc.tailnet.ts.net:8390   （Tailscale MagicDNS）
  访问口令   : aB3xYz9QkLmNpQrS
  当前适配器 : Soundpad（原生接口）（未运行/不可用）
========================================================
```

> 提示：首次运行会自动生成 `config.json`（含口令）。显示「未运行/不可用」说明 Soundpad 没在运行，启动 Soundpad 后刷新页面即可。
>
> 如果终端显示「未检测到 ZeroTier / Tailscale」，说明电脑还没装组网工具，按第 8 节操作即可开启互联网远程。

## 4. 手机连接（局域网）

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

> 说明：Tailscale 远程访问走虚拟网卡，不经过这条规则，一般无需放行。

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

- **访问口令默认开启**：即使暴露到互联网，没有口令也无法控制
- 互联网远程**推荐使用 ZeroTier（或 Tailscale）私有组网**：流量加密、设备间私有网络，不暴露公网端口
- **不要**直接做路由器端口转发把 8390 暴露到公网——等于把控制入口挂到互联网上，风险高
- `config.json` 含口令，已被 `.gitignore` 排除，**切勿提交仓库**

## 8. 互联网远程控制（ZeroTier）

ZeroTier 是私有虚拟组网工具：电脑和手机加入同一个网络后，就像处于一个虚拟局域网里，**不要求同一 Wi-Fi、不需要公网 IP、不需要路由器设置**，且邮箱注册即可、无需 Google 等第三方账号。

### 8.1 安装与加入网络

1. **电脑端**：下载安装 [ZeroTier](https://www.zerotier.com/download/)（Windows），安装后托盘图标出现
2. **创建网络**：访问 [my.zerotier.com](https://my.zerotier.com) 注册账号 → 创建 Network（记下 16 位 Network ID），或加入别人创建的网络
3. **电脑加入**：托盘图标 → Join Network → 输入 Network ID；在 my.zerotier.com 该网络页面勾选电脑的 **Auth?** 授权
4. **手机端**：App Store / 应用商店安装 **ZeroTier One**，用同一账号登录，Join 同一个 Network ID，并在网页端授权手机设备

### 8.2 获取远程地址

电脑加入网络后会自动获得一个 `25.x.x.x` 地址。查看方式：

```bat
:: 列出已加入网络及分配的 IP
"C:\Program Files (x86)\ZeroTier One\zerotier-cli.exe" listnetworks
```

或在 my.zerotier.com 网络页面看电脑设备旁显示的 IP（形如 `25.10.2.3`）。

### 8.3 启动并连接

1. 照常启动 CompanionDeck，终端会显示：

   ```
   互联网远程 : http://25.x.x.x:8390   （ZeroTier，全球可访问）
   ```

2. 手机（无论身在何处，只要有网且 ZeroTier 保持连接）打开该地址，输入访问口令即可控制

> 同一时间局域网访问依然可用，两种方式互不影响。

### 8.4 故障排查（远程）

| 现象 | 原因与解决 |
| --- | --- |
| 终端未显示「互联网远程」 | 电脑未装 ZeroTier 或未加入网络/未授权；加入并授权后重启 CompanionDeck |
| 手机打不开远程地址 | 手机 ZeroTier 未加入同一 Network ID 或未授权；App 需保持连接状态 |
| 网页端看不到设备 | my.zerotier.com 网络页面勾选设备 **Auth?** 授权 |
| 提示「需要访问口令」 | 输入终端显示的口令；远程场景下口令必须保留开启 |

### 8.5 备选：Tailscale（若可用）

如果所在网络能访问 [Tailscale](https://tailscale.com/download)，也可用 Tailscale 替代（WireGuard 私有组网，登录需 Google/微软/GitHub 账号）。安装登录后 CompanionDeck 会自动识别其 `100.x.x.x` 地址并在终端显示。ZeroTier 与 Tailscale 可共存，同时安装时终端会分别列出。

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

- 停止：关闭运行窗口，或 Ctrl+C
- 卸载：删除整个 `companion-deck` 目录即可（配置与口令在其中，如需保留请先备份 `config.json`）
