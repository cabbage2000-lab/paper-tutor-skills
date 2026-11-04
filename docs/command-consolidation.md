# 子命令合并设计

设计日期：2026-11-04。目标是降低安装后的选择成本，公开入口不超过 5 个。

## 用户体验

| 公开入口 | 用户目的 | 合并的内部能力 |
| --- | --- | --- |
| `/paper-help` | 起步、了解能做什么、排障 | init、help、doctor |
| `/paper-research` | 研究准备与文献工作 | topic、search、import、screen、daily、method、proposal |
| `/paper-write` | 根据已有材料成文和制图 | outline、draft、abstract、style、figure、plot；anchor 保持开发中 |
| `/paper-check` | 检查已有稿件并处理反馈 | verify、format、claim、logic、review、revise |
| `/paper-submit` | 准备投稿与交付文件 | submit、disclose、typeset |

用户直接说“帮我查引用真假”或“/paper-check 帮我查引用真假”。明确意图直接进入相关流程；模糊意图只澄清一次产物，不再次展示二十多个选项。不要求用户掌握二级子命令。

help 保留为新手入口，同时承接建项目和环境检查；将这两个能力单独保留会消耗有限的入口名额。文献工作集中在 research；logic 归入 check，使 write 聚焦产出、check 聚焦已有材料的检查。submit 的含义扩展到交付准备，实际投稿仍由用户完成。

## 实现与兼容

- 只有五份 `SKILL.md` 参与宿主发现。原来的技能说明更名为 `WORKFLOW.md`，原目录保留脚本、参考资料和模板，不新增兼容别名入口。
- `skills/_shared/commands.yaml` 管公开入口；`workflows.yaml` 管内部能力、发布状态、入口归属与流程路径，保留原有观察项。格式与结论检查继续共用 verify 流程。
- 原脚本路径、相对导入、产物位置、项目配置与 `.paper/` 内部 ID 保持不变。进度视图读内部能力清单，展示中文任务和新入口。
- 新安装复制整个 `skills/`，不能只复制五个入口目录。升级必须替换本套件旧目录，普通覆盖复制会残留旧 `SKILL.md`，导致命令仍然很多。安装脚本先验证归属，再将旧目录移出发现路径保存备份，保留第三方技能；冲突则在写入前退出。
- README、中英文示例、安装说明、插件描述和流程交接语同步到五入口；历史 CHANGELOG 与验收记录保留历史语境。

## 验收

递归扫描发布包及升级后的目标目录，本套件必须恰好只有五份 `SKILL.md`；所有原能力有且仅有一个公开归属；全部流程路径可解析；开发中能力不被提升为已发布；旧留痕解析结果不变。测试覆盖新装、从旧版升级、重复安装、同名第三方冲突和复制失败恢复，并运行现有离线回归测试。

宿主中的自然语言触发质量与菜单刷新需在新会话中人工验收；仓库结构测试不等同于真实宿主验证。合并实现阶段仅修改仓库；后续按用户要求以 v0.2.0 发布，已安装副本仍需按升级说明更新。

## 本次验证记录

- `python3 scripts/validate_commands.py` 通过：递归发现恰好五个公开入口，内部流程链接全部可解析。
- 全量离线回归：`python3 -m pytest tests/ -q --ignore=tests/datasources/smoke_real_api.py -p no:asyncio`，996 passed、24 subtests passed。初次检查发现排版模块原有的 CSL 文件缺失，并在未修改 HEAD 中复现；准备 v0.2.0 时已从 v0.1.8 原样恢复两份 CSL 及许可声明，全部测试通过。
- 安装测试覆盖新装、全量旧入口升级、重复安装、第三方保留、同名冲突、符号链接、复制失败和移动失败恢复。安装后的核验、检索、排版、风格脚本均从外部工作目录成功执行 `--help`，确认共享导入路径仍可用。
- `git diff --check` 通过。五入口的 name、slug、description、版本和路由由仓库测试校验。skill-creator 通用检查器不接受本仓库既有的 SkillHub 扩展字段（slug/displayName/version/summary），因此保留分发兼容字段并使用仓库的元数据守卫，不以通用检查器结果冒充宿主验收。
