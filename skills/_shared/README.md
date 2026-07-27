# `_shared/`：跨 skill 共享层

| 项 | 内容 |
| --- | --- |
| 类型 | 共享层准入约定（活文档） |
| 日期 | 2026-07-22 |
| 上游 | 仓库结构 ADR·4.2（2026-07-22 的内部决策记录，未随仓库发布） |

**这不是一个 skill 包**——本目录永不放置 SKILL.md，宿主按 SKILL.md 发现 skill 时自然跳过；下划线前缀即此标记。

## 准入规则

- **至少两个 skill 使用**的资源才进入本目录；单 skill 专用的留在该 skill 自己的 `scripts/` 或 `references/`；
- 每项资源入驻时在下表登记（防止本目录长成杂物抽屉）。

## 计划内容（随各 skill 开发落地）

| 资源 | 服务对象 | 出处 |
| --- | --- | --- |
| 文献 API 客户端（arXiv、OpenAlex、Semantic Scholar、Crossref；按学科补 PubMed、ERIC），含 DOI 注册机构判别路由——`doi.org/ra/` 免费端点分流 Crossref / DataCite / ISTIC，ISTIC（中文 DOI）条目径直落待人工核对 | `/paper-verify`、`/paper-search` | [PRD·文献数据源](../../docs/prd/paper-tutor-skills-prd-v1.md) |
| 数据源注册表：已接入各源的名称、端点、限流参数、覆盖声明，声明式统一维护；核验报告的"已查源清单"由此生成 | `/paper-verify`、`/paper-search` | PRD·文献数据源·配套机制 |
| 工程约束实现：本地结果缓存（同一 DOI 不重复查）、分批 + 指数退避、断点续验、剩余时间预估 | 同上 | PRD·引用核验策略（API 限流是核心设计约束，非附录） |
| 留痕写入器：`.paper/` 四级使用记录 + 产物人机分工页脚 | 全体 skill | PRD·披露与留痕 |
| 命令主清单 `commands.yaml`：全部 paper 命令的名称 / 阶段 / 定位 / 落盘目录 / 发布状态 / 使用指引，声明式统一维护 | `paper-help`、`paper-init` | 本仓库·paper-help spec |
| 外部工具链探测 [`paper_shared/toolchain.py`](paper_shared/toolchain.py)：pandoc / xelatex / 中文字体族名探测 + 三平台安装指引。两边各写一份必然漂移——doctor 说 pandoc 可用、typeset 说不可用，用户无从判断哪个对 | `paper-typeset`（转换前探测）、`paper-doctor`（体检项） | 本仓库·系统综述与风格校准与出版链三块补齐设计 §7.2 / §7.5 |
| 边界拒绝清单：A 类产品边界 8 条 + B 类拒绝的机制 4 条，每条带审查判据、依据、出口指引与同步锚点；新功能提案的评审准绳 | 全体 skill | [PRD·边界即产品](../../docs/prd/paper-tutor-skills-prd-v1.md) |

## 技术栈

**已决（2026-07-22）**：Python 3 标准库、零第三方运行时依赖，最低版本 3.9，测试框架 unittest——决策依据与展开见「数据源模块设计 spec·第 2 节」（内部稿，未随仓库发布），ADR·4.4 所留决策就此定案。本目录唯一 Python 包根为 `paper_shared/`，skill 脚本以标准三行头引导 import（见该 spec·4.2）。

## 分发注意

`skills/` 整目录是分发单元，本目录随行；skill 从自身 SKILL.md 以相对路径（`../_shared/...`）引用本目录资源。单 skill 独立分发时的打包问题（将本目录内联进目标 skill）显式延后至 Phase 2（ADR·遗留问题 3）。
