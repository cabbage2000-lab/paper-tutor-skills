# Phase 2 plugin 打包样板（备用，当前不启用）

| 项 | 内容 |
| --- | --- |
| 类型 | 配置模板 + 启用指南（备用件） |
| 状态 | **未启用**——Phase 1 维持散装平铺，本目录仅为 Phase 2 预备 |
| 日期 | 2026-07-23 |
| 上游 | 仓库结构 ADR·§6 skill 分发形态（内部决策记录，自用期精简时已删） |

## 这是什么

一套把 Paper-Tutor-Skills 整体打包成**一个 Claude Code plugin** 的配置样板，让 17 个 `/paper-*` 命令在 Claude Code 里以 `paper-tutor:<命令>` 统一前缀**成组显示**，而不是散装平铺。

**为什么放在 `docs/examples/` 而不是仓库根**：本目录不在任何宿主的扫描路径里，放这里零误激活风险，符合项目"确认前零创建实体、只留规范/模板"的哲学（呼应 paper-init spec·5.4 的"只建骨架不预建产物"红线）。要启用时，按下方步骤把 `.template` 文件拷到目标位置即可。

**为什么现在不启用**：见 ADR §6.4——Phase 1 只发 4 个命令，散装列表不冗长；散装形态跨宿主验收最简单。plugin 成组是 Phase 2+ 的**可选增量增强**，不是替换，也不改变散装主体。

## 前提条件（启用前必须全部满足）

1. 目标批次的 skill 已定稿、发布门全部通过（[skills/README·发布门](../../../skills/README.md)）；
2. 已确认接受"仅 Claude Code 一侧成组、其他宿主仍散装"——plugin 清单是 Claude Code 专有增强层，不承诺跨宿主一致的分组视觉（ADR §6.3）；
3. 已就下方「命名权衡」做出选择。

## 目录里有什么

```text
phase2-plugin-样板/
├── README.md                   # 本文件：启用指南
├── plugin.json.template        # plugin manifest 样板（走任一路径都需要）
└── marketplace.json.template   # 仅走 marketplace 分发路径时需要
```

## 两条官方启用路径（Phase 2 二选一）

> 官方依据：[plugins](https://code.claude.com/docs/en/plugins.md)、[plugins-reference](https://code.claude.com/docs/en/plugins-reference.md)（URL 于 2026-07-23 核实）。

### 路径 A：`skills-dir` 自动加载（最省事，适合自用 / 小范围）

把带 `.claude-plugin/plugin.json` 的 plugin 目录放进 `~/.claude/skills/`，Claude Code 下次会话即以 `paper-tutor@skills-dir` 自动加载，无需 marketplace、无需安装步骤。

```bash
# 方式一：官方脚手架直接生成骨架，再把本仓库 skills/ 内容放进去
claude plugin init paper-tutor        # 生成 ~/.claude/skills/paper-tutor/{.claude-plugin/plugin.json, SKILL.md}
# 然后用本仓库 skills/ 覆盖生成的 skills/，并用 plugin.json.template 覆盖 plugin.json

# 方式二：手工组装
mkdir -p ~/.claude/skills/paper-tutor/.claude-plugin
cp plugin.json.template ~/.claude/skills/paper-tutor/.claude-plugin/plugin.json
cp -R ../../../skills/ ~/.claude/skills/paper-tutor/skills/   # skill 主体
# 注意：_shared/ 会随 skills/ 一起复制；plugin 根的 skills/ 下每个子目录须含 SKILL.md
```

### 路径 B：marketplace 分发（适合团队 / 社区分发、要版本管理）

让**仓库自身**成为一个 marketplace，用户 `add` 仓库后即可 `install`。

```bash
# 1. 在仓库根建 plugin manifest（仓库根 = plugin 根，现有 skills/ 位置天然吻合）
mkdir -p .claude-plugin
cp docs/examples/phase2-plugin-样板/plugin.json.template .claude-plugin/plugin.json

# 2. 在仓库根建 marketplace manifest
cp docs/examples/phase2-plugin-样板/marketplace.json.template .claude-plugin/marketplace.json
#    （plugin.json 与 marketplace.json 同放 .claude-plugin/；见下方“常见坑”）

# 3. 用户侧安装
#    /plugin marketplace add <你的仓库 git 地址>
#    /plugin install paper-tutor@<marketplace 名>
```

## 命名权衡（启用前必须定）

plugin 的 `name` 字段既是 marketplace 里的标识，也是**所有 skill 的命名空间前缀**。它与现有 skill 目录名组合后决定最终命令名：

| plugin `name` | 现有 skill `paper-init` 的最终命令 | 评价 |
| --- | --- | --- |
| `paper-tutor` | `/paper-tutor:paper-init` | 前缀与命令都带 `paper`，**重复啰嗦** |
| `paper` | `/paper:init`、`/paper:verify` | 简洁、语义顺——但需先把 skill 目录名从 `paper-init` 改为 `init`（牵动 [skills/README·目录约定](../../../skills/README.md) 的"目录名 = 命令名"规约与 paper-init 命令发布映射表） |

`plugin.json.template` 里默认填 `paper-tutor`（不改现有 skill 名、改动最小），但如果 Phase 2 决定追求简洁的 `paper:init`，需配套一次 skill 改名，届时应在 ADR 追加决策、同步 [skills/README](../../../skills/README.md) 与 paper-init 的命令发布映射表。**此权衡现在只记录，不预先决定。**

## 常见坑（官方明确警告）

- `.claude-plugin/` 目录里**只放** `plugin.json`（marketplace 场景再加 `marketplace.json`）；`skills/`、`commands/`、`agents/`、`hooks/` 等**必须在 plugin 根**，绝不能塞进 `.claude-plugin/` 内。
- plugin 根就是含 `.claude-plugin/plugin.json` 的那个目录（marketplace 路径下 = 仓库根），**永远不是 `~/.claude/`**。
- 一个 plugin 若只含单个 skill，可把 `SKILL.md` 直接放 plugin 根；含多个 skill（本套件的情况）则用 `skills/` 布局——本仓库现有 `skills/` 正是这个布局，仓库根成为 plugin 根时无需搬动 skill。
- 改动 `plugin.json` 后在会话内用 `/reload-plugins` 生效，无需重启。

## 与散装形态的关系

启用本样板是**增量增强，不删任何东西**：`skills/` 散装主体原样保留，其他宿主（Codex / WorkBuddy 等）继续按 SKILL.md 开放标准散装装载，完全不受影响。ADR §6.3 的跨宿主中立性论证以此为前提。
