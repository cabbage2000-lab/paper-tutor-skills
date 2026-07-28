#!/usr/bin/env python3
"""paper-verify 引用核验主入口（spec §3 数据流）。

编排：解析输入（文本 / .bib / 单条 DOI|标题）→ fetch_batch 取证（复用 _shared，
带断点续验）→ judge 六态判定 → format_check 格式检查（默认开）→ report 组装
JSON + Markdown、report_html 渲染 HTML 视图（默认开）→ 落盘 → stdout 输出摘要 JSON。
三份产物同源于一份 payload：HTML 给人读（六态筛选 + 证据链折叠 + 可点 DOI）、
Markdown 给纯文本环境与 diff、JSON 给机器（断点续验、manual_result 回填）。

与 paper-search「脚本只吐 stdout」惯例不同：verify 的产物是「报告 artifact」
（含断点续验 progress.json，必须脚本管理），故脚本带 --out-dir 直接落盘——定位同
paper-search 的 render_html.py：把已判定的证据渲染成最终报告，不产生研究内容。
stdout 吐摘要（六态分布 + 三份报告路径），供宿主向用户呈现。

run() 接受 fetch 注入（测试用，默认门面 fetch_batch），便于离线确定性测编排。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
from paper_shared.datasources import fetch_batch  # noqa: E402
from paper_shared.datasources.models import Evidence, Ref  # noqa: E402
from paper_shared.datasources.registry import Registry  # noqa: E402

import format_check  # noqa: E402
import judge  # noqa: E402
import parse_refs  # noqa: E402
import report  # noqa: E402
import report_html  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(refs) -> str:
    h = hashlib.sha256()
    for r in refs:
        h.update((r.raw_text or r.title or "").encode("utf-8"))
        h.update(b"\x00")
    return "sha256:" + h.hexdigest()[:16]


def _load_input(args) -> list:
    if args.doi:
        return [parse_refs.parse_single(args.doi)]
    if args.title:
        return [parse_refs.parse_single(args.title)]
    if args.input:
        text = pathlib.Path(args.input).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        return []
    return parse_refs.parse_text(text)


def _load_manual(path: str) -> dict:
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return {it["ref_id"]: it.get("manual_result")
            for it in data.get("items", []) if it.get("manual_result")}


def _resolve_out_dir(out_dir) -> pathlib.Path:
    if out_dir:
        return pathlib.Path(out_dir)
    if pathlib.Path(".paper").exists():
        return pathlib.Path(".paper/review")
    return pathlib.Path(".")


def _sources_checked() -> list:
    """从注册表组装报告「已查源清单」（数据源 spec §7：清单是产品输出的一部分）。"""
    reg = Registry.load()
    out = []
    for s in reg.api_sources():
        if s.role == "core":
            out.append({"source": s.id, "name_zh": s.name_zh, "role": s.role, "coverage": "自动核验"})
    for s in reg.guided_sources():
        out.append({"source": s.id, "name_zh": s.name_zh, "role": "guided", "coverage": "待人工核对"})
    return out


def _parse_args(argv):
    p = argparse.ArgumentParser(
        description="paper-verify 引用核验：真实 API 取证 + 六态判定 + HTML/Markdown/JSON 报告。")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--input", help="参考文献文件路径（.bib / .md / .txt）")
    g.add_argument("--text", help="直接粘贴的参考文献文本")
    g.add_argument("--doi", help="单条 DOI 核验")
    g.add_argument("--title", help="单条标题核验")
    p.add_argument("--out-dir", help="报告输出目录（默认 .paper/review/，无则当前目录）")
    p.add_argument("--apply-manual", help="读旧报告 JSON 的 manual_result 回填（重跑升级 PENDING）")
    p.add_argument("--no-format", action="store_true", help="跳过 GB/T 7714 格式检查")
    p.add_argument("--no-cache", action="store_true", help="强制刷新缓存（投稿前终检）")
    p.add_argument("--no-html", action="store_true",
                   help="跳过 HTML 视图（默认生成，是给人读的主产物）")
    return p.parse_args(argv)


def run(args, fetch=None) -> int:
    """编排主流程。fetch 可注入（测试用），默认门面 fetch_batch。返回退出码。"""
    refs = _load_input(args)
    if not refs:
        sys.stderr.write("未解析出任何引用——请检查输入，或改用 --doi / --title 单条核验\n")
        return 2
    fetcher = fetch or fetch_batch
    manual_map = _load_manual(args.apply_manual) if args.apply_manual else {}
    out_dir = _resolve_out_dir(args.out_dir)
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    run_id = f"verify-{ts}"
    state_path = out_dir / f"{run_id}.progress.json"
    json_path = out_dir / f"{run_id}.json"
    md_path = out_dir / f"{run_id}.md"
    html_path = out_dir / f"{run_id}.html"

    shared_refs = [Ref(**r.to_ref_dict()) for r in refs]

    out_dir.mkdir(parents=True, exist_ok=True)   # state_path 落此目录、续验期间会写，须先建

    def progress(msg):
        sys.stderr.write(msg + "\n")

    t0 = time.time()
    batch = fetcher(shared_refs, state_path=state_path, progress=progress, fresh=args.no_cache)
    elapsed = time.time() - t0

    items = []
    by_status = {}
    for r in refs:
        ev = batch.evidences.get(r.id) or Evidence(ref_id=r.id, input=Ref(id=r.id))
        rec = judge.judge(r, ev, manual_result=manual_map.get(r.id))
        fi = [] if args.no_format else format_check.check_format(r.id, r.raw_text or "", parsed=r)
        items.append({
            "ref_id": r.id, "raw_text": r.raw_text, "parsed": r.to_dict(),
            "status": rec.status,
            "field_notes": [n.to_dict() for n in rec.field_notes],
            "evidence_summary": rec.evidence_summary,
            "exit_guidance": rec.exit_guidance,
            "evidence": ev.to_dict(),
            "format_issues": [i.to_dict() for i in fi],
            "manual_result": manual_map.get(r.id),
        })
        by_status[rec.status] = by_status.get(rec.status, 0) + 1

    sources_queried = sorted({q.get("source") for it in items
                              for q in (it["evidence"].get("queries") or []) if q.get("source")})
    stats = {"total": len(refs), "by_status": by_status,
             "elapsed_s": round(elapsed, 1), "sources_queried": sources_queried}
    payload = report.build_json_payload(
        {"run_id": run_id, "created_at": _now_iso(), "fingerprint": _fingerprint(refs),
         "network_status": batch.network_status, "sources_checked": _sources_checked()},
        items, stats)

    out_dir.mkdir(parents=True, exist_ok=True)
    report.write_outputs(payload, json_path, md_path)
    if not args.no_html:
        report_html.write_html(payload, html_path)
    try:
        state_path.unlink()      # 断点续验状态文件完成后清理
    except OSError:
        pass

    summary = {"run_id": run_id, "network_status": batch.network_status,
               "total": len(refs), "by_status": by_status,
               "report_md": str(md_path), "report_json": str(json_path)}
    if not args.no_html:
        summary["report_html"] = str(html_path)   # 人读主产物，宿主优先指向它
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def main(argv=None) -> int:
    return run(_parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
