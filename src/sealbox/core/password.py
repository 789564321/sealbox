"""一次性密码生成。

默认使用 uuid4 的 32 位十六进制形式：122 bit 熵、纯 ASCII、无歧义字符，
既满足“不可重复”的要求，又不会在命令行/剪贴板/跨平台编码里出问题。
"""

from __future__ import annotations

import secrets
import string
import uuid

STYLES = ("short22", "hex32", "uuid", "uuid+rand", "mixed62")

LABELS = {
    "short22": "短 UUID（22 位）",
    "hex32": "32 位十六进制",
    "uuid": "标准 UUID",
    "uuid+rand": "UUID + 32 位随机",
    "mixed62": "大小写混合（32 位）",
}

ENTROPY_BITS = {"short22": 122, "hex32": 122, "uuid": 122, "uuid+rand": 250, "mixed62": 190}

DEFAULT_STYLE = "short22"

# base57：去掉 0/O/I/l 这类易混字符，避免抄错。
_SHORT_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_MIXED_ALPHABET = string.ascii_letters + string.digits


def _short_uuid(data: bytes, length: int = 22) -> str:
    """把 16 字节 UUID 编码成固定长度的 base57 字符串。"""
    value = int.from_bytes(data, "big")
    if value == 0:
        return _SHORT_ALPHABET[0] * length
    out: list[str] = []
    while value:
        value, rem = divmod(value, len(_SHORT_ALPHABET))
        out.append(_SHORT_ALPHABET[rem])
    return "".join(reversed(out)).rjust(length, _SHORT_ALPHABET[0])


def generate(style: str = DEFAULT_STYLE) -> str:
    """生成一个密码字符串。每次调用都使用新的 uuid4，绝不复用。"""
    uid = uuid.uuid4()
    if style == "short22":
        return _short_uuid(uid.bytes, 22)
    if style == "hex32":
        return uid.hex
    if style == "uuid":
        return str(uid)
    if style == "uuid+rand":
        return uid.hex + secrets.token_hex(16)
    if style == "mixed62":
        return "".join(secrets.choice(_MIXED_ALPHABET) for _ in range(32))
    raise ValueError(f"未知的密码形态：{style}（可选 {', '.join(STYLES)}）")


def validate_style(style: str) -> str:
    if style not in STYLES:
        raise ValueError(f"未知的密码形态：{style}（可选 {', '.join(STYLES)}）")
    return style


def describe(style: str) -> dict[str, object]:
    validate_style(style)
    return {
        "style": style,
        "label": LABELS[style],
        "entropy_bits": ENTROPY_BITS[style],
    }
