# ADR 0001: SkillHub 作为第四分发渠道，元数据写进 SKILL.md frontmatter

## 状态

已接受。

## 背景

前三个渠道（Claude Code / Codex / WorkBuddy）共用一套思路：元数据放在仓库根的 `.*-plugin/` 清单里，`skills/` 主体完全不受污染，整个仓库作为一个 plugin 整体安装。SkillHub（skillhub.cn）是国内的 skill 社区，想上架就得接受两个与上述思路冲突的前提：

1. **元数据只从 SKILL.md frontmatter 读**——`slug`、`version`、`displayName` 三个字段缺任何一个，`skillhub publish` 直接拒绝（CLI 源码 `skills_store_cli.py` 的必填校验）。而本仓库的结构校验只认 7 个白名单字段，写入 `slug` 会被判为"未知字段"而报错，第一道防线直接红；
2. **一次只发一个 skill 文件夹**，平台侧没有"整体安装"的概念。本仓库 24 个 skill 之间有 45+ 条 `../<skill-name>/references/xxx.md` 跨 skill 引用、构成全网状依赖，用户只装其中一两个必然读到不存在的路径。

被否决的替代方案：

- **发布时临时注入，仓库 SKILL.md 保持干净**：另存一份元数据（如 `.skillhub-plugin/meta.json`），发布脚本把 `skills/` 复制到临时目录、注入字段后再 publish。哲学上更贴合"宿主专有信息隔离在清单目录"，但发到平台上的文件就不再是仓库里那一份。skill 是"给模型看的程序"，发布物与仓库逐字一致是排查线上行为的前提，多一层构建反而增加风险；
- **只上架主 skill `paper-init`**：以为发一个就没有断链问题。实际不成立——`paper-init/SKILL.md` 自己就引 `../_shared/references/...`，单发它一样断。

## 决策

- frontmatter 白名单从"Claude Code 会读的字段"扩为**四宿主并集**：原 7 个之外加 `slug`、`displayName`、`summary`。这三个字段对其余三宿主无副作用（被静默忽略），白名单的原意是"防手误写入无效字段"，而它们不是手误，是第四个渠道的必填项；
- 24 个 `skills/paper-*/SKILL.md` 写入 `slug` / `displayName` / `version` / `summary`。其中 **`slug` 必须与目录名逐字相同**：CLI 安装落盘为 `<install_root>/<slug>/`，只有 slug 与目录名一致，`../<skill-name>/references/` 才解析得到；
- `version` 由 `validate_skill_versions` 钉在 `.claude-plugin/plugin.json` 的 version 上，漏升任何一处即校验失败。SkillHub 从 SKILL.md 读版本号、其余三宿主从清单读，不锁住就会出现"清单升了、平台上还是旧版且无人报错"；
- 24 份 `summary` 一律写明"需与其余 skill 同级安装"。平台既然不能保证整体安装，这句文案就是断链的唯一提示；
- `displayName` 统一采用「学术辅导·<功能名>」前缀策略。主 skill 取 `学术辅导流水线`，其余 23 个取 `学术辅导·<四字功能>`。这条命名策略源自参考项目的搜索机制实测：
  - **参与召回的只有 `slug` 与 `displayName`**。`summary`、`description`、`tags` 一概不参与检索；
  - **中文不分词，query 当作一个整串做子串匹配**：`学术 辅导`（带空格）0 命中；
  - **前缀匹配得分远高于中间子串**：`学术辅导` 作为前缀命中的 skill 得分远高于 `辅导学术` 等中间子串；
  - **`displayName` 就是唯一的检索杠杆**，所以它同时承担"人看的名字"与"被搜到的关键词"两个职责；
- 发布前一律先跑 `skillhub publish skills/<name> --dry-run`（不发 HTTP 请求、不需登录），校验 metadata 与打包。

## 后果

版本真相的副本从 7 处涨到 31 处（7 原有 + 24 个 SKILL.md）。这是本决策最实在的代价，靠 `validate_skill_versions` 兜住；发版流程相应改口径，见 CONTRIBUTING.md。

ADR 中关于"整体安装、不可拆分"的判断在 SkillHub 上**无法由平台机制保证**，降级为 summary 里的一句文案提示。这不是对"整体安装"原则的推翻——`../` 相对引用与契约单源都照旧，只是多了一个平台侧无法强制的入口。若将来 SkillHub 支持多 skill 打包上架，应回头把 24 次发布收敛为一次。

新增 skill 时除"目录名即 slug"外，还要遵守 **`displayName` 以「学术辅导」开头、四字连续不被分隔符打断**（用 `·`）；这条校验脚本守不住，只能靠 CLAUDE.md 与本 ADR 记着。

**`slug` 一经发布不再改动**：它全网唯一，又同时是用户机器上的安装目录名。改 slug 会让所有已安装用户的跨 skill 引用当场断链，且旧 slug 未必能释放。新增 skill 时沿用"目录名即 slug"的规则，不加前后缀。

发布本身依赖两个只能由人在浏览器完成的前置动作（实名认证、创建 API Token），无法纳入 CI 自动化；跨宿主中立的设计约束不受影响——SkillHub 上架是增量渠道，`skills/` 主体在任何宿主照常按 SKILL.md 装载。

## 验证

2026-10-09 首次实施后验证：
- ✅ 24 个 `skills/paper-*/SKILL.md` 全部写入 `slug` / `displayName` / `version` / `summary`
- ✅ `validate_skills.py` 校验脚本通过所有 1011 个测试
- ✅ frontmatter 白名单扩展至 10 个字段
- ✅ 版本一致性由 `validate_skill_versions` 守卫

待后续实测（发布后）：
- 安装 2-3 个 skill 到临时目录，验证跨 skill 引用解析成功
- 搜索「学术辅导」确认 24 个 skill 的搜索排名
- 验证 `skillhub install` 不带 `--namespace` 时的安装布局
