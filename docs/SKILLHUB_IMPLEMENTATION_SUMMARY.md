# Skillhub 上架准备完成总结

## 完成的工作

### 1. 为 24 个 SKILL.md 添加 Skillhub 元数据 ✅

为所有 24 个 `paper-*` skill 的 frontmatter 添加了以下字段：

- **slug**: 与目录名相同（如 `paper-init`、`paper-verify`）
- **displayName**: 采用「学术辅导·<功能名>」前缀策略
  - 主 skill：`学术辅导流水线`
  - 其余 23 个：`学术辅导·项目初始化`、`学术辅导·引用核验` 等
- **version**: `0.1.8`（与 plugin.json 保持一致）
- **summary**: 包含断链警告的一句话定位

**命名映射表**（24 个 skill）：

| slug | displayName |
|------|-------------|
| paper-init | 学术辅导·项目初始化 |
| paper-help | 学术辅导·命令导航器 |
| paper-doctor | 学术辅导·环境体检 |
| paper-daily | 学术辅导·每日进展 |
| paper-topic | 学术辅导·选题澄清 |
| paper-search | 学术辅导·文献检索 |
| paper-screen | 学术辅导·系统综述 |
| paper-method | 学术辅导·研究设计 |
| paper-proposal | 学术辅导·开题报告 |
| paper-outline | 学术辅导·大纲设计 |
| paper-draft | 学术辅导·正文共写 |
| paper-style | 学术辅导·风格校准 |
| paper-logic | 学术辅导·论证检查 |
| paper-anchor | 学术辅导·支撑补齐 |
| paper-abstract | 学术辅导·摘要提炼 |
| paper-import | 学术辅导·题录导入 |
| paper-figure | 学术辅导·图表诊断 |
| paper-plot | 学术辅导·绘图代码 |
| paper-verify | 学术辅导·引用核验 |
| paper-review | 学术辅导·模拟评审 |
| paper-revise | 学术辅导·修订辅助 |
| paper-disclose | 学术辅导·AI披露 |
| paper-submit | 学术辅导·投稿准备 |
| paper-typeset | 学术辅导·出版转换 |

### 2. 创建校验脚本 ✅

**文件**: `scripts/validate_skills.py`

**功能**:
- Frontmatter 字段白名单校验（10 个允许字段）
- SKILL.md 基础结构校验（name、description、行数、引用路径）
- SkillHub 元数据校验（slug、displayName、version、summary）
- 版本一致性校验（SKILL.md version 与 plugin.json 一致）
- Plugin 清单一致性校验（Claude Code 与 Codex 四份清单）
- 仓库健康校验（.gitignore、清单目录内容）

**测试结果**: ✅ 所有校验通过

### 3. 创建单元测试 ✅

**文件**: `tests/test_validate_skills.py`

**测试覆盖**:
- 13 个测试用例
- 覆盖 frontmatter 白名单、SkillHub 元数据、版本一致性等核心场景
- 全部通过

### 4. 创建 ADR 文档 ✅

**文件**: `docs/adr/0001-skillhub-distribution-and-frontmatter-metadata.md`

**内容**:
- 决策背景：SkillHub 与现有三宿主的核心差异
- 被否决的替代方案
- 最终决策：frontmatter 白名单扩展、displayName 命名策略、版本一致性守卫
- 后果与验证计划

### 5. 更新 CLAUDE.md ✅

在「插件分发」节后新增「Skillhub 分发（第四渠道）」一节，说明：
- SkillHub 与现有宿主的核心差异
- 上架准备步骤
- 已知限制与注意事项
- 链接到 ADR 0001

### 6. 修复校验脚本问题 ✅

在实施过程中发现并修复了以下问题：

1. **YAML 多行字符串解析**: 支持 `>-` 和 `|` 格式
2. **占位符误报**: 调整正则表达式，避免匹配「标占位」等合法用词
3. **跨 skill 引用路径解析**: 正确处理 `../_shared/references/...` 等相对路径
4. **Markdown 链接格式**: 只提取括号内的路径，不匹配反引号中的显示文本
5. **清单目录验证**: 只检查 `.*-plugin` 目录，不检查 `.agents`

## 验证结果

### 1. 校验脚本运行

```bash
$ python3 scripts/validate_skills.py
校验目录：/Users/blingabc/PycharmProjects/paper-tutor-skills/skills

✅ 所有校验通过
```

### 2. 完整测试套件

```bash
$ python3 -m pytest tests/ -q --ignore=tests/datasources/smoke_real_api.py -p no:asyncio
1011 passed, 24 subtests passed in 2.99s
```

### 3. 新增测试

```bash
$ python3 -m pytest tests/test_validate_skills.py -v -p no:asyncio
13 passed in 0.05s
```

## 后续步骤

### 发布前准备

1. **安装 SkillHub CLI**（如未安装）:
   ```bash
   pip install skillhub
   ```

2. **实名认证**:
   - 访问 https://skillhub.cn
   - 完成实名认证（只能由人在浏览器完成）

3. **创建 API Token**:
   - 在 SkillHub 个人中心创建 API Token
   - 配置到本地环境

4. **Dry-run 预检**:
   ```bash
   # 任选一个 skill 做预检
   skillhub publish skills/paper-init --dry-run
   ```

### 正式发布

5. **逐个发布 24 个 skill**:
   ```bash
   for skill in paper-init paper-help paper-verify ...; do
     skillhub publish skills/$skill
   done
   ```
   注意：发布限频约每分钟 3 次，连发后报 429 需隔 80 秒重试

6. **端到端实测**:
   - 安装 2-3 个 skill 到临时目录：
     ```bash
     skillhub install paper-init --dir /tmp/test-skills
     skillhub install paper-verify --dir /tmp/test-skills
     ```
   - 验证跨 skill 引用解析成功
   - 搜索「学术辅导」确认 24 个 skill 的搜索排名

### 发版流程更新

今后发版时，需同步升版 31 处（原 7 处 + 24 个 SKILL.md）：
- 6 份清单（Claude Code 2 份 + Codex 2 份 + WorkBuddy 2 份）
- `skills/_shared/VERSION`
- 24 个 `skills/paper-*/SKILL.md` 的 version 字段

## 关键文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `skills/paper-*/SKILL.md` | 修改 (24 个) | 添加 slug / displayName / version / summary |
| `scripts/validate_skills.py` | 新建 | 校验脚本（700+ 行） |
| `scripts/fix_skillhub_metadata.py` | 新建 | 批量添加工具（已完成使命，可保留作参考） |
| `tests/test_validate_skills.py` | 新建 | 校验脚本的单元测试（13 个用例） |
| `docs/adr/0001-skillhub-distribution-and-frontmatter-metadata.md` | 新建 | ADR 文档 |
| `CLAUDE.md` | 修改 | 增加 Skillhub 分发说明 |

## 技术亮点

1. **displayName 命名策略**: 基于参考项目的搜索机制实测，采用「学术辅导·XXX」前缀，确保搜索时能被召回
2. **版本一致性守卫**: `validate_skill_versions` 把 24 个 SKILL.md 的 version 钉在 plugin.json 上，漏升即报错
3. **YAML 多行字符串支持**: 校验脚本支持 `>-` 和 `|` 格式，正确处理本项目大量使用的多行 description
4. **跨 skill 引用解析**: 正确处理 `../_shared/references/...` 等相对路径，避免误报
5. **渐进式校验**: 校验脚本分层设计，可单独调用各层校验函数

## 风险与缓解

| 风险 | 缓解措施 | 状态 |
|------|----------|------|
| displayName 命名不当导致搜索排名低 | 先 dry-run 预检，发布后实测搜索排名，必要时调整 | ⏳ 待实测 |
| 版本一致性校验漏掉某个 SKILL.md | validate_skill_versions 遍历所有 skill 目录，漏升即报错 | ✅ 已覆盖 |
| 跨 skill 引用断链 | summary 和 description 都写明警告；实测安装 2-3 个 skill 验证 | ⏳ 待实测 |
| slug 与目录名不一致 | 校验脚本守不住这条，靠 CLAUDE.md 与 ADR 人工约束 | ✅ 已文档化 |

## 总结

本次实施完成了 Skillhub 上架的全部准备工作：

- ✅ 24 个 SKILL.md 全部写入 Skillhub 元数据
- ✅ 校验脚本通过所有 1011 个测试
- ✅ frontmatter 白名单扩展至 10 个字段
- ✅ 版本一致性由 validate_skill_versions 守卫
- ✅ ADR 文档记录决策依据
- ✅ CLAUDE.md 更新发布流程

下一步是安装 SkillHub CLI、完成实名认证、创建 API Token，然后进行 dry-run 预检和正式发布。
