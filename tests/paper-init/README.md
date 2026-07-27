# paper-init 脚手架行为验收清单

| 项 | 内容 |
| --- | --- |
| 类型 | 行为验收清单（人工执行，paper-init 发布门） |
| 日期 | 2026-07-22（初版）· 2026-07-23（v2 增强：项目信息配置 + 宿主文件生成）· 2026-07-23（v3 增强：提问优先结构化选择） |
| 上游 | paper-init spec·测试要点 · [tests/README·脚手架行为](../README.md) |

**原则：验证外部可观察行为（文件系统结果 + 对话可见输出），不测实现细节。** 全部核查命令只读、可直接复制执行。技术栈落定（paper-verify spec）后，本清单的核查命令可平移为脚本置于本目录，清单语义不变。

## 前置准备

1. 安装 skill 到宿主（软链或复制 `skills/` 下条目进宿主 skills 目录，见仓库 README·安装）；
2. 建沙盒根，每个场景一个独立子目录：

   ```bash
   SANDBOX=/tmp/paper-accept && mkdir -p $SANDBOX/{s1a,s1b,s2,s2b,s3,s4,s5a,s5b,s5c,s5d,s6}
   ```

3. 每个场景开跑前做快照：`find $SANDBOX/<场景> | sort > /tmp/before-<场景>.txt`。

## 场景一：空位置 · 单项目 · 要 git

触发语（用贯穿案例，保证验收任务与语料同源）：

> 用 paper-init 建科研工作目录：项目名「ChatGPT 是否提高大学生论文写作效率」，单项目，建在 `<沙盒场景目录>`，要 git。用户身份研究生，学科计算机科学，当前文献调研阶段，引用格式 APA，简中优先；宿主选 Claude Code。

### 1a 中断跑——确认前零创建（红线）

**步骤**：会话走到方案呈现停点（`⏸ 等待确认：工作目录方案……`）后直接结束会话，不回复"确认"。

**核查**：

```bash
find $SANDBOX/s1a | sort > /tmp/after-s1a.txt && diff /tmp/before-s1a.txt /tmp/after-s1a.txt
```

- [ ] diff 无任何输出（文件系统零变化）；
- [ ] 停点消息本身完整呈现了：最终形态预览树（含 `.paper/` 与未来产物、逐项注明"本次不建"）、本次创建清单、关键选择及理由。

### 1b 完整跑——只建骨架

**步骤**：同一触发语重跑，在停点回复「确认」，等 skill 报告完成。

**核查**（`P=$SANDBOX/s1b/<项目目录>`）：

```bash
ls -A "$P"                                                  # 七目录 + README.md + .gitignore + project.paper.yaml + CLAUDE.md + .git
find "$P" -not -path "*/.git/*" -not -name .git -type f     # 恰四个文件：README.md、.gitignore、project.paper.yaml、CLAUDE.md
find "$P" -name ".paper*"                                     # 必须为空
git -C "$P" log --oneline                                   # 恰 1 条：init: 科研工作目录（paper-init 创建）
git -C "$P" status --porcelain                              # 必须为空（新建文件全部已提交）
grep -c '[<>]' "$P/README.md"                               # 必须为 0（无残留尖括号）
grep -c '[<>]' "$P/project.paper.yaml"                        # 必须为 0（无残留尖括号）
grep -c '[<>]' "$P/CLAUDE.md"                               # 必须为 0（无残留尖括号）
grep -E '^\.paper|^data/?$|^project\.paper\.yaml$' "$P/.gitignore"   # 必须为空（.paper/ data/ project.paper.yaml 不得被忽略）
grep 'literature/pdfs/' "$P/.gitignore"                     # 必须命中
grep 'created_by: "paper-init"' "$P/project.paper.yaml"         # 必须命中
grep 'project_name:' "$P/project.paper.yaml"                  # 必须命中且值为项目名
grep '计算机科学' "$P/project.paper.yaml"                      # 必须命中（用户回答落盘）
grep '计算机科学' "$P/CLAUDE.md"                             # 必须命中（宿主文件派生自配置）
```

- [ ] 七个顶层目录齐备：topic/ literature/ data/ analysis/ manuscript/ review/ submission/；
- [ ] 除 `.git/` 外恰好四个文件（README.md、.gitignore、project.paper.yaml、CLAUDE.md）——无任何 skill 产物文件、无 `.paper/`（红线）；
- [ ] git 恰一条提交，提交信息为 `init: 科研工作目录（paper-init 创建）`；
- [ ] README 无残留尖括号、日期为当天真实日期；
- [ ] README 写入者列只含已发布命令——当前无任何已发布命令，应全为「（后续版本）」「你——AI 不……」「各 skill 会话」；「下一步」不引导用户使用未发布命令；
- [ ] `.gitignore` 忽略 `literature/pdfs/`，且未忽略 `.paper/` 与 `data/` 与 `project.paper.yaml`；
- [ ] `project.paper.yaml` 存在、无残留尖括号、`created_by: "paper-init"`、字段值与用户回答一致（用户身份研究生、学科计算机科学、阶段文献调研、引用格式 apa、语言 zh-first）；
- [ ] `CLAUDE.md` 存在、无残留尖括号、派生自配置（含项目名与学科）；AGENTS.md 不存在。

## 场景二：目标目录已存在且非空——绝不覆盖

**预置**：

```bash
cd $SANDBOX/s2 && echo "我的旧笔记" > 旧笔记.md && printf "# 哨兵 README\n请勿改动此行\n" > README.md && md5 README.md 旧笔记.md > /tmp/sentinel-s2.txt
```

**步骤**：同场景一触发语（位置改 s2），走完确认与创建。

**核查**：

```bash
md5 $SANDBOX/s2/README.md $SANDBOX/s2/旧笔记.md | diff /tmp/sentinel-s2.txt -   # 逐字节不变
find $SANDBOX/s2 | sort | diff /tmp/before-s2.txt -                              # 只有 > 开头的新增行
```

- [ ] 方案呈现阶段列出了现有内容清单；
- [ ] 哨兵 README.md 与旧笔记.md 逐字节不变（README 已存在 → 保留不动，仅提示用户自行核对）；
- [ ] 快照 diff 只有新增行，无删除或改动行（只增不删）。

### 2b 已有 `.paper/`——进行中项目，就此打住

**预置**：`mkdir $SANDBOX/s2b/.paper && echo '{}' > $SANDBOX/s2b/.paper/usage.json`

**步骤**：对 s2b 触发 init。

**核查**：

- [ ] 对话中说明这是进行中的 Paper-Tutor-Skills 项目、建议直接用对应子命令续作，init 未再推进；
- [ ] `find $SANDBOX/s2b | sort | diff /tmp/before-s2b.txt -` 无输出（零新建）。

## 场景三：目标已处 git 仓库内——跳过 git init 并说明

**预置**：

```bash
cd $SANDBOX/s3 && git init -q && echo "外层仓库" > 外层说明.md && git add -A && git commit -qm "外层首提" && git log --oneline > /tmp/outer-log-s3.txt
```

**步骤**：项目建在 `$SANDBOX/s3/` 下（外层仓库内部），走完。

**核查**：

```bash
find $SANDBOX/s3 -name .git                                  # 仅外层一个（无嵌套仓库）
git -C $SANDBOX/s3 log --oneline | diff /tmp/outer-log-s3.txt -   # 外层无新增提交（不代提交）
git -C $SANDBOX/s3 status --porcelain                        # 新建文件应为未跟踪（??），未被暂存或提交
```

- [ ] 无嵌套 `.git`；
- [ ] 对话中解释了跳过原因（外层仓库会直接跟踪项目文件，再嵌一层反而让外层看不到内容）；
- [ ] 外层仓库历史与暂存区未被代动（新建文件保持未跟踪，收不收进外层仓库由用户决定）。

## 场景四：多项目工作区

**触发语**：

> 用 paper-init 建科研工作区：我多项目并行，工作区名用默认，先建第一个项目「ChatGPT 是否提高大学生论文写作效率」，位置 `$SANDBOX/s4`，要 git。

**核查**（`W=$SANDBOX/s4/科研工作区`）：

```bash
find "$W" -name .gitignore        # 全树恰一个，且在工作区根
grep 'literature/pdfs/' "$W/.gitignore"   # 应为 **/literature/pdfs/（作用于所有项目子目录）
find "$W" -name .git              # 仅工作区根一个
git -C "$W" log --oneline         # 恰 1 条
```

- [ ] 工作区 README 首段主语是工作区、含项目清单表；
- [ ] 项目子目录含七目录 + 标准版项目 README（无独立 .gitignore、无独立 .git）；
- [ ] 工作区 `.gitignore` 的 PDF 忽略行为 `**/literature/pdfs/`（不带 `**/` 时该规则管不到项目子目录）；
- [ ] README（两份）均无残留尖括号。

## 场景五：宿主配置文件生成（缺失才生成）

针对需求 2——最后一步检查用户选定宿主的配置文件，缺失才生成、已存在则保留不动（红线 3）。

### 5a 缺失才生成（Claude Code）

**触发语**：项目名「效率研究」，单项目，建在 `$SANDBOX/s5a`，要 git；宿主选 Claude Code（项目信息可留空）。

**核查**（`P=$SANDBOX/s5a/效率研究`）：

```bash
test -f "$P/CLAUDE.md" && echo "CLAUDE.md 存在"            # 必须命中
test ! -f "$P/AGENTS.md"                                   # 必须成功（AGENTS.md 不应存在）
grep -c '[<>]' "$P/CLAUDE.md"                              # 必须为 0
grep 'Paper-Tutor-Skills' "$P/CLAUDE.md"                                  # 必须命中（协作边界含 Paper-Tutor-Skills）
test -f "$P/project.paper.yaml"                              # 必须存在
```

- [ ] `CLAUDE.md` 生成、无残留尖括号、含项目名与 Paper-Tutor-Skills 协作边界；
- [ ] `AGENTS.md` 不存在（未选 Codex 不误建）。

### 5b 已存在则保留不动

**预置**：`printf "# 哨兵宿主文件\n请勿改动\n" > $SANDBOX/s5b/CLAUDE.md && md5 $SANDBOX/s5b/CLAUDE.md > /tmp/sentinel-s5b.txt`

**步骤**：项目建在 `$SANDBOX/s5b/`（外层放哨兵 CLAUDE.md），宿主选 Claude Code，走完流程。

**核查**：

```bash
md5 $SANDBOX/s5b/CLAUDE.md | diff /tmp/sentinel-s5b.txt -   # 逐字节不变（红线 3）
```

- [ ] 哨兵 CLAUDE.md 逐字节不变；
- [ ] 对话中说明检测到既有文件、保留不动、请用户自行核对。

### 5c 用户不要宿主文件

**触发语**：项目名「不要宿主文件」，单项目，建在 `$SANDBOX/s5c`，要 git；宿主选"不要"。

**核查**（`P=$SANDBOX/s5c/不要宿主文件`）：

```bash
test ! -f "$P/CLAUDE.md"                                   # 必须成功
test ! -f "$P/AGENTS.md"                                   # 必须成功
find "$P" -not -path "*/.git/*" -not -name .git -type f    # 恰三个文件：README.md、.gitignore、project.paper.yaml
```

- [ ] CLAUDE.md 与 AGENTS.md 均不存在；
- [ ] 仍有 `project.paper.yaml`（配置与宿主文件解耦，不因不要宿主文件而跳过配置）。

### 5d Codex 路径

**触发语**：项目名「Codex 项目」，单项目，建在 `$SANDBOX/s5d`，要 git；宿主选 Codex。

**核查**（`P=$SANDBOX/s5d/Codex项目`）：

```bash
test -f "$P/AGENTS.md" && echo "AGENTS.md 存在"            # 必须命中
test ! -f "$P/CLAUDE.md"                                   # 必须成功（CLAUDE.md 不应存在）
grep -c '[<>]' "$P/AGENTS.md"                              # 必须为 0
```

- [ ] `AGENTS.md` 生成、无残留尖括号；
- [ ] `CLAUDE.md` 不存在。

## 场景六：项目信息全留空

针对需求 1 的边界——项目信息逐项留空也照建配置文件。

**触发语**：项目名「空白配置」，单项目，建在 `$SANDBOX/s6`，要 git；项目信息五项全留空、宿主选"不要"。

**核查**（`P=$SANDBOX/s6/空白配置`）：

```bash
test -f "$P/project.paper.yaml"                              # 必须存在（全留空也照建）
grep -c '[<>]' "$P/project.paper.yaml"                       # 必须为 0
grep 'created_by: "paper-init"' "$P/project.paper.yaml"        # 必须命中
grep -E 'user_role|discipline|current_stage|citation_style|language_pref' "$P/project.paper.yaml"   # 五字段齐备
```

- [ ] `project.paper.yaml` 照建、无残留尖括号、`created_by` 落盘、五字段齐备且值为空字符串 `""`；
- [ ] 骨架完整（七目录 + README + .gitignore + project.paper.yaml），无宿主文件、无 `.paper/`。

## 默认路径——优先结构化提问

针对 v3 提问方式增强（SKILL.md 第 1 步「提问方式」段）：宿主有结构化提问工具时优先用选择式呈现，与下方「降级路径」互为正反两面。

**步骤**：任选一场景（建议场景一）正常重跑，触发语**不**加「请不要使用结构化提问」。

- [ ] 提问以**结构化选择 / 编号选项**形式呈现（而非纯散文追问）；
- [ ] 七个选择题项的**选项齐备**：规划范围、git、用户身份、研究阶段、引用格式、语言偏好、宿主配置文件；
- [ ] 自由文本三项（项目名、位置、学科）有落点——结构化工具的自填兜底，或一句文本补问；
- [ ] 其余行为（确认前零创建、只建骨架等）与原场景一致。

> 诚实标注：本清单由「子代理按 SKILL.md 逐轮执行」方式核验，核查的是措辞与选项齐备；真实 AskUserQuestion 弹窗的交互在该执行方式下不一定可验，待安装进真实宿主后人工复核。

## 降级路径——跨宿主约束

**步骤**：任选一场景重跑，触发语中加一句「请不要使用结构化提问工具」。

- [ ] 提问（含项目信息配置五子项与宿主选择，共六项）降级为编号列表纯文本、按语义解析回复，其余行为与原场景一致。

## 跨宿主验证（发布门，随第二宿主可用时执行）

- [ ] 在第二宿主（国内编程智能体）重复场景 1a + 1b，触发与产出一致。

## 结果记录

| 场景 | 宿主 | 日期 | 结果 | 备注 |
| --- | --- | --- | --- | --- |
| 1a 中断跑 | Claude Code（子代理按 SKILL.md 逐轮执行） | — | 待重跑 | 增强 v2 需重跑：本次创建清单现应含 project.paper.yaml 与 CLAUDE.md |
| 1b 完整跑 | 同上 | — | 待重跑 | 增强 v2 需重跑：核查扩展为 4 文件（+project.paper.yaml +CLAUDE.md）、配置内容断言、.gitignore 新增 project.paper.yaml 禁令 |
| 2 非空目录 | 同上 | 2026-07-22 | 通过 | 哨兵 README 与旧笔记 md5 不变；首提只含 .gitignore，既有文件保持未跟踪 |
| 2b 已有 .paper/ | 同上 | 2026-07-22 | 通过 | 说明进行中项目并打住，零新建 |
| 3 已在 git 仓库内 | 同上 | 2026-07-22 | 通过 | 无嵌套 .git，外层 log 与暂存区未动，对话含跳过原因 |
| 4 工作区 + 降级问答 | 同上 | 2026-07-22 | 通过 | 编号列表提问走通；唯一 .gitignore 在工作区根且为 `**/literature/pdfs/`；发现并修复默认工作区名首段重复表述（SKILL.md 已更新） |
| 5a 宿主文件·缺失才生成 | Claude Code | — | 待跑 | CLAUDE.md 生成、AGENTS.md 不存在 |
| 5b 宿主文件·已存在不动 | 同上 | — | 待跑 | 哨兵 CLAUDE.md md5 不变、对话含保留提示 |
| 5c 宿主文件·用户不要 | 同上 | — | 待跑 | CLAUDE.md 与 AGENTS.md 均不存在、仍有 project.paper.yaml |
| 5d 宿主文件·Codex 路径 | 同上 | — | 待跑 | AGENTS.md 生成、CLAUDE.md 不存在 |
| 6 项目信息全留空 | 同上 | — | 待跑 | project.paper.yaml 照建、五字段空字符串占位、骨架完整 |
| 跨宿主验证 | 第二宿主（国内编程智能体） | — | 未跑 | 待宿主可用时按场景 1a+1b+5a 重复 |
| 默认路径·优先结构化提问 | Claude Code（子代理按 SKILL.md 逐轮执行） | — | 待跑 | 提问以结构化选择呈现、七个选择题选项齐备；真实弹窗待真机复核 |

> 说明：2026-07-22 初版的运行方式是"子代理扮演宿主 agent、严格按 SKILL.md 逐轮执行脚本化用户会话"，文件系统断言由核查命令逐条验证。2026-07-23 v2 增强（项目信息配置 `project.paper.yaml` + 宿主配置文件 CLAUDE.md/AGENTS.md）新增场景 5a-5d、6，并把场景 1a/1b 的核查扩展到配置与宿主文件——标"待重跑/待跑"的行需重跑。安装进真实宿主后的自然语言触发（description 触发准确性）与第二宿主一致性尚待人工复核。
