---
name: paper-check
description: 学术辅导的检查与修订入口。用于引用真实性与参考文献格式核验、结论与论证链检查、模拟审稿或答辩、处理审稿意见和起草逐点回复；核验依赖真实证据，采纳与研究判断由用户决定。
slug: paper-check
displayName: 学术辅导·检查与修订
version: 0.2.0
summary: 学术辅导套件的五个入口之一；需整套安装 skills/，包含内部流程与 _shared 共享层。
---

# 检查与修订

先读[入口路由约定](../_shared/references/入口路由约定.md)，再按用户意图读取下面**一个相关流程**，直接承接用户已经提供的材料和要求。表中是内部选择依据，不是让用户逐项选择的菜单；明确意图不再问“要用哪个命令”。

覆盖：检查与修订。数据采集、实验与原创研究判断仍由研究者负责。其他阶段按[公开清单](../_shared/commands.yaml)转入对应入口。

| 用户想做什么 | 内部流程 |
| --- | --- |
| 引用核验 | [verify](../paper-verify/WORKFLOW.md) |
| 参考文献格式；只进入格式分支 | [format](../paper-verify/WORKFLOW.md) |
| 结论检查；只进入结论分支 | [claim](../paper-verify/WORKFLOW.md) |
| 论证检查 | [logic](../paper-logic/WORKFLOW.md) |
| 模拟评审 | [review](../paper-review/WORKFLOW.md) |
| 修订回复 | [revise](../paper-revise/WORKFLOW.md) |

“投稿前检查一下”但未指定维度时，结合材料提出一个最小检查范围供用户确认；不默认把六种检查全跑一遍。格式检查不触发在线引用核验，模拟评审保留稿件来源检查，修订回复保留逐条采纳决定。
