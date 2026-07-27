#!/usr/bin/env python3
"""外部工具链探测（pandoc / xelatex / 中文字体）——共享层资源。

**两个消费者**（这是它进 `_shared/` 的依据，见 `_shared/README.md` 准入规则
「至少两个 skill 使用」）：

  - `paper-typeset`：转换前探测，决定哪些目标格式可产、哪些走降级；
  - `paper-doctor`：体检项，把富信息转成 `{check,status,detail,fix}` 契约。

两边各写一份探测必然漂移——doctor 说 pandoc 可用、typeset 说不可用，用户
无从判断哪个对。故探测逻辑只有这一处实现。

pandoc / xelatex 是**外部二进制**（`subprocess` 调用），不是 Python 包依赖，
不违反本目录「零第三方运行时依赖」的技术栈约束。

纯标准库，最低 Python 3.9。
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

_TIMEOUT = 10

# 安装指引按平台 × 二进制。缺工具时必须给得出「装什么」——只说「未检测到」
# 等于把问题丢回用户（三条不变②要求降级报告含安装指引）。
INSTALL_HINTS: Dict[str, Dict[str, str]] = {
    "darwin": {
        "pandoc": "brew install pandoc",
        "xelatex": "brew install --cask mactex-no-gui"
                   "（约 4 GB；只要 xelatex 可换 basictex + tlmgr install xetex xecjk）",
    },
    "win32": {
        "pandoc": "winget install --id JohnMacFarlane.Pandoc"
                  "（或 choco install pandoc）",
        "xelatex": "winget install --id MiKTeX.MiKTeX（或安装 TeX Live）",
    },
    "linux": {
        "pandoc": "apt install pandoc（或 dnf install pandoc）",
        "xelatex": "apt install texlive-xetex texlive-lang-chinese"
                   "（或 dnf install texlive-xetex texlive-xecjk）",
    },
}

# 学术论文正文的中文字体优先序：宋体系（学术出版惯例的正文字体）→ 黑体系 →
# 其余。**排序不是审美问题**：`fonts[0]` 会被 typeset 当默认 `CJKmainfont`，
# 而 fc-list 的原始顺序是任意的——本机实测首位是 `Heiti TC`（繁体黑体），
# 拿它渲染简体论文能显示，但字形是繁体字形、且违学术正文惯例。
_PREFERRED_FAMILIES = (
    "Songti SC", "STSong", "Source Han Serif SC", "Noto Serif CJK SC",
    "SimSun", "Songti TC",
    "PingFang SC", "Source Han Sans SC", "Noto Sans CJK SC",
    "Hiragino Sans GB", "Microsoft YaHei", "Heiti SC", "SimHei",
)


def _rank_families(families: List[str]) -> List[str]:
    """按学术正文适用性排序；不在优先表里的保持原相对顺序、排在后面。"""
    def key(f: str):
        try:
            return (0, _PREFERRED_FAMILIES.index(f))
        except ValueError:
            return (1, families.index(f))
    return sorted(families, key=key)


# 中文字体：文件路径 → **字体族名**。族名才是 XeLaTeX 的 CJKmainfont 能接的值，
# 把 `PingFang.ttc` 这种文件名传进去是无效的——这是本模块最容易写错的一处。
_FONT_FILE_FAMILIES: Dict[str, str] = {
    # macOS
    "/System/Library/Fonts/PingFang.ttc": "PingFang SC",
    "/System/Library/Fonts/Hiragino Sans GB.ttc": "Hiragino Sans GB",
    "/System/Library/Fonts/Supplemental/Songti.ttc": "Songti SC",
    "/Library/Fonts/Songti.ttc": "Songti SC",
    "/System/Library/Fonts/STHeiti Light.ttc": "Heiti SC",
    # Windows
    "C:/Windows/Fonts/simsun.ttc": "SimSun",
    "C:/Windows/Fonts/msyh.ttc": "Microsoft YaHei",
    "C:/Windows/Fonts/simhei.ttf": "SimHei",
    # Linux（发行版路径差异大，fc-list 路径才是主力，这里只兜底常见位置）
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc": "Noto Serif CJK SC",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc": "Noto Sans CJK SC",
}


def _platform_key() -> str:
    if sys.platform.startswith("darwin"):
        return "darwin"
    if sys.platform.startswith("win"):
        return "win32"
    return "linux"


def _hint(binary: str) -> str:
    return INSTALL_HINTS.get(_platform_key(), {}).get(binary, "参见官方文档安装")


def probe_binary(name: str, version_flag: str = "--version",
                 timeout: int = _TIMEOUT) -> Dict:
    """探测一个外部二进制。返回 {name, available, version, path, fix}。

    先用 `shutil.which` 判存在再执行：不判的话未安装会抛 `FileNotFoundError`，
    靠捕获异常来判断既慢又会把「装了但坏了」和「没装」混成一类。

    `errors="replace"` 不能省——xelatex 在中文 Windows 上的输出未必是 UTF-8，
    不加会抛 `UnicodeDecodeError`，把一次探测变成一次崩溃。
    """
    path = shutil.which(name)
    if not path:
        return {"name": name, "available": False, "version": None, "path": None,
                "fix": f"未检测到 {name}；安装：{_hint(name)}"}
    try:
        proc = subprocess.run([path, version_flag], capture_output=True,
                              text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        # 装了但跑不起来（权限 / 依赖库缺失 / 超时）——与「没装」区分开报出，
        # 否则用户会去重装一个其实已经装好的东西。
        return {"name": name, "available": False, "version": None, "path": path,
                "fix": f"{name} 在 {path} 但无法执行（{type(e).__name__}）；"
                       f"确认权限与依赖，或重装：{_hint(name)}"}
    if proc.returncode != 0:
        return {"name": name, "available": False, "version": None, "path": path,
                "fix": f"{name} {version_flag} 返回 {proc.returncode}；"
                       f"疑似安装损坏，重装：{_hint(name)}"}
    first = (proc.stdout or proc.stderr or "").strip().splitlines()
    return {"name": name, "available": True,
            "version": first[0].strip() if first else "（版本未知）",
            "path": path, "fix": None}


def probe_pandoc() -> Dict:
    return probe_binary("pandoc")


def probe_xelatex() -> Dict:
    return probe_binary("xelatex")


def _fonts_via_fc_list(timeout: int = _TIMEOUT) -> Optional[List[str]]:
    """用 fc-list 取中文字体族名。无 fc-list 返回 None（与「有但一个都没找到」区分）。"""
    exe = shutil.which("fc-list")
    if not exe:
        return None
    try:
        proc = subprocess.run([exe, ":lang=zh", "family"], capture_output=True,
                              text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    families: List[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # fc-list 的 family 字段用逗号分隔多别名（"Songti SC,宋体-简"），取第一个
        first = line.split(",")[0].strip()
        # 以 `.` 开头的是系统内部字体（macOS 的 .PingFang SC、.LastResort 等），
        # **XeLaTeX 拿不到**——把它们留在列表里，首选就可能落到一个用不了的名字上，
        # 或更糟：落到 .LastResort（专门显示方框的兜底字体）。
        if first.startswith(".") or not first:
            continue
        if first not in families:
            families.append(first)
    return _rank_families(families)


def probe_cjk_fonts() -> Dict:
    """探测可用中文字体族名。返回 {available, fonts, source, fix}。

    `fonts` 是**族名**列表，可直接作 XeLaTeX 的 `CJKmainfont` 值。
    缺中文字体时中文 PDF 会整篇缺字或编译失败，必须显式报出——不能默默产出
    一份全是方框的 PDF（那就是「假装成功」）。
    """
    families = _fonts_via_fc_list()
    if families:
        return {"available": True, "fonts": families[:20],
                "source": "fc-list :lang=zh", "fix": None}
    found: List[str] = []
    for p, family in _FONT_FILE_FAMILIES.items():
        if pathlib.Path(p).exists() and family not in found:
            found.append(family)
    if found:
        return {"available": True, "fonts": _rank_families(found),
                "source": "已知字体文件路径", "fix": None}
    plat = _platform_key()
    fix = {
        "darwin": "系统应自带 PingFang / Songti；若确实缺失，装 Noto CJK："
                  "brew install --cask font-noto-serif-cjk-sc",
        "win32": "系统应自带 SimSun / Microsoft YaHei；缺失则从「设置 → 字体」补装",
        "linux": "apt install fonts-noto-cjk（或 dnf install google-noto-serif-cjk-fonts）",
    }[plat]
    return {"available": False, "fonts": [],
            "source": "fc-list 与已知路径均未命中", "fix": fix}


def probe_all() -> Dict:
    """一次探完三项。typeset 转换前调它，doctor 体检调它。"""
    return {"pandoc": probe_pandoc(),
            "xelatex": probe_xelatex(),
            "cjk_fonts": probe_cjk_fonts()}


if __name__ == "__main__":
    import json
    json.dump(probe_all(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
