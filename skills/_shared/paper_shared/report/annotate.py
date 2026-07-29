"""四层内容标注染色 —— 把 MD 里的行内 emoji 包成带色标签。

权威定义在 `_shared/references/四层内容标注.md`：**符号是死线**（👤 t1 用户原话 /
📋 t2 常见事实 / 🪞 t3 系统归纳 / ❓ t4 待用户决定），语义名的措辞允许变体。
`tests/test_shared_conventions.py` 守着符号不漂移，所以按符号染色是可靠的。

两个必须区分的特例：

* **paper-disclose 用的是另一个轴**（组件库 §1.6 / 四层内容标注.md「另立色轴的特例」）。
  它的 👤 是「导师带教」、📋 是「研究生院合规」——语义与四层完全不同，按四层上色会上错。
  判据是元表里那一行的键：`读者导引` → 读者轴，`内容标注` → 四层。
* **paper-draft 有三枚私有补充符号**（SKILL.md 的 5 枚标注）：⚠️ 未经文献支撑、
  ✍️ 模仿用户风格、🤖 中性默认。它们是四层之外的补充轴，就近映射到相邻语义层。

paper-import 只有 📋/🪞/❓ 三枚（它改用 `.st` 状态徽章族，见四层内容标注.md
「不适用的场景」）——缺的符号不出现即不染，天然兼容。
"""
from __future__ import annotations

import re
from typing import Dict

# 四层内容标注（死线符号 → 色档）
LAYER: Dict[str, str] = {"👤": "t1", "📋": "t2", "🪞": "t3", "❓": "t4"}

# paper-draft 私有补充轴 → 就近映射到四层色档
DRAFT: Dict[str, str] = {"⚠️": "t4", "✍️": "t3", "🤖": "t2"}

# paper-disclose 读者标签轴（组件库 §1.6）
READER: Dict[str, str] = {"👤": "r1", "📋": "r2", "🔎": "r3", "🛡️": "r4"}

# 元表里声明读者轴的键。命中则整份产物切到 r1-r4
READER_KEYS = ("读者导引", "读者标签", "读者轴")

_VS16 = "️"     # 变体选择符：⚠️ / ✍️ / 🛡️ 带它，⚠ / ✍ / 🛡 不带，两种都要认


def axis(meta_keys) -> Dict[str, str]:
    """按元表的键选色轴。默认四层，命中读者键则切读者轴。"""
    for k in meta_keys:
        if any(rk in k for rk in READER_KEYS):
            return READER
    return dict(LAYER, **DRAFT)


def _pattern(mapping: Dict[str, str]) -> "re.Pattern[str]":
    """按符号长度倒序，保证带变体选择符的先匹配（否则 ⚠ 先命中、留下裸 FE0F）。"""
    syms = sorted(mapping, key=len, reverse=True)
    alts = "|".join(re.escape(s.rstrip(_VS16)) + _VS16 + "?" for s in syms)
    return re.compile(f"({alts})")


def apply(escaped_html: str, mapping: Dict[str, str]) -> str:
    """在**已转义**的文本里把标注符号包成 `<span class="tag-inline tN">`。

    必须作用于转义后的文本：先包标签再转义会把 span 自己转义掉。emoji 不受
    `html.escape` 影响，所以这个顺序是安全的。
    """
    lookup = {s.rstrip(_VS16): cls for s, cls in mapping.items()}

    def sub(m: "re.Match[str]") -> str:
        sym = m.group(1)
        cls = lookup.get(sym.rstrip(_VS16))
        if not cls:
            return sym
        return f'<span class="tag-inline {cls}">{sym}</span>'

    return _pattern(mapping).sub(sub, escaped_html)


def swatches(label_row: str, mapping: Dict[str, str]):
    """从元表标注行解析图例条目，返回 [(符号, 语义名, 色档)]。

    直接读 MD 原文而非从 mapping 反推——语义名允许有措辞变体（`paper-review` 的 t2 是
    「模拟常见审稿维度（非推荐）」、`paper-figure` 的 t2 是「常见图类陈列」），
    反推只能给出通用名，会把这些变体抹平。
    """
    lookup = {s.rstrip(_VS16): cls for s, cls in mapping.items()}
    out = []
    for seg in re.split(r"[·•]", label_row):
        seg = seg.replace("　", " ").strip()
        if not seg:
            continue
        m = _pattern(mapping).match(seg)
        if not m:
            continue
        sym = m.group(1)
        cls = lookup.get(sym.rstrip(_VS16))
        if cls:
            out.append((sym, seg[m.end():].strip(), cls))
    # 按 t1-t4 / r1-r4 的权威顺序，图例顺序不随 MD 的书写顺序漂移
    order = ("t1", "t2", "t3", "t4", "r1", "r2", "r3", "r4")
    return sorted(out, key=lambda p: order.index(p[2]) if p[2] in order else len(order))
