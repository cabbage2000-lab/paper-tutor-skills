#!/usr/bin/env python3
"""paper-doctor 环境就绪度体检脚本。

输出结构化 JSON 到 stdout（契约见 paper-doctor spec §5）。SKILL.md 层转中文报告。
标准库零依赖，Python 3.9+。
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict, List


def check_python_version() -> Dict[str, Any]:
    vi = sys.version_info
    detail = ".".join(str(x) for x in (vi[0], vi[1], vi[2]))
    if (vi[0], vi[1]) >= (3, 9):
        return {"check": "python_version", "status": "ok", "detail": detail, "fix": None}
    return {"check": "python_version", "status": "fail",
            "detail": f"{detail}（需 3.9+）", "fix": None}


def check_sqlite3() -> Dict[str, Any]:
    try:
        import sqlite3  # noqa: F401
        return {"check": "sqlite3", "status": "ok", "detail": "可用", "fix": None}
    except ImportError:
        # 极罕见（某些精简发行版剥离了 sqlite3）；用户须自行装回
        return {"check": "sqlite3", "status": "fail", "detail": "缺失", "fix": None}


def check_shared_import() -> Dict[str, Any]:
    """捕获 import 失败，不崩——blocked 态能落地的前提。"""
    shared_path = str(pathlib.Path(__file__).resolve().parents[2] / "_shared")
    if shared_path not in sys.path:
        sys.path.insert(0, shared_path)
    try:
        import paper_shared.datasources  # noqa: F401
        return {"check": "shared_import", "status": "ok",
                "detail": "paper_shared.datasources 可导入", "fix": None}
    except Exception as e:
        return {"check": "shared_import", "status": "fail",
                "detail": f"{type(e).__name__}: {e}",
                "fix": "确认从 skill 目录运行（python3 skills/paper-doctor/scripts/doctor.py），或检查 _shared/ 路径"}


def run_probe_fresh(transport=None, cache=None):
    """跑数据源健康探测，fresh=True（不吃 TTL 缓存，拿实时可达性）。

    返回 (datasources_list, datasources_overall)。
    _shared 不可导入时返回 ([], None)。

    实现要点：build_clients 有一等 fresh 参数（数据源模块重构后），直接传
    fresh=True 让探测样本请求绕过 TTL 缓存读；判定复用 ProbeEngine.overall()
    静态方法（overall 内部按 CORE_IDS 算，doctor 不重复）。探测遍历与
    ProbeEngine.run() 同源：api_sources 逐源、无 client 的源记 unavailable
    （如 doi_ra 路由设施——注册表里是 core 但无标准 client、不在 CORE_IDS 内，
    不影响 overall）。doctor 默认含补充源以在报告呈现其状态。
    """
    try:
        from paper_shared.datasources.cache import Cache
        from paper_shared.datasources.clients import build_clients
        from paper_shared.datasources.models import ProbeResult
        from paper_shared.datasources.probe import ProbeEngine
        from paper_shared.datasources.registry import Registry
        from paper_shared.datasources.transport import Transport
    except Exception:
        return [], None

    transport = transport or Transport(user_agent="Paper-doctor/0")
    registry = Registry.load()

    # cache=None（默认 CLI 路径 main()→run_all()→run_probe_fresh）时用临时目录的
    # Cache，探测完在 finally 清理——红线 1「全程零文件系统改动」：默认体检绝不在
    # 用户 cache 目录建库留痕（Cache() 构造会 mkdir + CREATE TABLE，且 fresh=True
    # 的 _cached_json 仍 cache.put 写探测响应）。测试传入显式 cache 时走原路径，
    # 不清理（那是测试自己的临时目录）。
    if cache is None:
        import shutil
        import tempfile
        _probe_tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="_paper_doctor_probe_"))
        cache = Cache(_probe_tmpdir / "probe.db")
        _cleanup = lambda: shutil.rmtree(_probe_tmpdir, ignore_errors=True)
    else:
        _cleanup = None

    try:
        # fresh=True：探测走实时请求、不吃 TTL 缓存（build_clients 的一等参数）
        clients = build_clients(registry, transport, cache, fresh=True)

        results = []
        for src in registry.api_sources():
            client = clients.get(src.id)
            if client is None:
                results.append(ProbeResult(source=src.id, status="unavailable",
                                           role=src.role, reason="无客户端实现"))
            else:
                results.append(client.probe())

        overall = ProbeEngine.overall(results)
        return [r.to_dict() for r in results], overall
    finally:
        if _cleanup is not None:
            _cleanup()


# 凭证规格：check 名 / 环境变量名 / 未配的影响 / 配法。凭证不拉低 overall（spec §4）。
CREDENTIAL_SPECS = [
    {
        "check": "PAPER_MAILTO",
        "env": "PAPER_MAILTO",
        "impact": "Crossref、OpenAlex polite pool 提速（未配仍可查、查得全，仅慢）",
        "fix": "export PAPER_MAILTO=你的邮箱",
    },
    {
        "check": "SEMANTIC_SCHOLAR_API_KEY",
        "env": "SEMANTIC_SCHOLAR_API_KEY",
        "impact": "Semantic Scholar 提速到 10 req/s（未配仍可用，探测判 partial）",
        "fix": "export SEMANTIC_SCHOLAR_API_KEY=你的 key",
    },
    {
        "check": "NCBI_API_KEY",
        "env": "NCBI_API_KEY",
        "impact": "PubMed 提速到 10 req/s（补充源，未配不拉低整体）",
        "fix": "export NCBI_API_KEY=你的 key",
    },
]


def check_credentials():
    """凭证三件套是否配置。未配仅 ⚠️ 报告，不参与 overall 判定。"""
    import os
    out = []
    for spec in CREDENTIAL_SPECS:
        present = bool(os.environ.get(spec["env"]))
        out.append({
            "check": spec["check"],
            "status": "ok" if present else "missing",
            "detail": "已配置" if present else "未配置（可选，不影响核验可用性）",
            "impact": spec["impact"],
            "fix": spec["fix"],
        })
    return out


def check_cache():
    """缓存目录可解析 + 可写。试写临时文件后立即删除——不建库、不留痕。"""
    import os
    import tempfile
    try:
        from paper_shared.datasources.cache import default_cache_dir
        cache_dir = default_cache_dir()
    except Exception:
        # _shared 不可导入：退回 os.path 推断默认位——三向分支与 default_cache_dir() 对齐
        # （PAPER_CACHE_DIR→原样；XDG_CACHE_HOME→/paper；默认→~/.cache/paper）
        env = os.environ.get("PAPER_CACHE_DIR")
        if env:
            cache_dir = pathlib.Path(env)
        else:
            xdg = os.environ.get("XDG_CACHE_HOME")
            if xdg:
                cache_dir = pathlib.Path(xdg) / "paper"
            else:
                cache_dir = pathlib.Path.home() / ".cache" / "paper"
    path = str(cache_dir / "datasources.db")
    # 跟踪本次诊断是否新建了 cache_dir：事后若新建则只删最深一层，绝不递归删 parents
    created = not cache_dir.exists()
    try:
        # 试写：在目录下写临时文件再删，不实例化 Cache（避免建库表）
        cache_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(cache_dir), prefix="_paper_doctor_probe_")
        os.close(fd)
        os.unlink(tmp)
        return {"check": "cache", "status": "ok", "path": path, "detail": "目录可写", "fix": None}
    except OSError as e:
        return {"check": "cache", "status": "fail", "path": path,
                "detail": f"目录不可写：{e}",
                "fix": "检查目录权限，或设置 $PAPER_CACHE_DIR 指向可写位置"}
    finally:
        # 无副作用诊断：若本次新建了 cache_dir 则删最深一层（不删 parents、空时才成功）
        if created:
            try:
                cache_dir.rmdir()
            except OSError:
                pass


def check_typeset_toolchain() -> List[Dict[str, Any]]:
    """pandoc / xelatex / 中文字体三项——服务 `/paper-typeset` 的格式转换。

    探测实现在 `_shared/paper_shared/toolchain.py`，本函数只做契约适配：两边各写
    一份探测必然漂移（doctor 说 pandoc 可用、typeset 说不可用，用户无从判断哪个对）。

    **status 用 `warn` 而非 `fail`**：在 doctor 的语义里 `fail` = 核验根本跑不起来，
    会让 `compute_overall` 短路成 `blocked`。而这三项只影响转格式——没装 pandoc
    时 `/paper-verify`、`/paper-search` 照常工作，把整体体检判成 blocked 是误报。
    同理本组**不参与 `compute_overall`**（照 `check_cache` 的先例，见 run_all 注释）。

    延迟 import：`_shared` 不可导入时 doctor 仍须能出报告——那是 blocked 态能落地
    的前提（同 `check_shared_import` 的立场）。
    """
    shared = str(pathlib.Path(__file__).resolve().parents[2] / "_shared")
    if shared not in sys.path:
        sys.path.insert(0, shared)
    try:
        from paper_shared import toolchain
        probe = toolchain.probe_all()
    except Exception as e:
        return [{"check": "typeset_toolchain", "status": "warn",
                 "detail": f"探测层不可导入：{type(e).__name__}: {e}",
                 "fix": "确认 skills/_shared/paper_shared/toolchain.py 存在；"
                        "该组只影响 /paper-typeset 转格式，不影响引用核验与检索"}]
    out: List[Dict[str, Any]] = []
    for key in ("pandoc", "xelatex"):
        r = probe[key]
        out.append({"check": key,
                    "status": "ok" if r["available"] else "warn",
                    "detail": r["version"] or "未检测到",
                    "fix": r["fix"]})
    f = probe["cjk_fonts"]
    out.append({
        "check": "cjk_font",
        "status": "ok" if f["available"] else "warn",
        "detail": (f"{len(f['fonts'])} 个可用，首选 {f['fonts'][0]}（来源：{f['source']}）"
                   if f["available"] else "未检测到"),
        "fix": f["fix"],
    })
    return out


def infer_network(datasources_overall):
    """网络状态据核心数据源可达性推断——doctor 不额外发请求。

    offline = 核心源全不可达；ok = 至少有核心源可达（含 degraded）；
    unknown = _shared 不可导入、无探测结果。
    """
    if datasources_overall is None:
        return {"status": "unknown", "detail": "_shared 不可导入，无法探测数据源"}
    if datasources_overall == "offline":
        return {"status": "offline", "detail": "核心数据源全不可达，推断为断网或出口被阻"}
    # ok / degraded 都表示至少部分核心源可达 → 网络在线
    return {"status": "ok", "detail": "依据核心数据源可达性推断"}


def compute_overall(runtime, network_status, datasources_overall,
                    has_supplementary_unavailable):
    """四态短路判定（spec §4），优先级 blocked > offline > degraded > ok。

    runtime     : list[dict]——runtime 检查项（status ok|fail）
    network_status        : str——infer_network 的 status（ok|offline|unknown）
    datasources_overall   : str|None——probe 的 overall（ok|degraded|offline|None）
    has_supplementary_unavailable : bool——补充源是否有 unavailable（叠 degraded）
    """
    # 1. blocked：runtime 任一 fail（核验根本跑不起来）
    if any(item.get("status") == "fail" for item in runtime):
        return "blocked"
    # 2. offline：网络断 或 核心数据源全不可达
    if network_status == "offline" or datasources_overall == "offline":
        return "offline"
    # 3. degraded：数据源 degraded 或 补充源不可达
    if datasources_overall == "degraded" or has_supplementary_unavailable:
        return "degraded"
    # 4. ok
    return "ok"


def run_all(transport=None, cache=None):
    """组装完整体检报告 dict（契约见 spec §5）。"""
    runtime = [check_python_version(), check_sqlite3(), check_shared_import()]

    # 数据源探测：_shared 不可导入时返回 ([], None)
    datasources, ds_overall = run_probe_fresh(transport=transport, cache=cache)

    network = infer_network(ds_overall)
    credentials = check_credentials()
    cache_report = check_cache()

    # cache 检查失败是否影响 overall？spec 未把 cache 列入四态触发——
    # 缓存是性能设施（数据源 spec §8：缓存是性能设施而非证据）。
    # cache fail 不阻塞核验（顶多慢/重复请求），故不改 overall，只在报告层标 fail。

    # typeset 工具链同理、且更明确：pandoc / xelatex / 中文字体缺失只让
    # /paper-typeset 产不出对应格式，引用核验与检索完全不受影响。故本组
    # **不进 compute_overall**，且用 warn 而非 fail（fail 会短路成 blocked）。
    typeset = check_typeset_toolchain()

    # 补充源是否有 unavailable（用于叠 degraded）
    has_supp_unavail = any(
        d.get("role") == "supplementary" and d.get("status") == "unavailable"
        for d in datasources
    )

    overall = compute_overall(runtime, network["status"], ds_overall, has_supp_unavail)

    return {
        "overall": overall,
        "runtime": runtime,
        "credentials": credentials,
        "network": network,
        "cache": cache_report,
        "typeset": typeset,
        "datasources": datasources,
        "datasources_overall": ds_overall,
    }


def main():
    report = run_all()
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
