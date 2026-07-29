"""由设计 token 生成产物内联 CSS —— 学术档案纸面骨架，零外部依赖。

不走 Tailwind CDN（`paper-verify/scripts/report_html.py` 那条路）：产物落进用户项目后
要能断网打开、要满足各 skill SKILL.md 里「`grep -iE "https?://|<script src|cdn"` 期望
0 命中」的原始意图。放弃 skill 专属视觉组件后，需要的样式降到一屏，不必再背 Tailwind 引擎。

色值全部经 `:root` 自定义属性注入（唯一来源 `tokens.load()`），正文 CSS 因此是纯静态
字符串——不需要字符串格式化，也就不会与 CSS 自己的 `{}` 打架。

组件对应报告组件库：§2.1 `.page` / §2.2 `.doc-head` / §2.3 `.legend` / §2.4 `h2.section`
/ §2.5 `footer` / §2.6 body 底纹 / §2.7 rise / §2.8 `@media print` / §3.1 `.tag-inline`。
"""
from __future__ import annotations

from typing import Dict

# paper-disclose 读者标签轴。权威是报告组件库 §1.6，那里明定「不进 tailwind.config」
# （刻意与 l1-l4 分开、避免撞色），所以这四个色值只能在这里内联。
READER_COLORS = {
    "r1": ("#6b4a8f", "#ece6f3"),   # 👤 导师带教（靛紫）
    "r2": ("#6b7a3a", "#eef0e3"),   # 📋 研究生院合规（橄榄）
    "r3": ("#2a6b7a", "#e2eff2"),   # 🔎 期刊投稿（海蓝）
    "r4": ("#8f4a5a", "#f5e7ea"),   # 🛡️ AIGC 检测应对（暗红）
}

# rise 错峰动画的枚举级数。模板里最多 9 级，留 12 级 + n+13 兜底
_RISE_STEPS = 12

_STATIC = """
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;padding:0 1rem;
  background-color:var(--paper);
  background-image:linear-gradient(var(--paper-edge) 1px,transparent 1px),
                   linear-gradient(90deg,var(--paper-edge) 1px,transparent 1px);
  background-size:28px 28px;background-position:-1px -1px;
  color:var(--ink);font-family:var(--font-serif);line-height:1.85;
  font-size:16px;overflow-wrap:break-word;
}

/* §2.1 纸面容器 */
.page{
  max-width:880px;margin:3rem auto 5rem;padding:3.5rem 4rem;
  background:var(--paper);position:relative;
  border:1px solid var(--rule);border-top:6px solid var(--ink);
  box-shadow:0 1px 0 var(--paper-edge),0 30px 60px -30px rgba(60,45,20,.25);
}
.page::before{
  content:attr(data-label);
  position:absolute;top:-6px;right:0;
  background:var(--ink);color:var(--paper);
  font-family:var(--font-sans);font-size:10px;letter-spacing:.14em;
  text-transform:uppercase;padding:5px 12px 4px;font-weight:600;
}

/* §2.2 档案头 */
.doc-eyebrow{
  font-family:var(--font-sans);font-size:11px;letter-spacing:.28em;
  text-transform:uppercase;color:var(--ink-faint);margin-bottom:.6rem;
}
h1.doc-title{
  font-size:2.1rem;font-weight:700;line-height:1.25;
  margin:0 0 1rem;letter-spacing:.01em;
}
.doc-meta{
  display:flex;flex-wrap:wrap;gap:.5rem 1.5rem;
  padding-top:1rem;margin-bottom:2.5rem;
  border-top:1px solid var(--rule);
  color:var(--ink-soft);font-size:.9rem;
}
/* flex item 默认 min-width:auto，收缩不到内容宽度以下。元表字段值可以很长
   （如 revise 的成句生成声明），min-width:0 让它老实换行而不是撑宽 .doc-meta */
.doc-meta>span{min-width:0}
.doc-meta .k{color:var(--ink-faint);font-weight:500;margin-right:.4rem}

/* §2.3 四层图例 */
.legend{
  margin:1.75rem 0;padding:1rem 1.25rem;
  background:rgba(255,255,255,.4);border:1px dashed var(--rule);
  font-size:.85rem;
}
.legend-title{
  font-family:var(--font-sans);font-size:10px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--ink-faint);margin-bottom:.5rem;
}
.legend ul{margin:0;padding:0;list-style:none;display:flex;flex-wrap:wrap;gap:.5rem 1.5rem}
.legend li{display:flex;align-items:center;color:var(--ink-soft);margin:0}
.legend .sw{width:10px;height:10px;border-radius:2px;margin-right:.45rem;flex:none}
.legend-note{margin-top:.5rem;font-size:.78rem;color:var(--ink-faint)}

/* §2.4 章节标题 */
h2.section{
  font-family:var(--font-sans);font-size:1.05rem;font-weight:700;letter-spacing:.04em;
  margin:2.75rem 0 1.25rem;padding-bottom:.5rem;border-bottom:1px solid var(--rule);
}
h3{font-family:var(--font-sans);font-size:1rem;font-weight:700;margin:1.75rem 0 .5rem;color:var(--l3)}
h4{font-family:var(--font-sans);font-size:.94rem;font-weight:700;margin:1.25rem 0 .4rem;color:var(--ink-soft)}

/* 正文 */
p{margin:.75rem 0}
ul,ol{margin:.75rem 0;padding-left:1.5rem}
li{margin-bottom:.5rem}
li::marker{color:var(--ink-faint)}
blockquote{
  margin:1rem 0;padding:.6rem 1.1rem;
  border-left:3px solid var(--rule);background:rgba(255,255,255,.35);
  color:var(--ink-soft);
}
blockquote p{margin:.3rem 0}
a{color:var(--l1);text-decoration:underline;text-underline-offset:2px}
strong{font-weight:700;color:var(--ink)}
em{font-style:italic}
code{
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.88em;
  background:rgba(255,255,255,.55);border:1px solid var(--rule);
  border-radius:2px;padding:.1em .35em;
}
hr{border:0;border-top:1px solid var(--rule);margin:2rem 0}

/* §5 表格。宽表（如 revise 的 5 列对照表）横向滚动而不撑开 .page；
   max-width 与 overflow 成对出现才有效，且不限窄屏——宽表在任何屏宽都可能超出 */
.table-wrap{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;margin:1rem 0;font-size:.92rem}
th,td{border:1px solid var(--rule);padding:.55rem .75rem;text-align:left;vertical-align:top}
th{background:var(--paper-edge);font-family:var(--font-sans);font-weight:700;font-size:.88rem}

/* §3.1 四层行内标签 */
.tag-inline{
  display:inline-block;font-family:var(--font-sans);font-size:10px;font-weight:700;
  letter-spacing:.04em;padding:1px 6px;border-radius:2px;margin-right:4px;
  border:1px solid currentColor;white-space:nowrap;
}

/* §2.5 页脚 */
footer{
  margin-top:3.5rem;padding-top:1.25rem;border-top:2px double var(--rule);
  color:var(--ink-soft);font-size:.85rem;line-height:1.7;
}
footer .seal{
  font-family:var(--font-sans);font-size:10px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--ink-faint);margin-bottom:.5rem;
}
footer p{margin:.4rem 0}

/* 内嵌 SVG（paper-screen 的 PRISMA 流程图） */
figure{margin:1.5rem 0}
figure svg{display:block;max-width:100%;height:auto;margin:0 auto}
figcaption{
  margin-top:.6rem;font-size:.85rem;color:var(--ink-soft);
  font-family:var(--font-sans);text-align:center;
}

/* 窄屏：纸面收边、标题缩号 */
@media (max-width:720px){
  .page{padding:2rem 1.25rem;margin:1.5rem auto 3rem}
  h1.doc-title{font-size:1.6rem}
  .doc-meta{gap:.35rem 1rem}
}
"""

_PRINT = """
@media print{
  body{background:#fff;padding:0}
  .page{box-shadow:none;margin:0;max-width:none;border:none;border-top:6px solid #000;padding:0}
  .page::before{display:none}
  .page>*{opacity:1!important;transform:none!important;animation:none!important}
  a{text-decoration:none;color:inherit}
  table,figure,blockquote{break-inside:avoid}
  h2.section,h3{break-after:avoid}
}
"""


def _root(tokens: Dict[str, str]) -> str:
    """`:root` 段——色值与字栈的唯一注入点。"""
    lines = [f"  --{k}:{v};" for k, v in sorted(tokens.items())]
    for name, (fg, bg) in READER_COLORS.items():
        lines.append(f"  --{name}:{fg};--{name}-bg:{bg};")
    return ":root{\n" + "\n".join(lines) + "\n}"


def _layer_classes() -> str:
    """四层与读者轴的配色。两套轴共用 `.tag-inline` / `.sw` 骨架、只换色。

    注意色档名与 CSS 变量名不同名：四层的档名是 `t1-t4`（`references/四层内容标注.md`
    的权威命名），而 config 里的色变量是 `l1-l4`。读者轴两者同为 `r1-r4`。
    """
    out = []
    for n in ("1", "2", "3", "4"):
        out.append(f".tag-inline.t{n}{{background:var(--l{n}-bg);color:var(--l{n})}}")
        out.append(f".legend .sw.t{n}{{background:var(--l{n})}}")
    for n in ("1", "2", "3", "4"):
        out.append(f".tag-inline.r{n}{{background:var(--r{n}-bg);color:var(--r{n})}}")
        out.append(f".legend .sw.r{n}{{background:var(--r{n})}}")
    return "\n".join(out)


def _rise() -> str:
    """§2.7 入场动画。nth-child 错峰无法用单条规则表达，按级数展开。"""
    steps = "\n".join(
        f"  .page>*:nth-child({i}){{animation-delay:{.05 + i * .07:.2f}s}}"
        for i in range(1, _RISE_STEPS + 1)
    )
    return (
        "@media (prefers-reduced-motion:no-preference){\n"
        "  .page>*{opacity:0;transform:translateY(8px);animation:rise .6s ease forwards}\n"
        f"{steps}\n"
        f"  .page>*:nth-child(n+{_RISE_STEPS + 1}){{animation-delay:{.05 + (_RISE_STEPS + 1) * .07:.2f}s}}\n"
        "  @keyframes rise{to{opacity:1;transform:none}}\n"
        "}"
    )


def build(tokens: Dict[str, str]) -> str:
    """拼出完整内联 CSS。"""
    return "\n".join([_root(tokens), _STATIC, _layer_classes(), _rise(), _PRINT])
