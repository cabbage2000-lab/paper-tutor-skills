# Skill 包开发规范

`skills/` 是完整分发单元，必须成套安装。公开入口以 [`_shared/commands.yaml`](_shared/commands.yaml) 为唯一清单，最多 5 个；内部能力与状态以 [`_shared/workflows.yaml`](_shared/workflows.yaml) 为唯一清单。

## 目录与发现

只有公开入口目录含 `SKILL.md`，frontmatter 的 name、slug 与目录名一致。原能力目录保留 `WORKFLOW.md`、scripts/、references/ 和 assets/；`WORKFLOW.md` 不带技能 frontmatter，不作为公开命令发现。共享资源放 `_shared/`。保留原目录是为了稳定脚本路径、相对导入和模板引用。

入口按意图渐进加载内部流程，不把完整内部能力列表展示成另一个选择菜单。所有行为遵守[入口路由约定](_shared/references/入口路由约定.md)。新增能力优先纳入已有入口，登记 entry、request_zh、workflow、status，不新增第六个入口。

## 发布与验证

内部能力通过确定性测试与实际输入验收后，才将 workflows.yaml 的 status 改为 released。入口发布状态与内部能力状态分别维护，不因入口可用而把开发中能力当作已发布。结构与覆盖守卫见 `tests/test_manifest_consistency.py`；安装升级守卫见 `tests/test_install_skills.py`。

执行 `python3 -m pytest tests/ -q --ignore=tests/datasources/smoke_real_api.py`；本机若 pytest-asyncio 与 pytest 冲突，加 `-p no:asyncio`。结构检查运行 `python3 scripts/validate_commands.py`。确定性工具仍为 Python 标准库实现，pytest / pyyaml 仅测试时使用。

## 共享约定

- [四层内容标注](_shared/references/四层内容标注.md)与[学科三梯队](_shared/references/学科三梯队.md)保持原语义。
- [留痕契约](_shared/references/留痕契约.md)的内部能力 ID 不变，历史记录不重写。
- [报告组件库](_shared/references/报告组件库.md)与[边界拒绝清单](_shared/references/边界拒绝清单.md)继续适用。
- 核验依赖真实证据，失败显式降级；产物与用户决定如实留痕。
- 提问工具是可选增强，必须保留纯文本路径。

只安装五个入口目录会缺依赖；安装与升级使用仓库的 `scripts/install_skills.py`，不要用覆盖复制保留旧入口。
