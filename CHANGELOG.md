# 变更日志（CHANGELOG）

本项目所有面向用户的显著变更会记录在本文件中。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/)。各类别含义：

- **新增（Added）** — 新功能、新命令、新模块
- **变更（Changed）** — 对既有功能的调整
- **修复（Fixed）** — Bug 修复
- **重构（Refactored）** — 不改变外部行为的内部改进

> 提交级细节见 `git log`；本文件只记录面向使用者/开发者的**显著**变更，
> 细碎的提交不逐条收录。

---

## [0.1.1] — 2026-07-28

**分发与安装体验版本。** 命令与 skill 内容不变（仍是 25 个命令入口 / 23 个 skill 目录），
本版补齐「怎么装进宿主」：Claude Code 与 Codex 各自可一键装插件，散装安装改为逐宿主给出
写死目标路径的提示词。已知边界与 v0.1.0 相同，见下方 [v0.1.0 已知边界](#v010-已知边界)。

### 新增（Added）

- **Claude Code 插件分发**——仓库根 `.claude-plugin/`（`plugin.json` + `marketplace.json`）
  使仓库自身成为插件市场：`/plugin marketplace add cabbage2000-lab/paper-tutor-skills` 后
  安装，25 个命令以 `paper-tutor:` 前缀成组显示。这是增量增强——散装 `skills/` 主体原样
  保留，Codex / WorkBuddy 等宿主的装载方式完全不受影响。
- **Release 自动化**——推 `v*` tag 触发 [`release.yml`](.github/workflows/release.yml)：
  跑测试 → 用 `scripts/extract_changelog_notes.py` 摘取本文件对应版本段 → 创建或更新
  GitHub Release。Release notes 自此由本文件推导，不手工抄第二份；对应版本段缺失会让
  发布直接失败，宁可不发也不发空白 Release。
- **Codex 插件分发**——新增 `.codex-plugin/plugin.json` 与 `.agents/plugins/marketplace.json`，
  Codex 用户可 `codex plugin marketplace add cabbage2000-lab/paper-tutor-skills` 后
  `codex plugin add paper-tutor@paper-tutor-marketplace` 一键安装，23 个 skill 全部加载
  （命令不带 plugin 名前缀，直接是 `/paper-init`）。两套清单格式实打实不同、不能合并：
  Codex 的 plugin.json 多要 `skills` 指针与一整块 `interface`，marketplace 条目的
  `source` 是对象且必带 `policy`。
- **plugin 清单守卫** [`tests/test_plugin_manifest.py`](tests/test_plugin_manifest.py)
  （35 项）——锁住两宿主四份清单 ↔ 本文件的版本号与描述处处一致，校验 Codex 的 `skills`
  指针与 `interface` 必填字段符合官方摄取口径，并校验两个 `.*-plugin/` 只放清单文件
  （skill 内容塞进去会导致一个都加载不到）。

### 修复（Fixed）

- **两个 README 给 Codex 用户的安装路径是错的**——原文让「其他宿主」把 skills 装到
  `~/.claude/skills/` 或 `.claude/skills/`，而 Codex 根本不读这两个目录，照做的结果是
  一个 `/paper-*` 命令都不出现，且没有任何报错提示。现改为逐宿主给出写死目标路径的
  安装提示词（Codex 用 `~/.codex/skills/`，Claude Code 用 `~/.claude/skills/`），
  让用户不必自己判断该装哪儿。

### 变更（Changed）

- **两个 README 的安装章节改为「复制提示词交给智能体」**——按宿主各给一段可直接粘贴的
  提示词，目标路径写死在提示词里，用户不用敲任何命令、也不用自己挑目录。提示词同时约束
  智能体：同名目录覆盖即更新、其他来源的 skill 一个都别动（不清空目录）、`_shared/`
  必须一起装。插件式一键安装退为次级小节，并提醒两条路别都走（会装出两份、命令重复）。
- CLAUDE.md 补「插件分发」「发版」两节（含 Codex 的 `_shared` 预检报错说明：官方
  `validate_plugin.py` 会因它缺 SKILL.md 报错，但运行时摄取与加载都静默忽略，**不要**
  为讨好预检脚本给 `_shared` 改名），结构守卫测试表由三个更新为四个。
- 移除 `docs/examples/phase2-plugin-样板/`——其 `.template` 文件已被 `.claude-plugin/`
  的实际配置取代，留着即第二份真相。

---

## [0.1.0] — 2026-07-27

**首个版本。** Paper-Tutor-Skills 是一套面向中文学术写作的 AI 辅导 skill 套件，基于通用
agent skills 标准（SKILL.md + `references/`）。核心分工：**AI 负责效率（检索、整理、核对、
结构化），人负责研究决策（想法、判断、数据、结论）**。

本版把学术研究「5 阶段 23 环节」生命周期一次性收口，25 个命令入口全部发布。

### 本版规模

- **23 个 skill 目录 / 25 个命令入口**——`paper-format`、`paper-claim` 内建于 `paper-verify`，
  按设计无独立目录
- **6 个 skill 带确定性内核 `scripts/`**（verify / search / doctor / screen / style / typeset），
  其余为纯提示词层
- **529 条 pytest 全绿**（1.6 秒），CI 在 push / PR 上跑同一条命令
- 命令主清单 [`skills/_shared/commands.yaml`](skills/_shared/commands.yaml) 是命令集的单一
  事实来源，各命令的已知观察项以它为准

### 新增（Added）

#### 跨阶段基础设施（4）

| 命令 | 能力 |
| --- | --- |
| `/paper-init` | 科研工作目录脚手架——一轮提问建标准目录骨架 + 项目信息配置（长期记忆） |
| `/paper-help` | 命令导航器——双轴（研究阶段 / 学习意图）帮你找到当下该用哪个命令 |
| `/paper-doctor` | 环境就绪度体检——核验 / 检索环境能不能用、缺什么、怎么补，四态汇总 |
| `/paper-daily` | 每日学术雷达——抢发检测（全源对照）+ 新发泛读（arXiv 自动轨 + 用户多源补充轨） |

#### 阶段 A · 选题与立项（5）

| 命令 | 能力 |
| --- | --- |
| `/paper-topic` | 选题导航器——逐层给该方向客观常见的选项（不推荐不排序），用户拍板聚焦成 RQ |
| `/paper-search` | 中英双轨文献检索与综述辅助——真实 API 检索，不排序、不判研究价值 |
| `/paper-screen` | 系统综述筛选——PRISMA 2020 两轮筛选台账 + 计数守恒校验 + 流程图 + 数据提取表骨架 |
| `/paper-method` | 研究设计参谋——方法-RQ 匹配检查 / 方法类引导双模式 + 涉人类被试强制伦理提示清单 |
| `/paper-proposal` | 开题报告组装——多源汇聚（RQ + 文献笔记 + 研究设计）按中文学位论文制度节点摆骨架 |

#### 阶段 C · 成文（8）

| 命令 | 能力 |
| --- | --- |
| `/paper-outline` | 论文大纲——基于 RQ 与文献笔记产出带文献锚点的章节大纲草案 |
| `/paper-draft` | 分段正文共写——基于大纲与文献笔记逐段起草正文初稿 |
| `/paper-style` | 风格校准——六组特征脚本机械算出，全文一致性 + 个人风格基线 + AIGC 误判申诉 |
| `/paper-logic` | 论证链检查——RQ → 方法 → 结果 → 结论四者结构对应，只核结构不核内容真伪 |
| `/paper-abstract` | 摘要提炼——从已完成正文提炼摘要初稿，每句可追溯回正文出处 |
| `/paper-import` | 题录导入——知网 / Zotero / EndNote 题录批量入笔记表 + 题录-草稿一致性核对 |
| `/paper-figure` | 图表可视化辅助——诊断模式（5 维度陈列）+ 设计建议模式（图类 / 图注 / 配色 / 坐标轴 / 工具） |
| `/paper-plot` | 绘图代码生成（内建于 figure，可独立调用）——matplotlib / ggplot2 × 7 类图 |

#### 阶段 D · 评审与修订（5）

| 命令 | 能力 |
| --- | --- |
| `/paper-verify` | 引用存在性核验——六态判定（已核实 / 元数据不符 / 已撤稿 / 未找到 / 无法核实 / 待人工核对） |
| `/paper-format` | GB/T 7714-2015 著录格式检查（纯规则，内建于 verify） |
| `/paper-claim` | 结论夸大检查——核对结论是否超出结果支撑（内建于 verify） |
| `/paper-review` | 模拟评审——期刊审稿 / 学位论文盲审 / 答辩委员三视角 + 分项评分；不接收他人在审稿件 |
| `/paper-revise` | 修订辅助——修订建议对照表 + 逐点回复信初稿，采纳与否由用户逐条决定 |

#### 阶段 E · 发表与发表后（3）

| 命令 | 能力 |
| --- | --- |
| `/paper-disclose` | AI 使用说明生成——扫 `.paper/` 留痕按四级辅助级别汇编，四类读者标签轴 |
| `/paper-submit` | 投稿准备——材料 checklist + 目标期刊常见要求陈列 + cover letter 要点骨架 |
| `/paper-typeset` | 出版链——Markdown → LaTeX / DOCX / PDF 转换 + GB/T 7714-2015 国标著录（官方 CSL 两制式） |

> **没有阶段 B（数据分析）是产品立场，不是遗漏。** 数据与分析结论必须出自研究者本人，
> 详见下文「贯穿全套件的底线」与 [`边界拒绝清单.md`](skills/_shared/references/边界拒绝清单.md)。

#### 共享层 `skills/_shared/`

- **文献数据源层 `paper_shared/datasources/`**——7 层结构：数据契约 / 9 源注册表 / HTTP
  （节流 + 指数退避 + 错误分类）/ sqlite3 本地缓存 / DOI 注册机构判别路由 / 6 个数据源客户端
  （Crossref、OpenAlex、Semantic Scholar、arXiv、PubMed、ERIC）/ 批处理引擎与健康探测；
  统一门面 `lookup` / `fetch_batch` / `search` / `probe_all`。
- **跨 skill 共享约定 + 一致性守卫**——[四层内容标注](skills/_shared/references/四层内容标注.md)
  （👤 用户原话 / 📋 常见事实 / 🪞 系统归纳 / ❓ 待用户决定）、
  [学科三梯队](skills/_shared/references/学科三梯队.md)（实证 / 理论 / 诠释，梯队是现实描述而非
  价值排序）、[留痕契约](skills/_shared/references/留痕契约.md)（16 个生产者 / 2 个消费者的字段
  一致性）。三份约定各有 pytest 守卫锁住，防无声漂移。
- **[边界拒绝清单](skills/_shared/references/边界拒绝清单.md)**——拒绝决策的可审查记录：
  四问审查判据（归属 / 可溯 / 可见 / 责任）+ A 类产品边界 8 条（每条配出口指引）+ B 类评估过
  并拒绝的机制 4 条（每条配替代方案）。新功能提案先过一遍这把尺子。清单与 README、PRD 三处
  由 [`tests/test_boundary_registry.py`](tests/test_boundary_registry.py) 双向锁住。
- **报告设计层**——`tailwind.config.js`（四层语义色 + 字体 + typography token）+
  `echarts-theme.js` + [报告组件库](skills/_shared/references/报告组件库.md) +
  `scripts/check_templates.py`（9 项结构校验）。13 个 skill 的 HTML 报告模板共用这一层。
- **工具链探测 `paper_shared/toolchain.py`**——pandoc / xelatex / 中文字体的存在性探测，
  供 typeset 输出「未生成什么 · 原因 · 安装指引 · 可手工执行的完整命令」四件套。

### 贯穿全套件的底线

- **不编造**——事实性断言必须可追溯到真实来源。核验类命令 API 失败时明确标注降级
  （「未核验」「待人工核对」），**不静默用模型记忆顶替**；绘图不编看似真实的研究数据；
  文献笔记不凭记忆补全字段。
- **不替用户做研究决策**——选题不推荐不排序、筛选不替判纳排、修订不替决定采纳、
  评审评分是模拟视角陈列而非 AI 的价值判断。产物中禁用「建议纳入 / 排除」这类措辞，
  待定处一律标 ❓ 交回用户。
- **留痕如实**——每次 AI 参与按四级辅助级别（构思讨论 / 大纲结构 / 成句生成 / 语言润色）
  写进 `.paper/`，可隐去某条但顶部强制覆盖声明，**不抹除痕迹**；`/paper-disclose` 汇编成
  可对外披露的 AI 使用说明。

### v0.1.0 已知边界

本版为首发版本，三项全局缺口如实登记：

- **跨宿主验证未做**——主清单 19 处条目标注「第二宿主待跑」。项目定位第一句是「不绑定单一
  宿主」，但实际只在 Claude Code 上跑过。唯一例外是 `paper-search`：其「不排序」红线在 Codex
  侧验证通过，反倒是 Claude Code 侧有 2 次稳定偏离（已登记在主清单条目注释里）。
- **行为验收多数靠人工模拟脚本**——主清单 14 处标注「无 pytest」。529 条自动化测试覆盖的是
  确定性内核（解析、计算、渲染）与跨 skill 约定守卫；LLM 行为层靠人工跑模拟脚本验收。
- **无真实用户与产出样例**——全部命令未经真实论文流程端到端检验。
