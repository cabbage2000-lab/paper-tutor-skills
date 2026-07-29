# Paper-Tutor-Skills 学术辅导套件

![license](https://img.shields.io/badge/license-PolyForm--NC-blue)
![language](https://img.shields.io/badge/language-简体中文优先-green)
![status](https://img.shields.io/badge/status-v0.1.2-blue)
![host](https://img.shields.io/badge/host-Claude%20Code%20%7C%20Codex%20%7C%20WorkBuddy-grey)

**简体中文** | [English](README.en.md)

Paper-Tutor-Skills 是一套装进编程智能体（Claude Code / Codex / 国内 WorkBuddy）的学术辅导 skills，简体中文优先——AI 管效率（检索、整理、核对、结构化），人管研究决策（想法、判断、数据、结论）。为中文研究生与科研工作者设计——学生自助研究、导师带学生做科研训练、投稿前批量自查（工具形态不变）。当前 **v0.1.2**：25 个命令入口（`/paper-init` `/paper-help` `/paper-doctor` `/paper-daily` 四个工作台基础设施 + 选题 / 检索 / 写作 / 评审 / 投稿全链路 21 个研究命令），分布在 23 个 skill 目录，覆盖学术研究 5 阶段全生命周期。命令的准确清单与各自的已知观察项以 [`skills/_shared/commands.yaml`](skills/_shared/commands.yaml) 为准。

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

"不代写"不是缺点，是对研究诚信的承诺。面对"直接帮我写一篇"这类请求，Paper-Tutor-Skills 会先共情你的目标，再用你自己的语言讲清风险，最后给一个 5 分钟内可见成果的第一步——把目录搭好、把材料归位、从选题澄清起步。

> 每条「不做」的审查判据、依据与出口指引，见 [边界拒绝清单](skills/_shared/references/边界拒绝清单.md)——含 4 条评估过并拒绝的自动化机制（全链编排器、评分排序、静默降级、自动改写既有文件）。

## 研究全流程 × Paper-Tutor-Skills 能力

| 研究阶段 | Paper 命令 | 做什么 | 状态 |
| --- | --- | --- | --- |
| **起步** | `/paper-init` | 搭建标准科研工作目录（一轮提问就绪，顺带生成项目信息配置与可选的宿主配置文件） | ✅ 已发布 |
| **导航** | `/paper-help` | 命令导航器，找当下该用哪个命令 | ✅ 已发布 |
| **体检** | `/paper-doctor` | 环境就绪度体检——查清核验/检索环境能不能用、缺什么、怎么补 | ✅ 已发布 |
| **日常** | `/paper-daily` | 每日学术雷达——抢发检测 + 新发泛读，不打分不排序 | ✅ 已发布 |
| **选题与立项** | `/paper-topic` `/paper-search` `/paper-screen` `/paper-method` `/paper-proposal` | 选题澄清、文献检索、系统综述 PRISMA 筛选、研究设计参谋、开题报告组装 | ✅ 已发布 |
| **执行研究** | —（不设命令） | 数据采集 / 实验 / 分析属物质世界环节，明文留给人——这是 AI 负责效率、人负责研究决策的边界，不是缺口 | 🚫 明文不覆盖 |
| **成文** | `/paper-outline` `/paper-draft` `/paper-logic` `/paper-abstract` `/paper-import` `/paper-figure` `/paper-plot` `/paper-style` | 大纲、草稿、论证链检查、摘要、题录导入、图表可视化辅助、绘图代码生成、风格校准 | ✅ 已发布 |
| **评审与修订** | `/paper-verify` `/paper-format` `/paper-claim` `/paper-review` `/paper-revise` | 引用存在性核验、GB/T 7714 格式检查、结论夸大检查、模拟评审、修订辅助 | ✅ 已发布 |
| **发表与发表后** | `/paper-disclose` `/paper-submit` `/paper-typeset` | AI 使用说明生成、投稿准备、出版链（LaTeX / DOCX / PDF + 国标著录） | ✅ 已发布 |

## 快速开始

**25 个命令入口已发布**（v0.1.2——已知边界见 [CHANGELOG](CHANGELOG.md#012--2026-07-28)），覆盖学术研究 5 阶段全生命周期，逐命令见上表。今天就能先试一个（`/paper-doctor` 有 [验收记录](tests/paper-doctor/README.md)）。

### 安装

**复制下面对应你的智能体的那段话，粘贴给它就行**——它会自己装完，你不用敲任何命令。

**装到 Claude Code** 👇

```text
帮我安装 Paper-Tutor-Skills 学术辅导套件：

1. 把 https://github.com/cabbage2000-lab/paper-tutor-skills 克隆到一个临时目录
2. 确保 ~/.claude/skills/ 存在（没有就创建），把仓库 skills/ 下的**全部子目录**
   复制进去，一个都不能少（23 个 paper-* 加 1 个 _shared）
   - 同名目录直接覆盖，这就是更新
   - 该目录下其他来源的 skill 一个都别动，千万不要清空目录
   - _shared/ 没有 SKILL.md、不会显示成命令，但每个 skill 都用 ../_shared/ 引用它，
     漏装会全面断链，必须一起装
3. 删掉临时目录
4. 告诉我装到了哪里、有哪些命令可用
```

**装到 Codex** 👇

```text
帮我安装 Paper-Tutor-Skills 学术辅导套件：

1. 把 https://github.com/cabbage2000-lab/paper-tutor-skills 克隆到一个临时目录
2. 确保 ~/.codex/skills/ 存在（没有就创建），把仓库 skills/ 下的**全部子目录**
   复制进去，一个都不能少（23 个 paper-* 加 1 个 _shared）
   - 同名目录直接覆盖，这就是更新
   - 该目录下其他来源的 skill 一个都别动，千万不要清空目录
   - _shared/ 没有 SKILL.md、不会显示成命令，但每个 skill 都用 ../_shared/ 引用它，
     漏装会全面断链，必须一起装
3. 删掉临时目录
4. 告诉我装到了哪里、有哪些命令可用
```

**装到 WorkBuddy** 👇

```text
帮我安装 Paper-Tutor-Skills 学术辅导套件：

1. 把 https://github.com/cabbage2000-lab/paper-tutor-skills 克隆到一个临时目录
2. 确保 ~/.workbuddy/skills/ 存在（没有就创建），把仓库 skills/ 下的**全部子目录**
   复制进去，一个都不能少（23 个 paper-* 加 1 个 _shared）
   - 复制的是子目录本身，别把整个 skills/ 目录整体套进去——WorkBuddy 会按目录层级
     给技能命名，多套一层命令就变成 skills:paper-init 了
   - 同名目录直接覆盖，这就是更新
   - 该目录下其他来源的 skill 一个都别动，千万不要清空目录
   - _shared/ 没有 SKILL.md、不会显示成命令，但每个 skill 都用 ../_shared/ 引用它，
     漏装会全面断链，必须一起装
3. 删掉临时目录
4. 告诉我装到了哪里、有哪些命令可用
```

装完**新开一个会话**才会加载——已开的会话看不到新命令。WorkBuddy 还可以在「技能」面板里核对是否装齐。

> **只想在单个项目里用？** 把提示词里的用户级路径换成该项目根目录下的项目级目录：Claude Code 用 `.claude/skills/`，Codex 用 `.codex/skills/`，**WorkBuddy 用 `.codebuddy/skills/`**——注意不是 `.workbuddy/`，它的用户级目录叫 `~/.workbuddy/`，项目级目录却沿用底层 CodeBuddy 内核的 `.codebuddy/`，这一处不对称是实测结论，写错了命令一个都不出现。
>
> **用的是别的宿主？** 同一段提示词，把目标路径换成该宿主的 skills 目录即可。装错位置的表现是命令一个都不出现、且没有任何报错——三个宿主的目录**互不读取**（**Codex 与 WorkBuddy 都不读 `.claude/skills/`，Claude Code 也不读 `.codex/skills/`**），几个宿主都用就各装一份。
>
> **想先只试一个？** 把第 2 步换成「只复制 skills/paper-init 和 skills/_shared」。

#### 更喜欢自己敲命令？Claude Code 与 Codex 支持插件式一键安装

本仓库自身就是插件市场，插件形态多一个好处：能用一条命令更新。WorkBuddy 走上面的提示词路径（本仓库尚未提供经实测的 WorkBuddy 插件清单）。

Claude Code——在会话里依次执行：

```text
/plugin marketplace add cabbage2000-lab/paper-tutor-skills
/plugin install paper-tutor@paper-tutor-marketplace
```

25 个命令以 `paper-tutor:` 前缀成组出现（`/paper-tutor:paper-init`、`/paper-tutor:paper-verify`……），更新用 `/plugin update paper-tutor`。

Codex——在终端里执行：

```bash
codex plugin marketplace add cabbage2000-lab/paper-tutor-skills
codex plugin add paper-tutor@paper-tutor-marketplace
```

命令直接是 `/paper-init`、`/paper-verify`（Codex 不加 plugin 名前缀）。

两条路装的是同一套 skill，**别两种都装**——会出现两份、命令重复。插件形态只改变命令的显示方式，`skills/` 散装主体原样保留，跨宿主装载不受影响。

### 30 秒试一下

装好后，随便建一个空目录，对你的 AI 助手说：

> 用 /paper-init 帮我建个科研工作目录

它会一次性问你四个问题：

1. **项目名**（会成为目录名，比如"ChatGPT 对本科生写作效率的影响"）
2. **范围**（只做这一个项目，还是多项目并行的工作区）
3. **建在哪**（默认当前目录）
4. **要不要 git 版本管理**（默认要）

你确认方案后，它只建目录骨架 + README + .gitignore，绝不预建留痕目录、不生成任何研究内容——后续命令发布后，留痕目录 `.paper/` 会在你首次使用时自动创建。

## 怎么开口问：按研究阶段的提问示例

**不用背命令名。** 用你自己的话说出你卡在哪，宿主会匹配到对应的 skill；实在不知道该用哪个，就问一句 `/paper-help`，它一轮提问帮你定位（回复「看我用到哪了」还能扫 `.paper/` 出研究全貌）。当然你也可以直接显式调用 `/paper-verify` 这样的命令名，两种方式等价。

> **提问只是开场，不是一问一答。** 每个命令都会先问清你的情况、在检查点停下等你拍板，确认前零落盘。研究决策始终在你手上——它给的是选项、事实、对照与疑问句，不是答案。跨天、跨会话也没关系：`.paper/` 留痕让每个阶段都能新开一个会话续上。

### 起步与日常（跨阶段基础设施，任何时候都能用）

| 你会这么问 | 落到 | 你会拿到 |
| --- | --- | --- |
| "帮我建个放论文材料的文件夹" / "新开一个课题，目录怎么摆才规范" | `/paper-init` | 标准科研目录骨架 + README + `.gitignore` + `project.paper.yaml`（项目长期记忆） |
| "Paper 都能干什么" / "我想写论文但不知道从哪开始" / "我用到哪一步了" | `/paper-help` | 1-3 个最匹配的命令 + 为什么推荐它；或按阶段分组的研究全貌视图 |
| "为什么核验跑不起来" / "这些数据源通不通、要不要配 key" | `/paper-doctor` | 运行环境 / 数据源 / 网络 / 凭证 / 缓存五维体检报告 + 缺什么怎么补 |
| "我这个 idea 被人抢发了吗" / "今天 arXiv 这方向有什么新论文" | `/paper-daily` | 抢发对照 + 新发泛读日报（HTML+MD+JSON）；给高/中/低相关度标签，但不打分不排序 |

### 阶段 A · 选题与立项

| 你会这么问 | 落到 | 你会拿到 |
| --- | --- | --- |
| "我想研究 AI 和教育，但不知道具体做什么" / "我这个题你看行不行" | `/paper-topic` | 逐层给该方向学界常见的选项（不推荐不排序，每组带「以上都不是，我自己说」）→ 你拍板的 RQ + 过程报告 |
| "有没有人研究过 X" / "这方向国内外做到哪一步了" / "帮我搜搜文献" | `/paper-search` | `literature/文献笔记表.md` + 检索日志；每次都声明各来源覆盖方式（自动检索 / 你回填 / 未覆盖） |
| "这批文献怎么筛" / "纳排标准怎么定" / "PRISMA 流程图的数字对不上" | `/paper-screen` | 两轮筛选台账 + 过了计数守恒校验的 PRISMA 流程图 + 数据提取表骨架（纳排你逐篇拍板） |
| "问卷能回答我的问题吗" / "方法怎么选" / "我的研究需要伦理审查吗" | `/paper-method` | 方法-RQ 匹配维度陈列，或该方向常见方法类；涉人类被试强制附六项伦理审查提示（须机构确认） |
| "我要开题了，报告怎么组" / "选题依据这节怎么写" | `/paper-proposal` | 按中文学位论文制度节点摆的开题报告骨架 + 从 topic/search/method 真实产物提取的片段（研究内容、创新点标占位请你填） |

### 阶段 B · 执行研究：**这里没有命令**

数据采集、实验、分析属于物质世界的环节，明文留给你自己。所以 "帮我跑个实验" "帮我编一组数据凑结论" 会被拦下——这是「AI 负责效率、人负责研究决策」的边界，不是缺口。

### 阶段 C · 成文

| 你会这么问 | 落到 | 你会拿到 |
| --- | --- | --- |
| "论文分几章好" / "帮我把大纲列一下" / "帮我想想结构" | `/paper-outline` | 带文献锚点的章节大纲草案，逐章由你拍板；无笔记支撑的要点标「⚠️ 纯结构占位」 |
| "这段引言写不下去" / "基于大纲帮我展开方法这一段" | `/paper-draft` | 逐段正文初稿，每段尽量挂真实笔记锚点、无支撑标 ⚠️；可先贴 1-2 段你自己写的当风格样本（只学风格不抄内容） |
| "这几章读着不像一个人写的" / "我的句子是不是太长了" / "被 AIGC 判成 AI 生成要申诉" | `/paper-style` | 六组由脚本机械算出的特征表 + 章节间偏移（按变异系数排序）；可存成 `风格基线.md` 供 `/paper-draft` 复用 |
| "RQ 和结论对得上吗" / "我的论证有没有漏" / "方法能不能回答我的问题" | `/paper-logic` | RQ→方法→结果→结论四链结构对应陈列（只核结构不核内容真伪，禁「断裂 / 强弱」定性词） |
| "帮我从正文提炼摘要" / "关键词选几个" | `/paper-abstract` | 摘要初稿，每句可追溯回正文出处；句子是 AI 重组生成的新句，顶部标「成句生成级」披露 |
| "知网导出的题录帮我整理进来" / "核对下题录和草稿引用对不对得上" | `/paper-import` | 题录整理入笔记表 + 题录-草稿一致性核对报告（只陈列对应关系，不判存在性——那归 `/paper-verify`） |
| "我该画什么图" / "帮我看看这张图有什么问题" / "配色怎么选才色盲友好" | `/paper-figure` | 5 维度诊断，或图类/图注/配色/坐标轴/工具 5 组件建议（配色标 hex + 色板来源） |
| "给我一个画柱状图的 matplotlib 脚本" / "帮我写段代码画箱线图" | `/paper-plot` | 可运行的 `.py` / `.R` 代码（v1.0 支持 7 类图 × matplotlib/ggplot2）；没贴真实数据一律用 `PAPER_PLACEHOLDER` 占位 |

### 阶段 D · 评审与修订

| 你会这么问 | 落到 | 你会拿到 |
| --- | --- | --- |
| "这些参考文献是真的吗" / "投稿前帮我自查一下引用" / "这条 DOI 能查到吗" | `/paper-verify` | 逐条六态结果（已核实 / 元数据不符 / 已撤稿 / 未找到 / 无法核实 / 待人工核对），以真实 API 响应为准；中文文献一律落待人工核对 + 附核对包，绝不标编造嫌疑 |
| "参考文献格式符合国标吗" | `/paper-format`（内建于 verify） | GB/T 7714-2015 逐条著录格式问题（纯规则判定） |
| "我的结论有没有说过头" | `/paper-claim`（内建于 verify） | 结论-结果对照陈列，只摆对照不下定论 |
| "审稿人会提什么意见" / "盲审会挂吗" / "答辩委员可能追问什么" | `/paper-review` | 期刊审稿 / 学位论文盲审 / 答辩委员三视角模拟意见 + 分项评分（是模拟常见维度，不是「值得发表」判断）。会先问稿件来源——**你以评审人身份持有的他人在审稿件会被直接拒绝** |
| "这些审稿意见怎么回" / "逐点回复怎么写" / "改稿建议" | `/paper-revise` | 修订建议对照表 + 逐点回复信初稿；每条标 ❓ 待你决定采纳与否 |

### 阶段 E · 发表与发表后

| 你会这么问 | 落到 | 你会拿到 |
| --- | --- | --- |
| "要交一份 AI 使用说明" / "列一下我到底用了哪些 AI" | `/paper-disclose` | 按四级辅助级别（构思讨论 / 大纲结构 / 成句生成 / 语言润色）汇编的披露说明，只读 `.paper/` 真实留痕、缺级标占位；可按导师 / 研究生院 / 期刊 / AIGC 检测四类读者切换 |
| "投稿要交什么材料" / "这个期刊要什么" / "cover letter 怎么写" | `/paper-submit` | 投稿材料 checklist + 该类期刊常见要求类目 + cover letter 要点骨架（不编影响因子、不替你选刊） |
| "投稿要 Word 版" / "帮我转成 LaTeX" / "参考文献要按国标渲染" | `/paper-typeset` | `.docx` / `.tex` / `.pdf` 产物 + 转换记录（只换容器不改一个字；缺 pandoc / xelatex 时给「未生成什么 + 原因 + 安装指引 + 可手工执行的命令」四件套，绝不伪造产物） |

### 这些问法会被拦下来——但每条都有替代出口

| 你可能会这么问 | 为什么不做 | 它会把你引到哪 |
| --- | --- | --- |
| "直接帮我写一篇关于 X 的论文" | 代写经不起答辩追问与诚信核查，署名责任始终在你 | → `/paper-topic` 起步，或 `/paper-outline` 搭完大纲用 `/paper-draft` 分段共写 |
| "帮我编几条参考文献凑数" / "帮我编一组数据" | 编造引用与数据是学术不端 | → 文献用 `/paper-search` 真检索；数据自行采集（阶段 B 归你） |
| "帮我降 AI 率" / "改到检测不出来" / "帮我查重降重" | 方向反了——本套件帮你如实披露，不帮隐藏 | → `/paper-disclose` 出 AI 使用说明；被误判走 `/paper-style` 出申诉特征；查重走学校 / 知网正规渠道 |
| "我这研究应该不用伦理审查吧" | 伦理审查须走机构 IRB，AI 不出豁免判断 | → `/paper-method` 给六项提示清单，报批走你所在机构的正规渠道 |
| "帮我评一下这份我在审的稿子" | 违反同行评审保密义务 | → `/paper-review` 只评你本人或你指导学生的稿件 |
| "哪个方向更值得做" / "哪篇最重要" / "给我的论文打个分" | 研究价值判断归你 | → 命令只陈列客观常见选项与线索，末尾以疑问句把判断交回你 |

### 串起来看：一个课题从头到尾会问些什么

```text
 1. "帮我建个课题目录"                              → /paper-init
 2. "我想研究短视频对青少年注意力的影响，说不清具体做什么" → /paper-topic   （你拍板 RQ）
 3. "有没有人研究过这个"                            → /paper-search  （文献笔记表）
 4. "这批文献怎么筛"                                → /paper-screen  （做系统综述才需要）
 5. "问卷能回答我的 RQ 吗？涉及未成年人要伦理审查吗"    → /paper-method
 6. "我要开题了"                                    → /paper-proposal
 ── 采数据、跑实验、做分析：AI 不进场，这一段是你自己的 ──
 7. "论文分几章好"                                  → /paper-outline
 8. "这段方法写不下去"                              → /paper-draft
 9. "RQ 和结论对得上吗"                             → /paper-logic
10. "帮我提炼摘要"                                  → /paper-abstract
11. "这些引用是真的吗 / 格式符合国标吗 / 结论说过头了吗" → /paper-verify（含 format / claim）
12. "审稿人会提什么意见"                            → /paper-review
13. "收到意见了，怎么逐条回"                         → /paper-revise
14. "要交 AI 使用说明" / "投稿要交什么" / "要 Word 版"  → /paper-disclose → /paper-submit → /paper-typeset
```

每一步都可以是一个新会话——`.paper/` 里的留痕负责把上下文续上，不必把整个课题压在一次对话里。

## 为什么可信

Paper-Tutor-Skills 把研究诚信的承诺落进了可验证的工程设计：

- **核验六态**：每条引用的核验结果是六种状态之一——VERIFIED（已核实）、METADATA_MISMATCH（元数据不符）、RETRACTED（已撤稿）、NOT_FOUND（未查到）、UNVERIFIED（未核验）、PENDING_MANUAL（待人工核对）。定位是**存在性核验**（存在 ≠ 引用恰当），以真实 API 响应为准，绝不凭模型记忆判断。

  > 量化门槛（虚构检出率、真实误报率、中文误伤等）目前不是发布门的必要条件，按需补跑并回填到 [`evals/`](evals/README.md)。但"以真实 API 响应为准、绝不凭模型记忆"是产品底线，不与任何目标权衡。
- **中英双轨检索**：英文文献接开放 API（arXiv、OpenAlex、Semantic Scholar、Crossref）自动检索；中文文献走"自动 + 引导"混合路径——带 DOI 的中文期刊文献自动命中，其余生成知网 / 万方检索方案（检索式 + 筛选条件）引导你执行并回填。**检索产出声明各来源覆盖方式**（自动 / 回填 / 未覆盖）——缺了这个提示，你可能把"英文库没有"误判成"没人研究过"。中文文献 API 覆盖不到的绝不判为编造，而是落 PENDING_MANUAL 态并附人工核对包。
- **跨宿主不锁死**：实现不依赖任何宿主专有机制，编排与断点续跑用纯文件约定。目录约定是增强不是依赖——检测到标准目录则产物归位，否则落当前目录并提示。

## 仓库结构

四区：`skills/`（skill 包 + `_shared/` 共享层，[开发规范](skills/README.md)）、`tests/`（[行为验收与语料](tests/README.md)）、`evals/`（[裸模型 vs 带 skill 并排对比](evals/README.md)）、`docs/`（[产品 PRD](docs/prd/paper-tutor-skills-prd-v1.md) 与[学术论文全流程示例](docs/examples/学术论文全流程示例.md)）。其余设计文档（specs、实现计划、评审记录）为内部稿，不随仓库发布——**本 README 与 PRD 是对外公开信息的事实来源**。

## 贡献

想参与开发或二次定制，先读 [skills/README.md](skills/README.md) 的开发规范（skill 包标准结构、发布门、横切要求）与 [CONTRIBUTING.md](CONTRIBUTING.md)。发布门是三条：核心确定性逻辑有单测且通过、至少一条真实输入手工走通、`commands.yaml` 的 `status` 同步翻转；量化门槛、行为验收多场景、裸模型对比不是必要条件，按需补。

## 许可

本项目采用 **PolyForm Noncommercial License 1.0**——源码完全开放，允许个人学习、研究、教学、非商业分发与改造，**但禁止任何商业使用**（包括但不限于销售、打包进收费产品、商业服务集成）。许可全文见仓库根目录的 [LICENSE](LICENSE) 文件，或 [PolyForm 官网](https://polyformproject.org/licenses/noncommercial/1.0.0/)。
