# paper-help 全貌视图 · 模拟验收清单

> 设计文档与实施计划：`docs/plans/2026-07-26-paper-help-overview-{design,impl}.md`（内部过程稿，不随仓库发布）
> 行为层不写 pytest 验收（CLAUDE.md·开发流程：单测只覆盖核心确定性逻辑）；靠 4 档模拟场景人工眼看。
> 与 paper-topic / outline / disclose 同款做法。

## 怎么跑

把对应 fixture 复制到临时目录的 `.paper/` 下、在该目录里向宿主 agent 说 `/paper-help` → 选 9，眼看输出。

### 场景 1：部分跑过（主用例）

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp"
cp -r tests/paper-help/fixtures/.paper "$tmp/.paper"
cd "$tmp"
# 向宿主 agent 说：/paper-help → 选 9（看我的研究全貌）
```

**期望**：
- 顶部摘要：`共扫到 4 条 · 覆盖 1 / 5 个研究阶段`
- 阶段 A：🟡 yellow `2/4`（topic + search 跑过、search 两次去重为 1；method/proposal 未跑）
- 阶段 B：固定文案"研究者本人负责"
- 阶段 C：🔴 red `0/7`（全部未跑）
- 阶段 D：🔴 red `0/5`
- 阶段 E：🔴 red `0/2`
- infra 区：✅ init、⬜ daily
- 下一步弱导航：取前 2 条候选（method / proposal，按 commands.yaml 顺序）
- 不出现任何"建议你做""完成度高/低"等价值判断词

### 场景 2：空 `.paper/`

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/.paper"
cp tests/paper-help/fixtures/.paper/empty.md "$tmp/.paper/usage-trace.md"
cd "$tmp"
# /paper-help → 选 9
```

**期望**：让路提示"`.paper/` 存在但没有可识别的使用记录"、让路到 `/paper-topic` 等命令起步。**不裸编任何进度**。

### 场景 3：扫不到 `.paper/`

```bash
tmp=$(mktemp -d)
cd "$tmp"
# /paper-help → 选 9
```

**期望**：让路提示"当前目录没有 `.paper/` 留痕"、建议先用 `/paper-init` + `/paper-topic` 起步。**不裸编任何进度**。

### 场景 4：全跑过

手造一份 `.paper/` fixture，包含所有已发布命令各一条留痕（A 阶段 4 条、C 阶段 7 条、D 阶段 5 条、E 阶段 2 条、infra 区 init + daily 2 条），跑 `/paper-help → 选 9`。

**期望**：
- 所有阶段徽章 🟢 green（A: 4/4, C: 7/7, D: 5/5, E: 2/2）
- 下一步弱导航：候选池空（无未跑命令）→ 提示"所有已发布命令都有留痕、研究主权进度判断交回你"
- **仍不下"完成度高/全部完成"结论**

## 人工验收清单（4 档跑完逐项打勾）

- [ ] 场景 1：徽章 / 描述 / 去重计数 / 下一步指引全对
- [ ] 场景 2：空 `.paper/` 让路、不裸编
- [ ] 场景 3：无 `.paper/` 让路、不裸编
- [ ] 场景 4：全跑过徽章全绿、不下价值结论
- [ ] 所有场景：四块结构齐全（顶部摘要 / 阶段进度表 / infra 区 / 下一步弱导航）
- [ ] 所有场景：停点原文出现、不替用户执行被推荐命令
