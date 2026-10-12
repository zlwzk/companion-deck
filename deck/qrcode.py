"""二维码生成（用于扫码直连）。

依赖 `qrcode` 库（run.bat 会自动 pip install）；运行时无系统依赖。
若未安装该库，调用方应优雅降级为不显示 QR 而非崩溃。
"""

from __future__ import annotations

try:
    import qrcode as _qrcode  # type: ignore
except Exception:  # noqa: BLE001
    _qrcode = None


def is_available() -> bool:
    return _qrcode is not None


def to_svg(text: str, scale: int = 8) -> str:
    """把文本编码成 SVG 字符串。"""
    if _qrcode is None:
        raise RuntimeError("qrcode 库未安装，无法生成二维码")
    qr = _qrcode.QRCode(
        version=None,
        error_correction=_qrcode.constants.ERROR_CORRECT_L,
        box_size=scale,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0b0e13", back_color="#ffffff").convert("RGB")
    # 用 Pillow 转 SVG 字符串（避免引入 svgwrite，直接拼字符串）
    return _image_to_svg(img, scale)


def _image_to_svg(img, scale: int) -> str:
    """把 PIL Image 转 SVG 字符串。"""
    width, height = img.size
    pixels = img.load()
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]
    # 用像素步长优化：检测模块大小
    # 简单方案：每个像素一个矩形（QR 一般 200x200 左右，可接受）
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y][:3]
            if r < 128 and g < 128 and b < 128:  # 深色
                parts.append(
                    f'<rect x="{x}" y="{y}" width="1" height="1" fill="#0b0e13"/>'
                )
    parts.append("</svg>")
    return "".join(parts)
