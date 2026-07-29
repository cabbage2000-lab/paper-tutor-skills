# CLAUDE.md

本文件为 Claude Code 在 Paper-Tutor-Skills 仓库的工作指导。

## 项目概述

Paper-Tutor-Skills 是一套装进编程智能体的**学术辅导** agent skills，简体中文优先，面向中文研究生与科研工作者。v0.1.0 起提供 25 个命令入口 / 23 个 skill 目录，覆盖学术研究 5 阶段全生命周期。

核心分工：**AI 负责效率（检索、整理、核对、结构化），人负责研究决策（想法、判断、数据、结论）**。

产品定位是**辅导，不是代笔**：不代生成研究想法与原创结论、不代跑实验、不编造数据与引用、不端到端无人确认出稿、不做规避 AI 检测、不出具伦理豁免判断、不接收他人在审稿件。每条边界的审查判据、依据与出口指引在 [边界拒绝清单](skills/_shared/references/边界拒绝清单.md)（A 类产品边界 8 条 + B 类拒绝的机制 4 条 + 四问审查判据）——**新功能提案先过这把尺子**。

两条不与其他目标权衡的底线：**不编造**（文献核验以真实 API 响应为准，不凭模型记忆）、**留痕如实**（使用记录如实反映人机分工，不美化）。

## 常用命令

```bash
# 全量测试（CI 同命令，秒级跑完）
python3 -m pytest tests/ -q --ignore=tests/datasources/smoke_real_api.py

# 单个 skill 的测试
python3 -m pytest tests/paper-verify -q

# 真实 API 冒烟（打 Crossref / OpenAlex 等真实端点，有网络与配额依赖，按需手工跑）
python3 -m pytest tests/datasources/smoke_real_api.py -q

# 把 skills/ 镜像同步安装到本地测试项目（幂等；本地开发脚本，不入库）
python3 sync_skills.py --list                                   # 干跑，只打印计划
python3 sync_skills.py                                          # 同步全部
python3 sync_skills.py --skill paper-init --target <skills 目录>  # 选择性同步
```

本机无 `python` 别名，一律用 `python3`；若环境装了 pytest-asyncio 须补 `-p no:asyncio`。CI 配置见 [`.github/workflows/tests.yml`](.github/workflows/tests.yml)（push / PR 触发，只跑 pytest，无覆盖率门与 lint 门）。

## 架构

**`skills/` 是分发单元**——整目录成套安装。skill 之间以相对路径（`../_shared/...`）互引，单个 skill 拆出去会断链。

```text
skills/
├── paper-<word>/          # 一个 skill 一个目录，目录名 = 命令名去斜杠
│   ├── SKILL.md           # 必需：frontmatter（name、description）+ 行为指令
│   ├── references/        # 按需：分层加载的详细规则（核验协议、话术库、格式规则）
│   ├── scripts/           # 按需：本 skill 专用的确定性脚本
│   └── assets/            # 按需：模板等静态资源
└── _shared/               # 唯一的非 skill 目录（下划线前缀 = 永不放 SKILL.md）
    ├── commands.yaml      # 命令主清单（单一事实来源）
    ├── paper_shared/      # Python 包根
    │   ├── datasources/   # 文献 API 客户端 + 缓存 / 分批退避 / DOI 注册机构路由
    │   └── toolchain.py   # pandoc / xelatex / 中文字体探测（doctor 与 typeset 共用）
    └── references/        # 跨 skill 权威定义（见下「共享约定」）
```

`_shared/` 的准入规则：**至少两个 skill 使用**的资源才进来，单 skill 专用的留在自己的 `scripts/` / `references/`。

数据源层已接入 arXiv、OpenAlex、Semantic Scholar、Crossref、PubMed、ERIC，DOI 按注册机构分流（Crossref / DataCite / ISTIC；ISTIC 即中文 DOI，径直落「待人工核对」）。

其余目录：`tests/` 与 skills 平行（每个 skill 一个子目录 + `fixtures/` 共享语料）；`evals/` 放裸模型对比记录；`scripts/` 放仓库级工具（`extract_changelog_notes.py`）；入库的文档只有 `docs/prd/`（产品定位与设计理念，权威）与 `docs/examples/`。

### 插件分发（Claude Code 与 Codex）

仓库根的清单文件让**仓库自身成为一个插件市场**，两个宿主都能一键装：

| 宿主 | 清单文件 | 用户侧命令 |
| --- | --- | --- |
| Claude Code | `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` | `/plugin marketplace add cabbage2000-lab/paper-tutor-skills` |
| Codex | `.codex-plugin/plugin.json` + `.agents/plugins/marketplace.json` | `codex plugin marketplace add cabbage2000-lab/paper-tutor-skills` |

这是**增量增强、不替换任何东西**：`skills/` 散装主体原样保留，其他宿主照常按 SKILL.md 装载——与硬规则 3 的跨宿主中立不冲突。

- **plugin 根 = 仓库根**，所以 `skills/` 天然在正确位置。两个 `.*-plugin/` 目录里**只放清单文件**，skill 内容绝不能塞进去（官方明确的坑，放错则一个 skill 都加载不到）。
- **两套清单不能合并**：格式实打实不同——Codex 的 plugin.json 多要 `skills: "./skills/"` 指针与一整块 `interface`（`displayName` / `shortDescription` / `longDescription` / `developerName` / `category` / `capabilities` / `defaultPrompt` 全必填），marketplace 条目的 `source` 是对象且必带 `policy`。四份清单的公共字段由 [`tests/test_plugin_manifest.py`](tests/test_plugin_manifest.py) 守住不漂。
- **`skills/_shared` 会让官方预检脚本报错，但不影响真实安装**——Codex 的 `plugin-creator/validate_plugin.py` 只跳过 `.` 开头的目录，遇到无 SKILL.md 的 `_shared` 会判 `skill '_shared' is missing 'SKILL.md'`。运行时摄取（`codex plugin add`）与 skill 加载器都只认含 SKILL.md 的目录，`_shared` 被静默忽略，23 个 skill 全部正常加载（2026-07-28 实测 codex-cli 0.145.0）。**因此不要为了讨好预检脚本去给 `_shared` 改名或补 SKILL.md**——那会同时踩中硬规则 2 与硬规则 6，换来的只是一个预检脚本的绿灯。
- **plugin name 取 `paper-tutor`**，命令因此呈现为 `/paper-tutor:paper-init`——前缀与命令名都带 paper，确实啰嗦。更简洁的 `/paper:init` 需要把 23 个 skill 目录改名为 `init`/`verify` 等，牵动硬规则 2（`name` = 目录名 = 命令名）、主清单、两个 README 与全部内部引用。**权衡结论：不值得，保持 `paper-tutor`。** 要推翻这个结论，得连同上述几处一起改。

宿主的 skills 目录各不相同，**装错位置的表现是命令一个都不出现**（不是报错，所以很难自查）：Claude Code 读 `~/.claude/skills/` 与项目级 `.claude/skills/`；Codex 读 `~/.codex/skills/` 与项目级 `.codex/skills/`、`.agents/skills/`，**不读 `.claude/skills/`**。散装安装用 `sync_skills.py --target <目录>`（本地脚本，不入库）。

### 发版

1. 在 `CHANGELOG.md` 写 `## [x.y.z] — 日期` 段落（Release notes 由它推导，段落缺失会让发布流程直接失败——宁可不发，也不发空白 Release）；
2. 同步 `.claude-plugin/` 两份清单、`.codex-plugin/plugin.json`、`skills/_shared/VERSION` 的 `version`，以及两个根 README 的三处版本号与那条 CHANGELOG 锚点（[`tests/test_plugin_manifest.py`](tests/test_plugin_manifest.py) 守着处处一致）。**README 是最容易漏的一处**——它曾停在 v0.1.2 漂过三个版本，锚点漏改则是静默死链；
3. 合入 main 后 `git tag -a vx.y.z -m "..." && git push origin vx.y.z`；
4. [`release.yml`](.github/workflows/release.yml) 自动跑测试并创建 Release。测试不过则不发布。

### 四个结构守卫测试（改动前先知道它们守什么）

它们抓的是「改了 A 忘了同步 B」这类无声漂移，失败诊断路径各不相同：

| 测试 | 守什么 |
| --- | --- |
| [`test_manifest_consistency.py`](tests/test_manifest_consistency.py) | `commands.yaml` ↔ skill 目录 ↔ SKILL.md 的 `name` ↔ 两个根 README 的命令表，四处一致；README 正文与**安装提示词**里的各种「N 个」算得对；`skills/README.md` 不得另存命令清单表格 |
| [`test_shared_conventions.py`](tests/test_shared_conventions.py) | 四层内容标注符号、学科三梯队、留痕契约字段在全仓库不漂移，其中的产品立场不被改写 |
| [`test_boundary_registry.py`](tests/test_boundary_registry.py) | 边界拒绝清单 ↔ README 不做表 ↔ PRD 边界条目三处不背离，同步锚点真实存在 |
| [`test_plugin_manifest.py`](tests/test_plugin_manifest.py) | 两宿主四份清单 ↔ `_shared/VERSION` ↔ **两个根 README** ↔ CHANGELOG 最新版本，版本号与描述处处一致，README 指向 CHANGELOG 的锚点真能跳到最新版本段；Codex 的 `skills` 指针与 `interface` 必填字段符合官方摄取口径；两个 `.*-plugin/` 里只放清单文件 |

## 硬规则

1. **`commands.yaml` 是单一事实来源**——新增或发布命令只改它；`paper-help` 的命令总表、`paper-init` 的发布映射表都从它推导。别处不得另存第二份命令清单（第二份真相必然漂移）；改了主清单须同步 `README.md` 与 `README.en.md` 的命令表。
2. **每个 skill 必须有非空 SKILL.md**——空文件会被宿主误识别为可用 skill。frontmatter `name` = 目录名 = 命令名：`paper-` 前缀 + 单个学术熟词，基础设施命令取工程熟词。一个 skill 可暴露多个命令入口（`paper-format` / `paper-claim` 内建于 `paper-verify`），这类内建子命令在主清单里必须写 `builtin_in: <宿主命令名>`。
3. **跨宿主中立**——核心路径只依赖通用 agent skills 标准：SKILL.md frontmatter + `references/` 分层加载 + 标准库脚本。宿主专有能力（结构化提问工具、hooks、子 agent 编排、斜杠命令语法）只能作**可选增强**，且必须写明纯文本降级路径，工具不可用或用户拒绝时行为一致——先例见 [`paper-init`](skills/paper-init/SKILL.md) 与 [`paper-help`](skills/paper-help/SKILL.md) 的提问路径。目标宿主：Claude Code / Codex / WorkBuddy，验证项见 [`tests/跨宿主验证清单.md`](tests/跨宿主验证清单.md)。
4. **核验类 skill 的降级必须明标**（代码层红线）——API 失败时显式标注「未核验」「待人工核对」，绝不静默用模型记忆顶替。偷偷编造会让使用者学错，这条不接受权衡。
5. **`.paper/` 与 `project.paper.yaml` 绝不写进 `.gitignore`**——指 `paper-init` 为用户研究项目生成的 `.gitignore`。`.paper/` 是人机分工的过程证据，只能在使用当时留下、事后无法重构；`project.paper.yaml` 是后续全体命令的长期记忆。
6. **跨 skill 共享约定不重复定义**——下列概念的权威定义在 `_shared/references/`，自己的 SKILL.md 里引用即可，不要重述、也不要列举同辈 skill 的名字（否则每加一个 skill 要改 N 处）：[四层内容标注](skills/_shared/references/四层内容标注.md)（👤/📋/🪞/❓）、[学科三梯队](skills/_shared/references/学科三梯队.md)、[留痕契约](skills/_shared/references/留痕契约.md)、[报告组件库](skills/_shared/references/报告组件库.md)。
7. **生产代码零第三方依赖**——Python 3.9+，只用标准库（数据源层只用 urllib + sqlite3）。pytest / pyyaml 仅测试期使用。
8. **语言**——简体中文优先，术语中文为主、英文括注。

## 开发流程（新增 skill）

1. 用 skill-creator 生成骨架——**不手工预建空目录**。
2. 实现：SKILL.md 写行为指令，详细规则下沉到 `references/` 分层加载，确定性逻辑进 `scripts/`。SKILL.md 中声明本 skill 覆盖研究生命周期的哪些环节、明确不覆盖哪些。
3. 写最小 pytest 单测：只测核心确定性逻辑（解析、路由、格式化等纯函数），秒级跑完。**不追覆盖率**——LLM 能力在提升，重测试的边际收益递减。
4. 过发布门，翻 `commands.yaml` 的 `status` 为 `released`，与实现同一次提交。

### 发布门（三条全过才发布）

| 门 | 内容 |
| --- | --- |
| 单测 | 核心确定性逻辑有 pytest 单测且通过 |
| happy path | 至少一条真实 API / 真实输入手工走通 |
| 主清单同步 | `commands.yaml` 的 `status` 翻为 `released`，全量测试通过 |

量化门槛（虚构检出率等）、过程中立性门、`evals/` 的裸模型对比不是发布门的必要条件，按需补；已有记录留在 `evals/` 与各 skill 的测试目录里，作样板参考。

## 提交与文档纪律

- 提交信息：`<类型>: <中文描述>`（如 `feat: paper-outline 论文大纲命令`）。面向使用者/开发者的显著变更记进 [CHANGELOG](CHANGELOG.md)，细碎提交不逐条收录。
- **链接纪律**：`docs/specs/`、`docs/plans/`、`docs/reports/`、`docs/reviews/`、`docs/superpowers/` 是内部稿、不随仓库发布。公开文件里**不得用 markdown 链接指向它们**（公开仓库里是死链），只能用纯文字指代（如「见内部稿·数据源模块设计 spec」）。
- **clean-room**：本项目为独立实现，不复制任何第三方项目的提示词、文本、代码或文件结构，只借鉴公开的设计理念；有借鉴须在 PR 描述中声明来源与本项目的独立做法。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。
