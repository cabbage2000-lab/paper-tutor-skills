"""从 `_shared/tailwind.config.js` 解析设计 token —— 色值与字栈的单一事实来源。

四层语义色是产品死线，色值的唯一权威是那份 config（见 `references/四层内容标注.md`）。
本模块只搬运、不复制：任何 hex 都不许在 Python 源码里出现第二份，否则 config 改了、
产物不跟着改，两份真相必然漂移。

config 缺失时**抛 TokenError、不兜色值**——兜一份就是第二份真相（先例：
`paper-verify/scripts/report_html.py:_inline_tailwind_config` 同样拒绝兜底）。
"""
from __future__ import annotations

import pathlib
import re
from typing import Dict

# parents[2] = _shared/，其下 tailwind.config.js
CONFIG = pathlib.Path(__file__).resolve().parents[2] / "tailwind.config.js"

# 必备 token —— 缺任何一个都说明 config 被改坏了，早失败好于渲出一份没有四层色的产物
REQUIRED = (
    "paper", "paper-edge", "rule", "ink", "ink-soft", "ink-faint",
    "l1", "l1-bg", "l2", "l2-bg", "l3", "l3-bg", "l4", "l4-bg",
    "font-serif", "font-sans",
)

_NESTED = re.compile(r"(\w+):\s*\{([^}]*)\}")
_HEX = re.compile(r"'?([\w-]+)'?:\s*'(#[0-9a-fA-F]{3,8})'")


class TokenError(RuntimeError):
    """config 读不到 / 解析不出必备 token。调用方应如实报错，不得静默降级。"""


def _colors(cfg: str) -> Dict[str, str]:
    """抓 colors 段。嵌套组（ink / l1..l4）先抓，抓完从文本里剔除再抓扁平键，
    否则扁平正则会把嵌套组内部的 DEFAULT / bg / soft 当成顶层键抓上来。"""
    try:
        block = cfg.split("colors: {", 1)[1].split("fontFamily", 1)[0]
    except IndexError:
        raise TokenError("tailwind.config.js 里找不到 colors 段")
    out: Dict[str, str] = {}
    for group, body in _NESTED.findall(block):
        for key, hexv in _HEX.findall(body):
            out[group if key == "DEFAULT" else f"{group}-{key.lower()}"] = hexv
    for key, hexv in _HEX.findall(_NESTED.sub("", block)):
        out[key] = hexv
    return out


def _fonts(cfg: str) -> Dict[str, str]:
    """把 fontFamily 的 JS 数组拍成一条 CSS font-family 值。"""
    out: Dict[str, str] = {}
    for name in ("serif", "sans"):
        m = re.search(name + r":\s*\[(.*?)\]", cfg, re.S)
        if not m:
            continue
        items = [x.strip().strip("',\"") for x in m.group(1).split(",")]
        stack = [x for x in items if x]
        # 含空格的字族名要带引号，CSS 才认（'Source Han Serif SC'）
        out[f"font-{name}"] = ", ".join(
            f"'{x}'" if " " in x and not x.startswith("'") else x for x in stack
        )
    return out


def load(config_path: pathlib.Path = None) -> Dict[str, str]:
    """读 config，返回 {token 名: 值}。色值键如 `l1` / `l1-bg`，字栈键 `font-serif`。"""
    path = config_path or CONFIG
    try:
        cfg = path.read_text(encoding="utf-8")
    except OSError as e:
        raise TokenError(
            f"读不到设计 token 文件 {path}——四层语义色的唯一权威在那里，"
            f"本渲染器不内置备份色值。请确认 skill 目录完整。"
        ) from e
    tokens = _colors(cfg)
    tokens.update(_fonts(cfg))
    missing = [k for k in REQUIRED if k not in tokens]
    if missing:
        raise TokenError(f"{path} 缺必备 token：{'、'.join(missing)}")
    return tokens
