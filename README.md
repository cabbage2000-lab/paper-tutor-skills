# Paper-Tutor-Skills 学术辅导套件

![license](https://img.shields.io/badge/license-PolyForm--NC-blue)
![language](https://img.shields.io/badge/language-简体中文优先-green)
![status](https://img.shields.io/badge/status-v0.2.0-blue)
![host](https://img.shields.io/badge/host-Claude%20Code%20%7C%20Codex%20%7C%20WorkBuddy-grey)

**简体中文** | [English](README.en.md)

Paper-Tutor-Skills 是面向中文研究生与科研工作者的学术辅导技能套件。当前版本 **v0.2.0**；已将原来的细分命令合并为 **5 个命令入口**，对应 5 个 skill 目录：1 个起步导航入口 + 4 个研究命令。旧流程作为内部能力保留，用户只需说想完成什么。入口清单见 [`commands.yaml`](skills/_shared/commands.yaml)。

## 设计理念

**AI 提供知识、方法与过程辅导，Skill 提供实践工具，工程化方法帮助记录与复盘；最终的研究思考、判断与成果，由学习者自己完成。**

Paper-Tutor-Skills 把 AI 定位为**导师与教练**，而不是研究任务的执行者；把 Skill 定位为**学习与实践工具**，而不是一键完成研究的自动化能力；并把软件工程中的结构化、版本控制、过程留痕、可追溯引入学术研究学习——让长周期工作可中断、可续接、可审计。基于通用 agent skills 标准（SKILL.md + references/），不绑定单一宿主。

**不可妥协的底线**：不编造（文献核验以真实 API 响应为准，不凭模型记忆）、留痕如实（使用记录如实反映人机分工，不美化）。这条底线不与其他目标权衡。

## ✅ 能做的 / ⛔ 不做的

| ✅ Paper-Tutor-Skills 会做的 | ⛔ Paper-Tutor-Skills 不做的 |
| --- | --- |
| 检索文献、整理综述素材 | 代生成研究想法与原创结论 |
| 核验引用是否真实存在 | 代跑实验 / 代码、编造数据与引用 |
| 搭建标准科研工作目录 | 端到端无人确认直接出稿 |
| 大纲结构化、语言润色 | 做规避 AI 检测、出具伦理豁免判断 |
| 生成人机分工披露留痕 | 接收他人在审稿件 |
| 陈列常见选项与客观线索 | 对研究方向与文献下优劣定论 |
| 陈列开放获取状态与合法获取入口 | 提供绕过付费墙的获取路径 |

"不代写"不是缺点，是对研究诚信的承诺。面对"直接帮我写一篇"这类请求，Paper-Tutor-Skills 会先共情你的目标，再用你自己的语言讲清风险，最后给一个 5 分钟内可见成果的第一步——把目录搭好、把材料归位、从选题澄清起步。

> 每条「不做」的审查判据、依据与出口指引，见 [边界拒绝清单](skills/_shared/references/边界拒绝清单.md)——含 4 条评估过并拒绝的自动化机制（全链编排器、评分排序、静默降级、自动改写既有文件）。

## 五个入口怎么选

| 命令 | 什么时候用 | 示例 |
| --- | --- | --- |
| `/paper-help` | 不知道从哪开始、建项目、看进度、环境排障 | `/paper-help 帮我建一个研究项目` |
| `/paper-research` | 选题、文献检索/导入/筛选、每日追踪、方法、开题 | `/paper-research 找近三年关于我的研究问题的文献` |
| `/paper-write` | 大纲、分段写作、摘要、风格、图表与绘图代码 | `/paper-write 基于这些笔记整理引言大纲` |
| `/paper-check` | 引用真实性、格式、论证、结论、模拟评审、修订回复 | `/paper-check 核验这份稿件里的参考文献` |
| `/paper-submit` | 投稿材料、AI 使用披露、Word/LaTeX/PDF 导出 | `/paper-submit 把现有稿件导出为 Word` |

也可以直接说“我收到审稿意见了，帮我整理逐点回复”，不用背命令。明确需求会直接进入对应流程；只有任务不清楚时才简短澄清。命令后面的中文是自然语言示例，不是必须记住的二级子命令。

研究决策、真实数据、原创结论、逐项采纳与实际投稿仍由你负责。各流程原有的确认点继续保留，不会自动跑完整条研究流程。文献支撑补齐能力仍为开发中。

## 快速开始

**5 个命令入口**（v0.2.0）。首次使用可以说：`/paper-help 帮我建个科研工作目录`；它会收集项目名、位置等信息，展示方案后创建目录骨架。

### 安装与升级

将下面的话复制给你的智能体，把目标路径替换成你使用的宿主目录：

```text
帮我安装或更新 Paper-Tutor-Skills：
1. 克隆 https://github.com/cabbage2000-lab/paper-tutor-skills 到临时目录。
2. 在仓库根运行 python3 scripts/install_skills.py --target ~/.codex/skills --dry-run 查看计划。
3. 运行同一命令去掉 --dry-run 完成安装。
4. 告诉我安装路径、备份路径和五个公开入口，然后清理临时克隆目录。
不要清空目标 skills 目录，不要只复制五个入口文件夹，内部流程与 _shared 都是必需依赖。
```

| 宿主 | 用户级目录 | 项目级目录 |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex | `~/.codex/skills/` | `.codex/skills/` |
| WorkBuddy | `~/.workbuddy/skills/` | `.codebuddy/skills/` |

安装器整体复制 `skills/` 下的目录：只有 5 个 paper-* 目录含 `SKILL.md`，其余目录是内部流程和共享资源。升级时先检查本套件归属，将被替换的旧目录移到宿主配置目录下的 `.paper-tutor-backups/` 保存，然后安装新包；其他来源的技能保留，同名来源冲突会在写入前报错。备份路径会打印出来。

**旧版升级不能直接覆盖复制**：那样会残留旧 `SKILL.md`，菜单仍显示旧命令。使用上述安装器；升级后新开会话刷新技能。旧快捷命令不再注册，请改用上表的新入口加自然语言。已有研究目录、产物和 `.paper/` 记录无需改动。

插件安装渠道继续使用仓库现有的 Claude Code / Codex 市场清单。首次安装或更新时由宿主安装当前包；不要同时使用插件安装和目录安装，避免重复入口。Claude Code 插件可能带 `paper-tutor:` 前缀，例如 `/paper-tutor:paper-check`。已通过插件安装的用户走宿主的插件更新流程，不对插件缓存运行目录安装器。

插件命令（选择对应宿主）：

```text
# Claude Code 会话内
/plugin marketplace add cabbage2000-lab/paper-tutor-skills
/plugin install paper-tutor@paper-tutor-marketplace

# Codex 终端
codex plugin marketplace add cabbage2000-lab/paper-tutor-skills
codex plugin add paper-tutor@paper-tutor-marketplace
```

### 常见任务

- 文献：“/paper-research 整理这份知网导出题录”；“/paper-research 帮我筛选这批综述文献”。
- 写作：“/paper-write 从正文提炼摘要”；“/paper-write 根据真实数据写 matplotlib 绘图代码”。
- 检查：“/paper-check 只查参考文献格式”；“/paper-check 对照结果看看结论是否说过头”；“/paper-check 整理审稿意见和回复草案”。
- 投稿：“/paper-submit 根据真实使用记录生成 AI 披露”；“/paper-submit 整理投稿材料清单”。

合并依据、完整能力映射与兼容策略见[子命令合并设计](docs/command-consolidation.md)。

## 为什么可信

Paper-Tutor-Skills 把研究诚信的承诺落进了可验证的工程设计：

- **核验六态**：每条引用的核验结果是六种状态之一——VERIFIED（已核实）、METADATA_MISMATCH（元数据不符）、RETRACTED（已撤稿）、NOT_FOUND（未查到）、UNVERIFIED（未核验）、PENDING_MANUAL（待人工核对）。定位是**存在性核验**（存在 ≠ 引用恰当），以真实 API 响应为准，绝不凭模型记忆判断。

  > 量化门槛（虚构检出率、真实误报率、中文误伤等）目前不是发布门的必要条件，按需补跑并回填到 [`evals/`](evals/README.md)。但"以真实 API 响应为准、绝不凭模型记忆"是产品底线，不与任何目标权衡。
- **中英双轨检索**：英文文献接开放 API（arXiv、OpenAlex、Semantic Scholar、Crossref）自动检索；中文文献走"自动 + 引导"混合路径——**带中文 DOI 的期刊文献走 DOI 内容协商自动取题录**（标题 / 作者 / 刊名 / 卷期页 / 摘要，ISTIC 注册的中文核刊可用；知网自注册的 DOI 不回题录，落人工核对），其余生成知网 / 万方检索方案（检索式 + 筛选条件）引导你执行并回填，或用站内"导出引文"功能导出后自动解析入表。**检索产出声明各来源覆盖方式**（自动 / 回填 / 未覆盖）——缺了这个提示，你可能把"英文库没有"误判成"没人研究过"。中文文献 API 覆盖不到的绝不判为编造，而是落 PENDING_MANUAL 态并附人工核对包。
- **跨宿主不锁死**：实现不依赖任何宿主专有机制，编排与断点续跑用纯文件约定。目录约定是增强不是依赖——检测到标准目录则产物归位，否则落当前目录并提示。

## 仓库结构

四区：`skills/`（skill 包 + `_shared/` 共享层，[开发规范](skills/README.md)）、`tests/`（[行为验收与语料](tests/README.md)）、`evals/`（[裸模型 vs 带 skill 并排对比](evals/README.md)）、`docs/`（[产品 PRD](docs/prd/paper-tutor-skills-prd-v1.md) 与[学术论文全流程示例](docs/examples/学术论文全流程示例.md)）。其余设计文档（specs、实现计划、评审记录）为内部稿，不随仓库发布——**本 README 与 PRD 是对外公开信息的事实来源**。

## 贡献

想参与开发或二次定制，先读 [skills/README.md](skills/README.md) 的开发规范（skill 包标准结构、发布门、横切要求）与 [CONTRIBUTING.md](CONTRIBUTING.md)。发布门是三条：核心确定性逻辑有单测且通过、至少一条真实输入手工走通、内部能力 `workflows.yaml` 的 `status` 同步翻转；量化门槛、行为验收多场景、裸模型对比不是必要条件，按需补。

## 许可

本项目采用 **PolyForm Noncommercial License 1.0**——源码完全开放，允许个人学习、研究、教学、非商业分发与改造，**但禁止任何商业使用**（包括但不限于销售、打包进收费产品、商业服务集成）。许可全文见仓库根目录的 [LICENSE](LICENSE) 文件，或 [PolyForm 官网](https://polyformproject.org/licenses/noncommercial/1.0.0/)。
