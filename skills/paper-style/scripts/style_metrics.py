#!/usr/bin/env python3
"""paper-style 风格特征内核——markdown 预处理 / 切句 / 五类特征 / 章节间偏移。

设计要点：风格特征一律**算出来**，不是感觉出来的。LLM 只解读本脚本输出的数字，
不得给「读起来像 / 不像 AI」这类无依据判断。两项近似值（术语密度、四字格）在
输出里带 `approximate: true` 与中文声明，**不得被当成精确值使用**——不引 jieba
是既定技术栈约束（`_shared/README.md`），近似就如实说近似。

markdown 预处理、切句、切章与引用识别在 `_shared/paper_shared/citations.py`——
`paper-anchor` 是第二个消费者，两处各存一份正则必然漂移（硬规则 1）。本文件只留
风格特征专属的词表与计算。

纯标准库（零第三方运行时依赖，最低 Python 3.9）。
"""
from __future__ import annotations

import pathlib
import re
import statistics
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# 标准三行引导头（同 paper-doctor/scripts/doctor.py）：parents[2] = skills/，其下 _shared/
_SKILLS = pathlib.Path(__file__).resolve().parents[2]
if str(_SKILLS / "_shared") not in sys.path:
    sys.path.insert(0, str(_SKILLS / "_shared"))
from paper_shared.citations import (  # noqa: E402
    citation_positions, effective_chars, split_sections, split_sentences,
    strip_markdown,
)

# ── 词表（权威在此，references 不复制副本：两份必然漂移）────────────────────
# 选词依据：中文学术写作常见连接与限定成分，取自写作惯例；**不取自任何 AIGC
# 检测器的特征工程**——本命令不服务规避检测（见 references/误判申诉口径.md）。
_FUNCTION_WORDS: Tuple[str, ...] = (
    "值得注意的是", "需要指出的是", "综上所述", "由此可见", "换言之", "也就是说",
    "一方面", "另一方面", "除此之外", "与此同时", "在此基础上", "总的来说",
    "然而", "因此", "此外", "首先", "其次", "再者", "最后", "总之", "同时",
    "另外", "但是", "尽管", "虽然", "即使", "因为", "所以", "于是", "从而",
    "进而", "鉴于", "基于", "其中", "并且", "而且", "不仅", "以及", "且",
    "However", "Therefore", "Moreover", "Furthermore", "In addition",
    "Nevertheless", "Consequently", "Accordingly", "Specifically",
    "In particular", "On the other hand", "In conclusion", "Thus", "Hence",
)

# 常见学术四字格。**固定词表、非全量识别**——无分词做不到全量，故此项为近似值。
_QUAD_PHRASES: Tuple[str, ...] = (
    "至关重要", "不可忽视", "值得关注", "日益增长", "广泛应用", "深入研究",
    "显著提升", "显著提高", "有效促进", "充分发挥", "全面分析", "系统梳理",
    "详细阐述", "深刻影响", "重要意义", "关键作用", "核心要素", "内在逻辑",
    "客观规律", "长期以来", "与日俱增", "错综复杂", "行之有效", "势在必行",
)

_PERSON_WORDS: Tuple[str, ...] = (
    "本研究", "本课题", "本文", "笔者", "我们", "该研究", "作者认为", "本人",
)
# 先屏蔽再计数：不屏蔽「本文献」会让「本文」多计一次（长词优先的边界情形）。
_PERSON_MASK: Tuple[str, ...] = ("本文献", "本文件", "本文档")

# 术语密度近似路径的通用词黑名单——这些词高频但不是术语，不屏蔽会把密度顶高。
_COMMON_NOISE: Tuple[str, ...] = (
    "研究", "方法", "问题", "分析", "结果", "数据", "影响", "作用", "发展",
    "提高", "进行", "通过", "以及", "可以", "能够", "这些", "其中", "不同",
    "相关", "重要", "情况", "内容", "方面", "过程", "基础", "工作", "存在",
)

# 近似术语候选的首 / 尾字剪除表：不剪的话「神经网络的」会因为出现 3 次、且比
# 「神经网络」更长而胜出（长串优先），把结构助词粘进术语。两表分开是必要的——
# 「中」作尾字（研究中）是噪声、作首字（中位数）是术语；「一」两侧都不剪，
# 否则「一致性」这类真术语会被误杀。
_TRIM_HEAD = set("的了着地得和与及或把被对从向为以在是也就都而其此该那之等个们")
_TRIM_TAIL = set("的了着地得和与及或把被对从向为以在是也就都而其此该这那之等中上下时后前里")

_MIN_SENTENCES_FOR_STD = 5  # 少于这么多句，标准差不具解释力 → reliable=False


# ── 五类特征 ───────────────────────────────────────────────────────────────
def count_words(text: str, words: Sequence[str],
                mask: Sequence[str] = ()) -> Dict[str, int]:
    """长词优先计数：先数长词并把命中区间置为占位，再数短词。

    不这么做，「值得注意的是」会同时被自己和「注意」各计一次，虚词密度虚高。
    `mask` 里的词只屏蔽、不计入结果（如「本文献」屏蔽掉，防「本文」误命中）。
    """
    work = text
    for m in sorted(mask, key=len, reverse=True):
        work = work.replace(m, "\x00" * len(m))
    counts: Dict[str, int] = {}
    for w in sorted(words, key=len, reverse=True):
        c = work.count(w)
        if c:
            counts[w] = c
            work = work.replace(w, "\x00" * len(w))
    return counts


def approximate_terms(text: str, terms: Optional[Sequence[str]] = None
                      ) -> Tuple[Dict[str, int], str]:
    """术语计数。返回 (计数字典, 来源说明)。

    用户给术语表 → 精确计数。没给 → 退到「文中重复出现 ≥3 次的 2–6 字汉字串」
    近似，**这是不引 jieba 的直接后果，必须如实标注为近似值**（CLAUDE.md 唯一
    保留的代码层约束：降级必须明确标注，不静默）。近似路径会把「研究」这类
    常用词误当术语，故先过 `_COMMON_NOISE` 黑名单减噪，但**减不干净**。
    """
    if terms:
        return count_words(text, terms), "用户术语表"
    freq: Dict[str, int] = {}
    for run in re.findall(r"[一-鿿]{2,}", text):
        for length in range(2, 7):
            for k in range(len(run) - length + 1):
                sub = run[k:k + length]
                freq[sub] = freq.get(sub, 0) + 1
    blocked = set(_COMMON_NOISE) | set(_FUNCTION_WORDS) | set(_PERSON_WORDS)
    cands = [
        (w, c) for w, c in freq.items()
        if c >= 3 and w not in blocked
        and w[0] not in _TRIM_HEAD and w[-1] not in _TRIM_TAIL
        and not any(b in w for b in _PERSON_WORDS)
    ]
    # 长串优先：短串若只是某个已选长串的一部分（计数也不更高），是同一个术语的碎片
    cands.sort(key=lambda kv: (-len(kv[0]), -kv[1]))
    picked: Dict[str, int] = {}
    for w, c in cands:
        if any(w in p and c <= pc for p, pc in picked.items()):
            continue
        picked[w] = c
        if len(picked) >= 20:
            break
    return picked, "重复串近似"


@dataclass
class SectionMetrics:
    """一个章节的风格特征向量。`reliable=False` 时标准差不具解释力。"""
    name: str
    char_count: int = 0
    sentence_count: int = 0
    len_mean: float = 0.0
    len_median: float = 0.0
    len_std: float = 0.0
    function_word_per_100: float = 0.0
    function_word_top: List[Tuple[str, int]] = field(default_factory=list)
    citation_pos: Dict[str, int] = field(default_factory=dict)
    citation_end_ratio: float = 0.0
    person_counts: Dict[str, int] = field(default_factory=dict)
    person_per_1000: float = 0.0
    quad_per_1000: float = 0.0
    quad_top: List[Tuple[str, int]] = field(default_factory=list)
    term_density_per_100: float = 0.0
    term_top: List[Tuple[str, int]] = field(default_factory=list)
    term_source: str = ""
    reliable: bool = False

    def to_dict(self) -> Dict:
        d = dict(self.__dict__)
        d["function_word_top"] = [list(x) for x in self.function_word_top]
        d["quad_top"] = [list(x) for x in self.quad_top]
        d["term_top"] = [list(x) for x in self.term_top]
        d["approximate"] = {"term_density_per_100": True, "quad_per_1000": True}
        return d


def measure_section(name: str, text: str,
                    terms: Optional[Sequence[str]] = None) -> SectionMetrics:
    """算一个章节的全部特征。`text` 须是已 `strip_markdown` 的纯正文。"""
    m = SectionMetrics(name=name)
    sents = split_sentences(text)
    m.sentence_count = len(sents)
    m.char_count = effective_chars(text)
    if not sents:
        return m
    lens = [effective_chars(s) for s in sents]
    lens = [x for x in lens if x] or [0]
    m.len_mean = round(statistics.fmean(lens), 2)
    m.len_median = round(statistics.median(lens), 2)
    # 总体标准差：样本标准差在 5–10 句时虚高，而这里要的是"这一章内部的离散度"
    m.len_std = round(statistics.pstdev(lens), 2) if len(lens) > 1 else 0.0
    m.reliable = m.sentence_count >= _MIN_SENTENCES_FOR_STD

    fw = count_words(text, _FUNCTION_WORDS)
    fw_total = sum(fw.values())
    m.function_word_per_100 = _per(fw_total, m.char_count, 100)
    m.function_word_top = sorted(fw.items(), key=lambda kv: -kv[1])[:5]

    m.citation_pos = citation_positions(sents)
    cite_total = sum(m.citation_pos.values())
    m.citation_end_ratio = (
        round(m.citation_pos["句末"] / cite_total, 4) if cite_total else 0.0
    )

    pc = count_words(text, _PERSON_WORDS, mask=_PERSON_MASK)
    m.person_counts = pc
    m.person_per_1000 = _per(sum(pc.values()), m.char_count, 1000)

    qc = count_words(text, _QUAD_PHRASES)
    m.quad_per_1000 = _per(sum(qc.values()), m.char_count, 1000)
    m.quad_top = sorted(qc.items(), key=lambda kv: -kv[1])[:5]

    tc, src = approximate_terms(text, terms)
    m.term_source = src
    m.term_density_per_100 = _per(sum(tc.values()), m.char_count, 100)
    m.term_top = sorted(tc.items(), key=lambda kv: -kv[1])[:8]
    return m


def _per(count: int, chars: int, base: int) -> float:
    return round(count / chars * base, 2) if chars else 0.0


# ── 章节间偏移 ─────────────────────────────────────────────────────────────
_COMPARE_FEATURES = (
    ("len_mean", "句长均值"),
    ("len_median", "句长中位数"),
    ("len_std", "句长标准差"),
    ("function_word_per_100", "虚词密度（每百字）"),
    ("citation_end_ratio", "引用置句末占比"),
    ("person_per_1000", "人称密度（每千字）"),
    ("quad_per_1000", "四字格密度（每千字·近似）"),
    ("term_density_per_100", "术语密度（每百字·近似）"),
)


def compare_sections(ms: Sequence[SectionMetrics]) -> Dict:
    """算章节间偏移：每个特征的 min / max / 极差 / 标准差 / 变异系数（CV）。

    为什么要 CV：句长（几十字）与虚词密度（每百字几次）量纲不同，直接比极差
    会把「句长差 8 字」说成比「虚词密度差 3 次」更重要。CV = 标准差 / 均值，
    无量纲，是「哪个特征在章节间抖得最厉害」的唯一可辩护排序依据。

    **脚本只排序、不下结论**——「所以第 3 章要改」是用户的研究判断，不是本
    脚本的输出（三条不变①）。
    """
    if len(ms) < 2:
        return {"available": False,
                "note": "只有一个章节，无章节间偏移可算——需 ≥2 个章节"}
    per: Dict[str, Dict] = {}
    for key, label in _COMPARE_FEATURES:
        vals = [getattr(m, key) for m in ms]
        mean = statistics.fmean(vals)
        std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        lo, hi = min(vals), max(vals)
        per[key] = {
            "label": label,
            "min": round(lo, 4), "max": round(hi, 4),
            "range": round(hi - lo, 4),
            "mean": round(mean, 4), "std": round(std, 4),
            "cv": round(std / mean, 4) if mean else 0.0,
            "min_section": ms[vals.index(lo)].name,
            "max_section": ms[vals.index(hi)].name,
        }
    ranked = sorted(per.items(), key=lambda kv: -kv[1]["cv"])
    return {
        "available": True,
        "per_feature": per,
        "ranked_by_cv": [{"key": k, **v} for k, v in ranked],
    }


APPROXIMATE_NOTES = {
    "term_density_per_100":
        "术语密度为近似值：技术栈约定零第三方依赖（不引 jieba 分词），"
        "无用户术语表时退到「文中重复出现 ≥3 次的 2–6 字汉字串」估算，"
        "会把部分常用词误当术语。产物引用此项须标注「近似」。",
    "quad_per_1000":
        "四字格密度为近似值：基于固定词表命中计数，非全量四字格识别。"
        "产物引用此项须标注「近似」。",
}


# ── CLI ────────────────────────────────────────────────────────────────────
def _render_text(payload: Dict) -> str:
    """人类可读输出。宿主 agent 转录数字时用 --json 更稳，这里供人工核对。"""
    out = [f"模式：{payload['mode']}",
           f"输入：{'、'.join(payload['inputs'])}",
           f"合计：{payload['total']['char_count']} 有效字符 / "
           f"{payload['total']['sentence_count']} 句", ""]
    for s in payload["sections"]:
        flag = "" if s["reliable"] else "  ⚠️ 句子数 < 5，标准差不具解释力"
        out.append(f"【{s['name']}】{s['char_count']} 字 / "
                   f"{s['sentence_count']} 句{flag}")
        out.append(f"  句长 均值 {s['len_mean']} / 中位 {s['len_median']} / "
                   f"标准差 {s['len_std']}")
        out.append(f"  虚词 每百字 {s['function_word_per_100']}"
                   f"（前 5：{s['function_word_top']}）")
        out.append(f"  引用位置 {s['citation_pos']}")
        out.append(f"  人称 每千字 {s['person_per_1000']}（{s['person_counts']}）")
        out.append(f"  四字格 每千字 {s['quad_per_1000']}（近似）")
        out.append(f"  术语 每百字 {s['term_density_per_100']}"
                   f"（近似·来源：{s['term_source']}）")
    cmp_ = payload["comparison"]
    if cmp_.get("available"):
        out.append("\n章节间偏移（按变异系数 CV 降序，只排序不下结论）：")
        for r in cmp_["ranked_by_cv"]:
            out.append(f"  · {r['label']}：CV {r['cv']}，"
                       f"{r['min_section']} {r['min']} → {r['max_section']} {r['max']}")
    else:
        out.append("\n" + cmp_["note"])
    out.append("\n近似值声明：")
    for v in payload["approximate_notes"].values():
        out.append(f"  · {v}")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI。退出码：0 算出结果 / 2 样本不足（切不出句子）/ 3 读不到输入。

    只有三个码是有意的：本命令没有 `paper-screen` 那样的守恒等式，不存在
    「算得出但不可信」的中间态，样本不足是唯一必须拒绝出数的情形。不凑第四个。
    """
    import argparse
    import json
    import pathlib

    ap = argparse.ArgumentParser(description="风格特征计算与章节间偏移")
    ap.add_argument("--input", action="append", default=[],
                    help="正文 markdown 路径（可重复）")
    ap.add_argument("--dir", help="目录，扫其中 *.md（按文件名排序）")
    ap.add_argument("--terms", help="术语表文件，一行一术语（给了则术语密度为精确值）")
    ap.add_argument("--json", dest="json_out", help="JSON 输出路径（省略则打印文本）")
    ap.add_argument("--baseline", action="store_true",
                    help="模式 b：合并全部输入算一份全局基线，不做章节比对")
    args = ap.parse_args(argv)

    paths: List[pathlib.Path] = [pathlib.Path(p) for p in args.input]
    if args.dir:
        d = pathlib.Path(args.dir)
        if not d.is_dir():
            print(f"读不到目录：{args.dir}")
            print("请确认路径正确；manuscript/ 尚无正文则先用 /paper-draft 起草。")
            return 3
        paths.extend(sorted(d.glob("*.md")))
    if not paths:
        print("未指定输入：用 --input <文件> 或 --dir <目录>。")
        return 3

    raw: List[Tuple[str, str]] = []
    for p in paths:
        try:
            raw.append((p.name, p.read_text(encoding="utf-8")))
        except OSError as e:
            # 读不到是环境 / 输入问题，与「样本不足」区分：后者路径没错、只是字太少
            print(f"读不到输入文件：{p}")
            print(f"  原因：{e.strerror or e}")
            return 3

    terms: Optional[List[str]] = None
    if args.terms:
        try:
            terms = [ln.strip() for ln in
                     pathlib.Path(args.terms).read_text(encoding="utf-8").splitlines()
                     if ln.strip()]
        except OSError as e:
            print(f"读不到术语表：{args.terms}")
            print(f"  原因：{e.strerror or e}")
            return 3

    multi = len(raw) > 1
    sections: List[SectionMetrics] = []
    if args.baseline:
        merged = "\n\n".join(strip_markdown(t) for _n, t in raw)
        sections.append(measure_section("全局基线", merged, terms))
    else:
        for fname, text in raw:
            for name, body in split_sections(text):
                clean = strip_markdown(body)
                if not clean.strip():
                    continue
                label = f"{fname} · {name}" if multi else name
                sections.append(measure_section(label, clean, terms))

    total_sents = sum(s.sentence_count for s in sections)
    if total_sents == 0:
        print("样本不足：剥离表格 / 代码 / 引用块后切不出任何句子，不产特征。")
        print(f"  输入：{'、'.join(p.name for p in paths)}")
        print("这不是错误——是可分析的正文太少。请补正文，或换一个包含正文的范围。")
        return 2

    payload = {
        "mode": "baseline" if args.baseline else "compare",
        "inputs": [p.name for p in paths],
        "total": {
            "char_count": sum(s.char_count for s in sections),
            "sentence_count": total_sents,
            "section_count": len(sections),
        },
        "approximate_notes": APPROXIMATE_NOTES,
        "sections": [s.to_dict() for s in sections],
        "comparison": ({"available": False, "note": "模式 b 只算全局基线，不做章节比对"}
                       if args.baseline else compare_sections(sections)),
    }
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(_render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
