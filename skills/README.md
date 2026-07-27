# skill 包开发规范

| 项 | 内容 |
| --- | --- |
| 类型 | 开发规范（活文档） |
| 上游 | [CLAUDE.md·硬规则](../CLAUDE.md#硬规则)（本文件是它在 skill 包层面的展开，口径以 CLAUDE.md 为准） |

本目录是 Paper-Tutor-Skills 的**分发单元**：全部 skill 包 + 共享层 [`_shared/](_shared/README.md)。

## 目录约定

- 一个 skill 一个目录，**目录名 = 命令名去斜杠**（`paper-verify/` ↔ `/paper-verify`）；
- skill 目录由各自开发任务用 skill-creator 生成骨架，**不手工预建空目录**（空 SKILL.md 会被宿主误识别为可用 skill）；
- `_shared/` 是唯一的非 skill 目录（跨 skill 共享层），准入规则 = 至少两个 skill 使用。
- 套件身份靠命名（统一 `paper-` 前缀）+ 文档传达，不靠目录层级；`/paper-` + Tab 在支持的宿主里可列出全集。嵌套磁盘目录分组不可行（宿主只识别 skills 目录的第一层子目录）。

## skill 包标准结构

```text
paper-<word>/
├── SKILL.md          # 必需：frontmatter（name、description）+ 行为指令
├── references/       # 按需：分层加载的详细参考（核验协议、话术库、格式规则……）
├── scripts/          # 按需：确定性工具脚本（本 skill 专用；跨 skill 共用的进 _shared/）
└── assets/           # 按需：模板等静态资源
```

## SKILL.md 规范

- frontmatter `name` = 目录名 = 命令名：`paper-` 前缀 + 单个学术熟词（`verify`、`outline`），基础设施命令取工程熟词（`init`、`pipeline`）；
- `description` 用简体中文描述触发场景——**命令名即 skill 触发名**，自然语言描述任务即可触发；`/paper-xxx` 斜杠命令只是支持该机制的宿主中的快捷入口。
- 一个 skill 可暴露多个命令入口（先例：paper-verify 内建 paper-format 与 paper-claim）；
- SKILL.md 中声明本 skill 覆盖「5 阶段 23 环节」标尺中的哪些环节、明确不覆盖哪些。

## 发布门

| 门 | 内容 |
| --- | --- |
| 单测 | 核心确定性逻辑有 pytest 单测且通过（秒级、不追覆盖率） |
| happy path | 至少一条真实 API / 真实输入走通（手动验） |
| 主清单同步 | `commands.yaml` 的 `status` 翻转为 `released` |

**不是必要条件**（按需补）：行为验收多场景、量化门槛（虚构检出率 ≥95% 等）、过程中立性门、裸模型 vs 带 skill 对比、evals。

**发布联动**：发布任一命令时，在同一次提交里翻 `commands.yaml` 的 `status` 即可——paper-help 命令总表与 paper-init 命令发布映射表都从主清单推导、自动同步。

## 横切要求（每个 skill 都要满足）

- **跨宿主中立**：核心路径只依赖通用 agent skills 标准（SKILL.md frontmatter + `references/` 分层加载 + 标准库脚本）。宿主专有能力（结构化提问工具、hooks、子 agent 编排）只能作可选增强，且必须写明纯文本降级路径——先例见 `paper-init` / `paper-help` 的提问路径（CLAUDE.md 硬规则 3；验证项见 [`tests/跨宿主验证清单.md`](../tests/跨宿主验证清单.md)）。
- **拒绝边界**：碰到越界请求先共情目标、再讲清风险、最后给一个 5 分钟内可见成果的替代第一步。逐条判据与出口指引以 [`_shared/references/边界拒绝清单.md`](_shared/references/边界拒绝清单.md) 为准，不在自己的 SKILL.md 里另立标准。
- **降级明标**：调外部 API 的 skill 失败时必须显式标注「未核验」「待人工核对」，绝不静默用模型记忆顶替（CLAUDE.md 硬规则 4）。
- **披露留痕**：产物型 skill 按 [`留痕契约`](_shared/references/留痕契约.md) 追加写 `.paper/` 使用记录；`.paper/` 随用户项目入库，绝不写进 `.gitignore`（CLAUDE.md 硬规则 5）。

## 命令清单在哪

**不在本文件。**已发布命令、阶段归属、发布状态、各命令的已知观察项，全部以 [`_shared/commands.yaml`](_shared/commands.yaml) 的 `status` 字段与条目注释为准——它是单一事实来源（CLAUDE.md 硬规则 1），`paper-help` 的命令总表与 `paper-init` 的发布映射表都从它推导。

> 本文件曾另存一份「已发布 skill」表，结果停在最早的 6 个命令没跟上——20 个命令发布后才发现漂了 14 个。第二份真相必然漂移，故删除，并由 [`tests/test_manifest_consistency.py`](../tests/test_manifest_consistency.py) 守着：本文件再出现表格式命令清单会导致测试失败。

**样板参考**：`paper-init` / `paper-help` / `paper-doctor` / `paper-verify` / `paper-search` / `paper-topic` 这六个额外过了量化门槛、过程中立性门与行为验收多场景，其测试目录可作完整档样板；各命令的已知观察项记在主清单的条目注释里。

## 跨 skill 共享约定（新增 skill 必读）

下列概念被多个 skill 复用，权威定义在 `_shared/references/`，**不要在自己的 SKILL.md 里重新定义、也不要列举同辈 skill 的名字**（那会让每加一个 skill 都要改 N 处）：

| 约定 | 权威定义 | 用它的 skill 数 |
| --- | --- | --- |
| 四层内容标注（👤/📋/🪞/❓） | [`四层内容标注.md`](_shared/references/四层内容标注.md) | 11+ |
| 学科三梯队 | [`学科三梯队.md`](_shared/references/学科三梯队.md) | 9+ |
| `.paper/` 留痕字段与四级辅助级别 | [`留痕契约.md`](_shared/references/留痕契约.md) | 19 生产者 / 2 消费者 |
| 产物 HTML 组件与色板 | [`报告组件库.md`](_shared/references/报告组件库.md) | 16 |

这四份定义由 [`tests/test_shared_conventions.py`](../tests/test_shared_conventions.py) 守着——符号漂移、字段漏定义、产品立场被改写都会让测试失败。
