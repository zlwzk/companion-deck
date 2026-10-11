# CompanionDeck 安装与使用手册

## 1. 环境要求

- Windows 10 / 11（需要 `.NET` 系统组件，Windows 自带）
- Python 3.10+（开发时使用 3.14 验证）
- 目标软件：Soundpad（推荐，原生接口）；或任意有全局热键/媒体会话的软件
- 控制端（手机/平板）与电脑的连通方式二选一：
  - **局域网**：同一 Wi-Fi / 同一路由器下
  - **互联网**：通过 Tailscale 组网（推荐，见第 8 节），人在外面也能控制

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
> 如果终端显示「未检测到 Tailscale」，说明电脑还没装 Tailscale，按第 8 节操作即可开启互联网远程。

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
- 互联网远程**强烈推荐使用 Tailscale**：流量经 WireGuard 加密、设备间私有组网，不暴露公网端口
- **不要**直接做路由器端口转发把 8390 暴露到公网——等于把控制入口挂到互联网上，风险高
- `config.json` 含口令，已被 `.gitignore` 排除，**切勿提交仓库**

## 8. 互联网远程控制（Tailscale）

Tailscale 是基于 WireGuard 的私有组网工具：电脑和手机登录同一个账号后，就像在一个虚拟局域网里，**不要求同一 Wi-Fi、不需要公网 IP、不需要路由器设置**。

### 8.1 安装与登录

1. **电脑端**：下载安装 [Tailscale](https://tailscale.com/download)（Windows），用你的账号（微软/谷歌/GitHub 均可）登录
2. **手机端**：App Store / 应用商店搜索 **Tailscale**，安装后用**同一个账号**登录
3. 两侧都登录后，在电脑 Tailscale 界面确认手机设备已出现（MagicDNS 默认开启）

### 8.2 获取远程地址

在电脑终端执行：

```bat
tailscale ip -4
```

会输出一个 `100.x.x.x` 地址。或者看 Tailscale 界面里电脑的名称（如 `mypc.tailnet.ts.net`）。

### 8.3 启动并连接

1. 照常启动 CompanionDeck，终端会显示：

   ```
   互联网远程 : http://100.x.x.x:8390   （Tailscale，全球可访问）
   远程域名   : http://mypc.tailnet.ts.net:8390   （Tailscale MagicDNS）
   ```

2. 手机（无论身在何处，只要有网）打开该地址，输入访问口令即可控制

> 同一时间局域网访问依然可用，两种方式互不影响。

### 8.4 故障排查（远程）

| 现象 | 原因与解决 |
| --- | --- |
| 终端未显示「互联网远程」 | 电脑未装 Tailscale 或未登录；安装登录后重启 CompanionDeck |
| 手机打不开远程地址 | 手机 Tailscale 未登录同一账号；手机没开 Tailscale（App 需保持连接状态） |
| 提示「需要访问口令」 | 输入终端显示的口令；远程场景下口令必须保留开启 |
| 域名打不开但 IP 能开 | MagicDNS 未开启：Tailscale 管理后台 → DNS → 开启 MagicDNS |

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
