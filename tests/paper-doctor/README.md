# paper-doctor 行为验收

| 项 | 内容 |
| --- | --- |
| 类型 | 行为验收清单（活文档） |
| 日期 | 2026-07-22 |
| 上游 | paper-doctor spec §9 |

验证外部可观察行为（脚本 JSON 输出 + SKILL.md 报告呈现 + 文件系统零变化断言），不测实现细节。核查命令只读、可直接复制执行。

## 发布门

命令已于 2026-07-23 由项目负责人决定翻 `released`（`_shared/commands.yaml`），先行发布时跨宿主验证记为「豁免待补」；同日第二宿主（Codex CLI）就绪后已补跑通过（见 [跨宿主核对包](跨宿主核对包.md)）。各门实况如下。

| 门 | 内容 | 状态 |
| --- | --- | --- |
| 行为验收 | 下方十场景全部通过 | 单测七项已过（`test_doctor.py`，CI 绿）；三项 [手动] 待人工核对 |
| 跨宿主验证 | ≥2 宿主触发与产出一致，含断网宿主上报 offline | 已通过（2026-07-23 补跑）：宿主 A Claude Code = `degraded`、宿主 B Codex CLI = `offline`，判定层五项「必须一致」全吻合；断网 offline 强制子项由宿主 B 沙箱网络受限（核心源全不可达）真实命中，显式声明核验不可用。逐项对照见 [跨宿主核对包](跨宿主核对包.md) |
| 裸模型对比（evals） | 豁免（基础设施命令，核心是确定性脚本；与 `/paper-init` 同例，见 [evals/README](../../evals/README.md)） | N/A |

## 十个验收场景

对应 spec §9.2。单测覆盖（`tests/paper-doctor/test_doctor.py`）标注 [单测]；需手动 / 真实环境标注 [手动]。

1. **[单测] 全绿 ok**：运行时正常 + 凭证齐 + probe 全 ok → overall `ok`，顶部结论指向可直接跑 verify/search。
2. **[单测] S2 无 key degraded**：S2 无 key（probe 报 partial）、其余核心源 ok → overall `degraded`，报告标降级项 + impact + fix，不判不可用。
3. **[单测] 可选凭证未配仍 ok**：全可达、仅 PAPER_MAILTO/NCBI_API_KEY 未配 → overall `ok`，凭证 ⚠️ 提示但不拉低（不 double count）。
4. **[单测] 补充源不可达**：pubmed/eric unavailable、核心源 ok → overall 至多 `degraded`，绝不 offline（CORE_IDS 规则）。
5. **[单测] 断网 offline**：核心源全不可达 → overall `offline`，network offline，显式声明核验不可用。
6. **[单测] Python <3.9 blocked**：伪造低版本 → overall `blocked`，环境未就绪，其余项仍照常报出。
7. **[单测] _shared import 失败 blocked**：破坏 import 路径 → shared_import fail → overall `blocked`，脚本不崩溃、仍输出结构化 JSON。
8. **[手动] 只体检不代修**：任一缺项场景，报告给 fix 指引但不执行修复，`find` 快照核查文件系统零变化。
9. **[手动] 越界拦截**：「帮我写一篇」触发 → 走三段式转化，不代写。
10. **[手动] 无脚本宿主降级**：禁用脚本执行 → 显式声明探测不可用 + 给手动核对清单，不凭记忆报就绪。

## 跑全部单测

```bash
# 在仓库根目录执行
python3 -m pytest -p no:asyncio tests/paper-doctor/ -v
```

## 真实环境冒烟

```bash
python3 skills/paper-doctor/scripts/doctor.py
```

断网环境下 overall 应为 `offline`（验证断网硬约束出口）。
