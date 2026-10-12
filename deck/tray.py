"""系统托盘驻留（Windows，零第三方库）。

用 ctypes 直接调用 Shell_NotifyIconW + 自定义窗口类，
托盘图标 + 右键菜单（打开/退出），左键双击打开浏览器。
在独立线程里跑消息循环，不影响 FastAPI 主循环。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import webbrowser
from pathlib import Path
from typing import Callable, Optional

# Shell_NotifyIcon 相关常量
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

WM_APP = 0x8000
WM_TRAY_ICON = WM_APP + 1
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_LBUTTONUP = 0x0202
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_QUIT = 0x0012

CS_VREDRAW = 0x0001
CS_HREDRAW = 0x0002
IDI_APPLICATION = 32512
SW_SHOW = 5

WS_EX_APPWINDOW = 0x00040000
WS_OVERLAPPEDWINDOW = 0x00CF0000

CS_CLASSNAME = "CompanionDeckTray"

IDM_OPEN = 1001
IDM_QUIT = 1002

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT),
        ("hIcon", wt.HICON),
        ("szTip", wt.WCHAR * 128),
        ("dwState", wt.DWORD),
        ("dwStateMask", wt.DWORD),
        ("szInfo", wt.WCHAR * 256),
        ("uVersion", wt.UINT),
        ("szInfoTitle", wt.WCHAR * 64),
        ("dwInfoFlags", wt.DWORD),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wt.HWND),
        ("message", wt.UINT),
        ("wParam", wt.WPARAM),
        ("lParam", wt.LPARAM),
        ("time", wt.DWORD),
        ("pt", POINT),
    ]


# 函数签名设置
_user32.RegisterClassExW.restype = wt.ATOM
_user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    wt.INT, wt.INT, wt.INT, wt.INT,
    wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p,
]
_user32.CreateWindowExW.restype = wt.HWND
_user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_user32.DefWindowProcW.restype = ctypes.c_long  # LRESULT
_user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wt.HWND, wt.UINT, wt.UINT]
_user32.GetMessageW.restype = wt.BOOL
_user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_user32.PostMessageW.restype = wt.BOOL
_user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
_user32.SetForegroundWindow.argtypes = [wt.HWND]
_user32.PostQuitMessage.argtypes = [ctypes.c_int]
_user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
_user32.TrackPopupMenu.argtypes = [
    wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, ctypes.c_void_p,
]
_user32.TrackPopupMenu.restype = wt.BOOL
_user32.LoadIconW.argtypes = [wt.HINSTANCE, wt.LPCWSTR]
_user32.LoadIconW.restype = wt.HICON

_shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
_shell32.Shell_NotifyIconW.restype = wt.BOOL

_kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wt.HMODULE

# 简单菜单
_user32.CreatePopupMenu.restype = wt.HMENU
_user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, wt.UINT, wt.LPCWSTR]
_user32.AppendMenuW.restype = wt.BOOL
_user32.DestroyMenu.argtypes = [wt.HMENU]


def is_supported() -> bool:
    """托盘是否在当前系统可用（仅 Windows 桌面环境）。"""
    try:
        return _user32.GetCursorPos is not None
    except Exception:  # noqa: BLE001
        return False


# 窗口过程的回调签名是 WNDPROC(HWND, UINT, WPARAM, LPARAM) -> LRESULT
# 这里用一个全局函数指针注册，因为 ctypes 不直接支持 Python 闭包作为回调
# 使用 CFUNCTYPE 包装
_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class TrayIcon:
    """系统托盘图标。需在 Windows 上调用，否则不工作。"""

    def __init__(self, title: str = "CompanionDeck", url: str = "",
                 icon_path: Optional[str] = None, on_quit: Optional[Callable] = None) -> None:
        self.title = title
        self.url = url
        self.icon_path = icon_path
        self.on_quit = on_quit
        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._stopped = threading.Event()
        self._proc = _WNDPROC(self._wnd_proc)

    def start(self) -> None:
        if not is_supported():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._hwnd:
            _user32.PostMessageW(self._hwnd, WM_QUIT, 0, 0)
        self._stopped.set()

    def _run(self) -> None:
        hinst = _kernel32.GetModuleHandleW(None)
        # 注册窗口类
        wc = WNDCLASSW()
        wc.style = CS_HREDRAW | CS_VREDRAW
        wc.lpfnWndProc = ctypes.cast(self._proc, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.lpszClassName = CS_CLASSNAME
        # 注意：使用 RegisterClassW（不带 Ex）
        try:
            atom = _user32.RegisterClassW(ctypes.byref(wc))
        except Exception:
            return
        # 创建一个消息专用隐藏窗口
        hwnd = _user32.CreateWindowExW(
            0, CS_CLASSNAME, "CompanionDeckTray", 0,
            0, 0, 0, 0, 0, 0, hinst, None,
        )
        if not hwnd:
            return
        self._hwnd = hwnd
        # 加载图标：优先自定义，否则用系统默认
        icon = self._load_icon(hinst)
        # 注册托盘
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY_ICON
        nid.hIcon = icon
        tip = (self.title or "CompanionDeck")[:127]
        nid.szTip = tip
        _shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        # 消息循环
        msg = MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
        # 退出时删托盘
        nid.uFlags = 0
        _shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        if self.on_quit:
            try:
                self.on_quit()
            except Exception:  # noqa: BLE001
                pass

    def _load_icon(self, hinst) -> int:
        if self.icon_path and Path(self.icon_path).exists():
            # 用 LoadImageW 加载自定义图标
            try:
                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x0010
                _user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT]
                _user32.LoadImageW.restype = wt.HANDLE
                handle = _user32.LoadImageW(
                    None, self.icon_path, IMAGE_ICON,
                    0, 0, LR_LOADFROMFILE,
                )
                if handle:
                    return int(handle)
            except Exception:  # noqa: BLE001
                pass
        # 默认应用图标
        return int(_user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION)))

    def _wnd_proc(self, hwnd, msg, w, l):
        if msg == WM_TRAY_ICON:
            mouse_msg = l & 0xFFFF
            if mouse_msg == WM_LBUTTONDBLCLK or mouse_msg == WM_LBUTTONUP:
                self._open_browser()
                return 0
            if mouse_msg == WM_RBUTTONUP:
                self._show_menu(hwnd)
                return 0
        elif msg == WM_COMMAND:
            menu_id = w & 0xFFFF
            if menu_id == IDM_OPEN:
                self._open_browser()
                return 0
            if menu_id == IDM_QUIT:
                _user32.PostQuitMessage(0)
                return 0
        elif msg == WM_DESTROY:
            _user32.PostQuitMessage(0)
            return 0
        return _user32.DefWindowProcW(hwnd, msg, w, l)

    def _open_browser(self) -> None:
        url = self.url or "http://127.0.0.1:8390"
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    def _show_menu(self, hwnd) -> None:
        menu = _user32.CreatePopupMenu()
        _user32.AppendMenuW(menu, 0, IDM_OPEN, "打开网页控制台")
        _user32.AppendMenuW(menu, 0, IDM_QUIT, "退出")
        pos = POINT()
        _user32.GetCursorPos(ctypes.byref(pos))
        _user32.SetForegroundWindow(hwnd)
        # TPM_LEFTALIGN | TPM_RIGHTBUTTON | TPM_BOTTOMALIGN
        flags = 0x0000 | 0x0002 | 0x0020
        _user32.TrackPopupMenu(menu, flags, pos.x, pos.y, 0, hwnd, None)
        _user32.DestroyMenu(menu)


# 在 Windows 注册窗口类的辅助函数
_user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
_user32.RegisterClassW.restype = wt.ATOM
