#!/usr/bin/env python3
"""paper-search 中文轨导出解析 CLI：把知网 / 万方的**官方导出引文文件**解析成与
`search.py` 同形的 results，供宿主并入同一张文献笔记表。输出结构化 JSON 到 stdout、
不写任何文件（产物落盘由宿主按 SKILL.md 完成）。

为什么是「解析导出」而不是「程序化检索」：中文库无免费开放 API，而站内检索接口带
robots.txt 明示禁止（知网海外版为 `Disallow: /`）与反爬水印；由用户在站内检索、用官方
「导出引文」功能取题录，再由本脚本解析，才既拿到最完整的题录（官方格式带卷期页码、
部分带 DOI），又不与站点意愿对抗。检索这一步仍由人执行 —— 文献取舍的研究判断本来
就归用户（paper-search 红线 1）。

覆盖方式因此记「用户回填（官方导出）」，不是「自动检索」：这是红线 2 要求的如实声明，
不许把导出结果说成自动检索的产物。

支持格式：BibTeX（`@article{...}`）与 EndNote/RIS（`TY  - JOUR` … `ER  -`）—— 两者
都是结构化字段、跨库通用，知网与万方均可导出。GB/T 7714 是排版文本而非结构化格式，
不在本脚本范围（要支持须另立解析器并接受字段缺失）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# 标准三行引导头（同 search.py）：parents[2] = skills/，其下 _shared/
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
from paper_shared.datasources.models import normalize_doi   # noqa: E402

# 允许的源 id 与注册表一致（registry.json 的 guided 源）。other 供其他中文库导出兜底，
# 覆盖声明里会如实标为未知来源，不冒充知网 / 万方。
_SOURCE_IDS = ("cnki", "wanfang", "other")

# BibTeX 条目类型 → canonical 文献类型（canonical 集同 clients/base.py 的 TYPE_MAP）
_BIB_TYPE = {"article": "journal-article", "inproceedings": "conference-paper",
             "conference": "conference-paper", "proceedings": "conference-paper",
             "phdthesis": "thesis", "mastersthesis": "thesis", "thesis": "thesis",
             "book": "book", "inbook": "book-chapter", "incollection": "book-chapter",
             "techreport": "report", "misc": None, "unpublished": "preprint"}

# RIS TY → canonical。给不出映射的留 None（宁可为空，也不猜一个类型去污染筛选）
_RIS_TYPE = {"JOUR": "journal-article", "EJOUR": "journal-article",
             "CONF": "conference-paper", "CPAPER": "conference-paper",
             "THES": "thesis", "BOOK": "book", "CHAP": "book-chapter",
             "RPRT": "report", "UNPB": "preprint", "GEN": None}

# RIS 字段 → 内部键。多值字段（作者 / 关键词）单列，见 _RIS_MULTI
_RIS_FIELD = {"TI": "title", "T1": "title", "AU": "author", "A1": "author",
              "PY": "year", "Y1": "year", "DA": "date",
              "JO": "venue", "JF": "venue", "JA": "venue", "T2": "venue",
              "VL": "volume", "IS": "issue", "SP": "start_page", "EP": "end_page",
              "DO": "doi", "UR": "url", "AB": "abstract", "KW": "keyword",
              "SN": "issn", "PB": "publisher"}
_RIS_MULTI = ("author", "keyword")


def strip_invisible(s: str) -> str:
    """删掉 Unicode 格式类（Cf）与控制类（Cc，保留不了任何题录语义的）字符。

    这是**无损**清洗：零宽空格 / 方向标记 / WORD JOINER（U+200B-200F、U+2060-206F、
    U+FEFF 等）在正常题录里不该出现，出现即为站点注入的防爬水印或复制粘贴噪音。实测知网
    页面单条标题里可含 22-27 个此类字符（散布在单词内部）。

    ⚠️ 顺序要紧：必须先删这些字符、再折叠空白。反过来会把 U+FEFF 这类被部分正则引擎的
    `\\s` 覆盖的字符替换成真空格，在单词内部留下不可逆的假词边界（`content` → `c ontent`）。
    """
    out = [ch for ch in s if unicodedata.category(ch) not in ("Cf", "Cc")]
    return re.sub(r"\s+", " ", "".join(out)).strip()


# 站点注入的可见水印词。**只告警、不删**：这些词在真实标题里可能是正文（《数字出版版权
# 保护研究》），静默删除会破坏题名，而题名是题录的主键。判断交用户（红线 1）。
_WATERMARK_WORDS = ("知网", "版权", "CNKI", "万方")


def watermark_warning(entries: List[Dict[str, Any]]) -> Optional[str]:
    """标题里出现疑似水印词时如实提示人工核对，不代为删改。"""
    hits = [e["title"] for e in entries
            if e.get("title") and any(w in e["title"] for w in _WATERMARK_WORDS)]
    if not hits:
        return None
    return (f"{len(hits)} 条题名含疑似站点水印词（{'/'.join(_WATERMARK_WORDS)}）："
            f"已清除不可见字符，但可见词未删——它可能是真实题名的一部分。"
            f"请逐条核对后再入表，首条：{hits[0][:60]}")


def _first_year(v: Optional[str]) -> Optional[int]:
    """从年份字段取 4 位年。RIS 的 PY 可能是 `2023/06//`、BibTeX 可能是 `{2023}`。
    取不出就是 None——不拿当前年、不拿卷号凑（给不出就是 null，同 search.py 的 date）。"""
    if not v:
        return None
    m = re.search(r"(19|20)\d{2}", str(v))
    return int(m.group(0)) if m else None


def _clean_bib_value(v: str) -> str:
    """BibTeX 值清洗：去最外层包裹、拆 LaTeX 转义、清不可见字符。

    只解常见转义（`\\&` `\\_` `\\%` `\\$` `\\#`）与用于保护大小写的花括号；不实现完整
    LaTeX 解析——中文库导出极少含复杂宏，遇到了原样留下比猜错好。"""
    t = v.strip()
    t = re.sub(r"\\([&_%$#])", r"\1", t)
    t = t.replace("{", "").replace("}", "")
    return strip_invisible(t)


def _split_authors(raw: str) -> List[str]:
    """BibTeX 作者串按 ` and ` 拆分。姓名形态（`张三` / `Zhang, San`）**原样保留**——
    姓名重排是引文格式化的职责（paper-format），检索层擅自重排会让中文姓名变成 `三, 张`。"""
    if not raw:
        return []
    parts = re.split(r"\s+\band\b\s+", raw)
    return [p.strip() for p in parts if p.strip()]


def _is_cjk(ch: str) -> bool:
    """CJK 统一汉字（含扩展 A）与中文标点。折行拼接是否补空格全看这个判断。"""
    o = ord(ch)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x3000 <= o <= 0x303F


def _join_continuation(prev: str, cont: str) -> str:
    """RIS 折行续行的拼接：英文必须补空格（否则 `learn` + `ing` 粘成一个词），中文必须
    不补（中文不用空格分词，补了会在题名中间留假空格）。

    这不是洁癖——题名是无 DOI 时的去重主键（search.py `_dedup_key` 的标题回退路径），
    中文题名多一个空格就跟 API 侧的同一篇对不上，会在笔记表里变成两条。"""
    if not prev:
        return cont
    if not cont:
        return prev
    sep = "" if _is_cjk(prev[-1]) and _is_cjk(cont[0]) else " "
    return f"{prev}{sep}{cont}"


def _pages(start: Optional[str], end: Optional[str], pages: Optional[str]) -> Optional[str]:
    if pages:
        return pages
    if start and end:
        return f"{start}-{end}"
    return start or end or None


def parse_bibtex(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """解析 BibTeX。返回 (条目列表, 跳过原因列表)。

    自己数花括号而不用正则一把梭：字段值里的嵌套花括号（`title = {A {BERT} Study}`）
    会让贪婪 / 懒惰正则都切错。跳过的片段全部记进 skipped，不静默丢弃。"""
    entries: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for m in re.finditer(r"@(\w+)\s*\{", text):
        kind = m.group(1).lower()
        i, depth = m.end(), 1
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        if depth:
            skipped.append(f"@{kind} 条目花括号未闭合，已跳过")
            continue
        body = text[m.end():i - 1]
        fields: Dict[str, str] = {}
        # 字段切分同理手工扫描：value 可以是 {..}（可嵌套）、"..." 或裸 token
        j = 0
        while j < len(body):
            fm = re.compile(r"(\w+)\s*=\s*").search(body, j)
            if not fm:
                break
            name, j = fm.group(1).lower(), fm.end()
            if j < len(body) and body[j] == "{":
                d, k = 1, j + 1
                while k < len(body) and d:
                    if body[k] == "{":
                        d += 1
                    elif body[k] == "}":
                        d -= 1
                    k += 1
                fields[name], j = body[j + 1:k - 1], k
            elif j < len(body) and body[j] == '"':
                k = body.find('"', j + 1)
                if k < 0:
                    skipped.append(f"字段 {name} 引号未闭合，已跳过该字段")
                    break
                fields[name], j = body[j + 1:k], k + 1
            else:
                k = j
                while k < len(body) and body[k] not in ",\n":
                    k += 1
                fields[name], j = body[j:k], k
            nxt = body.find(",", j)
            j = (nxt + 1) if nxt >= 0 else len(body)
        if not fields:
            skipped.append(f"@{kind} 条目无可解析字段，已跳过")
            continue
        g = lambda k: _clean_bib_value(fields[k]) if fields.get(k) else None   # noqa: E731
        entries.append({
            "type": _BIB_TYPE.get(kind),
            "title": g("title"),
            "authors": _split_authors(_clean_bib_value(fields.get("author", ""))),
            "year": _first_year(fields.get("year")),
            "venue": g("journal") or g("booktitle") or g("publisher"),
            "doi": normalize_doi(fields["doi"]) if fields.get("doi") else None,
            "url": g("url"),
            "volume": g("volume"), "issue": g("number"),
            "pages": _pages(None, None, g("pages")),
        })
    return entries, skipped


def parse_ris(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """解析 EndNote/RIS。返回 (条目列表, 跳过原因列表)。

    续行处理是必需的：长标题 / 摘要会折行且续行无 tag 前缀，丢掉续行会得到截断的题名。
    缺 `ER  -` 结束标记的末条仍然收下（导出文件被截断时，能救回的条目要救）。"""
    entries: List[Dict[str, Any]] = []
    skipped: List[str] = []
    cur: Dict[str, Any] = {}
    last_key: Optional[str] = None

    def flush():
        nonlocal cur, last_key
        if cur:
            if cur.get("title"):
                entries.append(_ris_to_entry(cur))
            else:
                skipped.append("RIS 条目缺 TI/T1（题名），已跳过——题名是题录主键，不猜")
        cur, last_key = {}, None

    for line in text.splitlines():
        tm = re.match(r"^([A-Z][A-Z0-9])  ?-\s?(.*)$", line)
        if not tm:
            if last_key and line.strip():          # 续行：接到上一字段尾部
                if last_key in _RIS_MULTI:
                    cur[last_key][-1] = _join_continuation(cur[last_key][-1], line.strip())
                else:
                    cur[last_key] = _join_continuation(cur.get(last_key, ""), line.strip())
            continue
        tag, val = tm.group(1), tm.group(2).strip()
        if tag == "TY":
            flush()
            cur["_ty"] = val.upper()
            last_key = None
            continue
        if tag == "ER":
            flush()
            continue
        key = _RIS_FIELD.get(tag)
        if not key:
            last_key = None
            continue
        if key in _RIS_MULTI:
            cur.setdefault(key, []).append(val)
        else:
            cur[key] = val
        last_key = key
    flush()
    return entries, skipped


def _ris_to_entry(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": _RIS_TYPE.get(c.get("_ty", ""), None),
        "title": strip_invisible(c.get("title", "")) or None,
        "authors": [strip_invisible(a) for a in c.get("author", []) if a.strip()],
        "year": _first_year(c.get("year") or c.get("date")),
        "venue": strip_invisible(c["venue"]) if c.get("venue") else None,
        "doi": normalize_doi(c["doi"]) if c.get("doi") else None,
        "url": strip_invisible(c["url"]) if c.get("url") else None,
        "volume": c.get("volume"), "issue": c.get("issue"),
        "pages": _pages(c.get("start_page"), c.get("end_page"), None),
    }


def detect_format(text: str) -> Optional[str]:
    """按内容特征判格式。判不出返回 None —— 报错而不猜，猜错会把整份文件解析成 0 条
    却让人以为「导出里没文献」。"""
    if re.search(r"^\s*TY\s\s?-\s", text, re.M):
        return "ris"
    if re.search(r"@\w+\s*\{", text):
        return "bibtex"
    return None


def to_result(entry: Dict[str, Any], source: str) -> Dict[str, Any]:
    """转成与 `search.py` 的 `dedup_hits` 输出同形的一条 result，好让宿主把导出条目与
    API 检索结果并进同一张表、走同一套去重。

    `date` 恒为 None：导出格式只给到年，日级日期给不出就是 null（同 search.py，不用
    year 凑）。`retraction` 恒为 None：导出文件不含撤稿信息，「没查过」不等于「没被撤稿」，
    撤稿判定归 /paper-verify。"""
    return {
        "title": entry.get("title"), "authors": entry.get("authors") or [],
        "year": entry.get("year"), "date": None,
        "venue": entry.get("venue"), "doi": entry.get("doi"),
        "type": entry.get("type"), "url": entry.get("url"),
        "volume": entry.get("volume"), "issue": entry.get("issue"),
        "pages": entry.get("pages"),
        "sources": [source], "primary_source": source,
        "from_cache": False, "retraction": None,
        "coverage_mode": "user_export",
    }


def build_payload(path: str, fmt: str, source: str, entries: List[Dict[str, Any]],
                  skipped: List[str]) -> Dict[str, Any]:
    """组装输出契约。与 search.py 的输出并列：results 同形、warnings 同样不许吞。"""
    results = [to_result(e, source) for e in entries]
    for i, r in enumerate(results, 1):
        r["rank"] = i
    warns = list(skipped)
    wm = watermark_warning(entries)
    if wm:
        warns.append(wm)
    no_doi = sum(1 for r in results if not r["doi"])
    if no_doi:
        warns.append(f"{no_doi} 条无 DOI（中文文献常见）：这类条目无法用 --lookup-doi 补全，"
                     f"元数据以导出文件为准；不得据此判定文献不存在")
    return {
        "input_file": path,
        "format": fmt,
        "source": source,
        "coverage": [{"source": source, "mode": "user_export",
                      "hit_count": len(results), "format": fmt,
                      "note": "用户在站内检索后用官方「导出引文」功能导出，本脚本仅解析"}],
        "results": results,
        "warnings": warns,
        "stats": {"parsed": len(results), "skipped": len(skipped)},
    }


def _parse_args(argv):
    p = argparse.ArgumentParser(
        description="解析知网 / 万方官方导出的引文文件（BibTeX / EndNote-RIS），"
                    "输出与 search.py 同形的结构化 JSON。")
    p.add_argument("--in", dest="path", required=True, help="导出文件路径")
    p.add_argument("--source", default="other", choices=_SOURCE_IDS,
                   help="导出来源库 id（覆盖声明用；默认 other）")
    p.add_argument("--format", dest="fmt", choices=["bibtex", "ris"],
                   help="强制指定格式；缺省按内容自动判别")
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    try:
        text = pathlib.Path(args.path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        # 知网 / 万方的导出偶有 GBK 编码。解码失败不是「文件没内容」，如实换码重试。
        try:
            text = pathlib.Path(args.path).read_text(encoding="gbk")
        except Exception as e:
            sys.stderr.write(f"读取失败（utf-8 与 gbk 均不可解）：{e}\n")
            return 2
    except OSError as e:
        sys.stderr.write(f"读取失败：{e}\n")
        return 2
    fmt = args.fmt or detect_format(text)
    if not fmt:
        sys.stderr.write("无法判别导出格式：未见 RIS 的 `TY  - ` 行，也未见 BibTeX 的 "
                         "`@type{`。请用 --format 指定，或确认导出时选的是 BibTeX / "
                         "EndNote（GB/T 7714 等排版格式本脚本不支持）\n")
        return 2
    entries, skipped = parse_bibtex(text) if fmt == "bibtex" else parse_ris(text)
    payload = build_payload(args.path, fmt, args.source, entries, skipped)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
