#!/usr/bin/env python3
"""产物 Markdown → 学术档案风 HTML（纯转换、零依赖、断网可用）。

各产物型 skill 的 HTML 视图统一由本脚本渲染，宿主 agent 不再手写 HTML——HTML 是 MD 的
机械投影，逐字手写既费 token 又容易静默出错。渲染实现在
`_shared/paper_shared/report/`，本文件只做 CLI 包装。

用法：
    python3 skills/_shared/scripts/render_report.py --in manuscript/论证链检查.md \\
        --skill paper-logic

    # paper-screen：先让 screen.py 产 SVG，再内嵌进产物（产物自包含）
    python3 skills/paper-screen/scripts/screen.py --ledger 台账.md --svg prisma.svg
    python3 skills/_shared/scripts/render_report.py --in 系统综述筛选报告.md \\
        --skill paper-screen --embed-svg prisma.svg

退出码：0 成功 / 1 设计 token 读不到（skill 目录不完整）/ 2 输入输出路径问题。
非零退出时**不产出半成品**——宿主 agent 应如实声明「HTML 视图未生成」、只交 `.md`，
绝不手写一份顶替。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

# 标准三行引导头（同 paper-doctor/scripts/doctor.py）：parents[1] = _shared/
_SHARED = pathlib.Path(__file__).resolve().parents[1]
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from paper_shared import report  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="产物 Markdown → 单文件 HTML 视图（纯转换，零外部依赖）。")
    p.add_argument("--in", dest="src", required=True, help="输入 Markdown 产物")
    p.add_argument("--out", dest="dst", help="输出 HTML（默认同名 .html）")
    p.add_argument("--skill", help="skill 名，用于档案条（如 paper-logic）")
    p.add_argument("--embed-svg", dest="svg", action="append", metavar="FILE",
                   help="内嵌 SVG 文件（可重复）；MD 里用 ![说明](该文件名) 引用")
    args = p.parse_args(argv)

    src = pathlib.Path(args.src)
    if not src.is_file():
        sys.stderr.write(f"读不到输入文件：{src}\n")
        return 2

    svg = {}
    for item in args.svg or []:
        path = pathlib.Path(item)
        if not path.is_file():
            sys.stderr.write(f"读不到 SVG：{path}\n")
            return 2
        text = path.read_text(encoding="utf-8")
        svg[str(path)] = svg[path.name] = text

    try:
        dst = report.write(src, args.dst, skill=args.skill, svg=svg)
    except report.TokenError as e:
        sys.stderr.write(f"{e}\n")
        return 1
    except OSError as e:
        sys.stderr.write(f"写不出产物：{e}\n")
        return 2
    sys.stderr.write(f"已生成 {dst}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
