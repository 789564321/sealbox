"""一次性密码生成。

默认使用 uuid4 的 32 位十六进制形式：122 bit 熵、纯 ASCII、无歧义字符，
既满足“不可重复”的要求，又不会在命令行/剪贴板/跨平台编码里出问题。
"""

from __future__ import annotations

import secrets
import uuid

STYLES = ("hex32", "uuid", "uuid+rand")

LABELS = {
    "hex32": "32 位十六进制",
    "uuid": "标准 UUID",
    "uuid+rand": "UUID + 32 位随机",
}

ENTROPY_BITS = {"hex32": 122, "uuid": 122, "uuid+rand": 250}


def generate(style: str = "hex32") -> str:
    """生成一个密码字符串。每次调用都使用新的 uuid4，绝不复用。"""
    uid = uuid.uuid4()
    if style == "hex32":
        return uid.hex
    if style == "uuid":
        return str(uid)
    if style == "uuid+rand":
        return uid.hex + secrets.token_hex(16)
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
