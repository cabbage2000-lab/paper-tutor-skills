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

## [0.1.7] — 待定

<!-- RELEASE-BLOCKER 本段落仍是开发骨架，还不能发布。
     发版前的收口动作：① 摘要句改成本版实际内容；② 删掉本注释整块；
     ③ 清掉段落里其余 HTML 注释；④ 标题日期改为实际发版日。
     留着本注释打 tag 会让 extract_changelog_notes.py 直接失败（宁可不发，
     也不发占位符）——这道拦阻只在发版时刻生效，开发期 CI 照常绿。
     四份清单、skills/_shared/VERSION、两个 README 的三处版本号已同步为 0.1.7。
     本版仍在累加条目。 -->

**（待填：一句话说清本版让使用者多了什么能力，或哪个旧能力真的能用了。）**

### 新增（Added）

- **`/paper-search` 的中文轨从「逐条手抄」升级为「官方导出 + 自动解析」**——新增
  [`parse_export.py`](skills/paper-search/scripts/parse_export.py)：用户在知网 / 万方站内检索后，用站点自己的
  「导出引文」功能导出 BibTex / EndNote(RIS) 文件，交脚本解析成与 `search.py` 同形的 `results`，直接并入
  同一张文献笔记表。20 条文献从「逐条抄标题/作者/年份/刊名」变成一次导出，且题录比手抄更全（带卷期页码、
  部分带 DOI，可续跑 `--lookup-doi` 补全）。注册表相应给 `cnki` / `wanfang` 两个 guided 源加上
  `import_export` 能力。

  覆盖方式如实分档为「用户回填（官方导出）」与「用户回填（手工）」，**都不是「自动检索」**——中文库的检索
  仍由用户在站内执行，说成自动检索会违反覆盖声明的如实要求。同一篇同时来自英文 API 与中文库时，`sources`
  累积并列（中英双库均收录是有价值的事实，不丢任一侧）。

  **为什么是解析导出、而不是程序化检索知网**：实测知网海外版 `robots.txt` 为 `User-agent: * / Disallow: /`，明示
  禁止自动化访问（国内主站对非浏览器 UA 返回 HTTP 418，robots 内容读不到）；而本产品分发给他人使用，不把站点
  ToS 与账号风险默认转嫁给每个不知情的安装者。**这是合规与分发层面的取舍，不是技术做不到**——浏览器 MCP 驱动
  站内官方导出 API 的路径已评估、题录质量与手动导出相同，未采用的原因就是上面这两条，留档见
  [检索方案模板](skills/paper-search/references/知网万方检索方案模板.md)。

  站内题名确实注入了防爬水印（单条标题散布 22-27 个不可见字符，U+200B-200F / U+2060-206F / U+FEFF，外加
  `<span class="hrc">` 包裹的「知网」「版权」字样），但那是**解析器要处理的事实、不是拒绝抓取的理由**：
  不可见字符按 Unicode `Cf`/`Cc` 类**无损清除**（且必须先删再折叠空白——反过来会把 U+FEFF 变成真空格，在词内
  留下 `content` → `c ontent` 这种不可逆的假词边界）；可见水印词**只告警、不删**（「版权」可能是真实题名的一
  部分，如《数字出版版权保护研究》，判断归用户）。跳过的条目、疑似水印题名、无 DOI 条目数三类一律进
  `warnings`，宿主须原文呈现、不许吞掉。

### 修复（Fixed）

- **`/paper-init` 生成的 README 少标两个命令的写入者，而它自带的自检又必然误报**——同一张表上的两个缺陷，
  真机跑一次就同时撞上：

  1. paper-init 的「命令发布映射表」停在 18 行，漏了 `/paper-style`（`manuscript/`）、`/paper-typeset`
     （`submission/`）与尚未发布的 `/paper-anchor`（`literature/`）。SKILL.md 明写 README 的「谁写入」列
     **只准从本表推导**，于是生成的 README 里 `manuscript/` 与 `submission/` 两行各少一个写入者。这种漏
     从产物本身看不出来——用户只会以为那两个目录没有对应命令，不会想到是表漏了。
  2. 映射表 `/paper-search` 行的「下一步」列写着 `` `<你的 RQ>` ``（故意留给读者自己填的占位符），而
     README 模板的实例化自检是 `grep '[<>]' README.md` 期望零命中——真机在生成的 README 第 32 行命中、
     报了一次假警。更要紧的是它与实例化规则第一条「尖括号项全部替换为真实值」正面冲突：替换掉是错的
     （该由读者填），留着则自检误报，两条路都错。

  修法：三条命令补进表（未发布的 `anchor` 也列进去，落盘目录 / 「下一步」行 / 交接语一并预填，将来发布时
  只需改一个状态格）；占位符改写成「你的 RQ」这类中文引号形态，保留「正文零尖括号」这个零例外的机械判据，
  而不是给自检开个例外——一旦开例外，实例化时每个尖括号都要先判断「这个算不算允许的」，规则就从可机械
  执行退化成要模型拿主意。

  根因是这张表此前**一条守卫都没有**：`test_manifest_consistency.py` 盯着 `skills/README.md`（禁第二份
  清单）与两个根 README（须与主清单一致），却对被 CLAUDE.md 称作「派生呈现」的映射表毫无覆盖。所以
  `style` 与 `typeset` 自 v0.1.0 首发起就没进过表，五个版本没人发现。现补四条守卫：命令集合、落盘目录与
  发布状态、「下一步」列无尖括号、README 自检判据仍在——末条与第三条成对，判据若被删掉，第三条就成了
  守着一句空话。

- **`/paper-help` 的命令总表看不见正在开发的 `/paper-anchor`**——同一类漂移的另一半。总表是导航器的全貌
  视图，paper-help 的 SKILL.md 明写「不把未发布命令说成可用、**不漏标开发中命令的状态**」，但 `paper-anchor`
  自实现完成起就没进过表。后果不是表不好看：用户问「导师说这段缺文献支撑，该用什么」时，导航器只能回答
  该环节没有命令，给不出「有一个正在开发中」这个用户其实想知道的事实。现补进阶段 C 并标 🔧 开发中。

  这张表的守卫判据与 paper-init 那张不同，故另立三条（命令集合须覆盖主清单**全部**命令，含 infra 与未发布，
  而映射表只收落盘目录非空的；状态标记与 `status` 一致；状态图例与守卫用的字面量一致——图例措辞若改而守卫
  没跟上，守卫会开始错判）。两张表的表格解析共用一个 `section_table_rows()`，按 `## 小节` 切分而非全文扫
  表格：这两份 SKILL.md 里还有边界表、字段表，全文扫会把它们行文里提到的命令名也算进清单。

---

## [0.1.6] — 2026-07-30

**本版让 `/paper-search` 的检索结果不再静默缺斤少两**：结果被 `--limit` 截断时脚本会自报截掉了
几条、该调到多少（此前只能靠自己比对 `stats.after_dedup` 与 `shown`，照抄示例参数做综述检索会
整年整年地漏文献），`--limit 0` 可一次取回全部去重结果；DOI 回填补全也不再把前缀根本没注册的
（疑似编造的）DOI 和真实中文文献说成同一件事。

### 修复（Fixed）

- **`/paper-search` 的示例参数会让综述检索静默漏掉整整几年的文献**——SKILL.md 第 2 步
  「英文 / 自动轨」的命令行示例写着 `--per-source 20 --limit 30`，宿主照抄就跑。实测一条
  真实 RQ 下：74 条去重结果只呈现 30 条，**2024 与 2023 两整年、36 篇一条未进**。根因是
  `--limit` 是**截断不是分页**（`build_payload()` 里 `ranked[:limit]`，没有 offset），默认 30
  配默认排序 `year_desc` 恰好等于「只给最新的 30 条」——年份越早越容易被整年切掉。判据其实
  一直在输出里（`stats.after_dedup=74` 对 `shown=30`），只是**没有一处告诉宿主要看这两个数**。
  换 `--sort source_count` 不解决（实测两种排序前 30 条只差 3 条）。现在 SKILL.md 补一条与
  「不加日级时间窗」并列的子项：先跑一次看 `stats.after_dedup` 是多少、按那个数调 `--limit`，
  `shown` 明显小于 `after_dedup` 就必须调大重跑或向用户说明。

  提示层只能管到「宿主读到了就会调参」，所以代码层同时补两处（都是纯增量，默认 30 不动
  ——`/paper-daily` 的新发轨共用这个脚本，改默认值会波及按时间监测）：

  1. **截断时脚本自报**——`shown < after_dedup` 时往 `warnings` 数组塞一条，说清截掉了几条、
     按当前排序被截的是哪一头、该把 `--limit` 调到多少。搭的是 `warnings` 已有的现成契约
     （SKILL.md 早写着「非空时原文呈现给用户，不要吞掉」），宿主漏读文档也会在输出里撞见。
  2. **`--limit 0` = 不截断**，全量呈现去重结果，省掉「先跑一次看 `after_dedup` 再重跑」这轮
     往返。负数按手滑挡掉（退出码 2），同 `--days` 的既有口径。

  实测复现与验证（2026-07-29，crossref + openalex，`flipped classroom nursing education`
  限 2020-2024）：`--limit 5` 时去重 35 条只呈现 5 条、**全是 2024 年**，2020-2023 整四年
  一条未进，warning 如实报出「去重后 35 条、本次只展示 5 条……请用 `--limit 35` 或
  `--limit 0` 重跑」；换 `--limit 0` 后 35 条全出，年份分布 2024:6 / 2023:5 / 2022:6 /
  2021:12 / 2020:6，`warnings` 空。

- **回填补全把编造 DOI 与真实中文文献说成同一件事**——`/paper-search` 第 4 步的
  `scripts/search.py --lookup-doi` 对着一个前缀根本没注册的 DOI（`10.9999/fake` 这类编造
  强信号），给出的 `note` 与真实中文文献未被收录时**一字不差**：「各开放源未命中：可能是
  中文库文献或元数据未收录，请人工核对，**勿据此判定编造**」——方向正好说反了。根因是
  `build_lookup_payload()` 只分了 ISTIC 与「其余查不到」两档，而路由给 `not_registered` 的
  `sources` 是**空列表**（前缀未注册就不浪费重试预算，见 `_shared/paper_shared/datasources/routing.py`），
  于是 `hits` 恒空、径直落进兜底档。区分信息只剩 `route_note` 字段，而 `note` 才是给宿主读的
  断言句。更要紧的是同一个 `not_registered` 在 `/paper-verify` 的 `judge.py` 里正是判
  NOT_FOUND / fabricated 的最强信号——**同一个信号在两个 skill 里被读成相反的意思**。

  现在 `not_registered` 单列一档：如实说「DOI 前缀未在任一注册机构注册（因此未查任何元数据源）：
  这是 DOI 不存在的强信号，请人工核对来源；存在性判定请走 `/paper-verify`」。两处措辞是有意的
  ——不写「元数据未命中」（一个源都没查过，说未命中不如实），仍保留「人工核对」且 `found`
  照旧为 `false`，**存在性判定不在 paper-search 做**这条红线不动。SKILL.md 同步补两处行为
  指令：第 4 步回填闭环明写 `route_note` 与 `note` **两个字段都要读、都要原文转述**，三档
  证据强度不许混为一谈，并加「DOI 照记」的唯一例外（`not_registered` 一档**先别照记**，回读
  两个字段请用户确认 DOI 来源——「不判 NOT_FOUND」不等于把疑似编造的 DOI 静默收进笔记表），
  边界与异常对照表在 ISTIC 那行下新增对应一行。`route_note` 这处此前只有 `/paper-verify` 在
  展示（`report.py` / `report_html.py`），paper-search 的指引漏了它，分档信息等于白传。单测
  钉住两侧：既不许退回 NOT_FOUND，也不许与「各源未命中」共用同一句。

- **开发骨架能一路留到发版、把占位符发进 GitHub Release**——0.1.5 发版时实况：CHANGELOG
  的 0.1.5 段落到打 tag 前仍顶着「⚠️ 开发中骨架，发版前必须改写」的警告块、摘要句是
  「（待填：…）」，而 `extract_changelog_notes.py` 当时只拦「段落找不到」与「段落为空」
  两种情形，**占位符两道都过**；759 个测试也全绿，因为没有一条盯这件事。差一步就把骨架
  发到 Release 页面上，靠人肉复核才拦住。脚本的 docstring 其实早写了「宁可不发，也不发
  空白**或残缺的**」——只是「残缺」那一半从未实现。

  现在补第三道检查 `find_blockers()`：段落里留着 `RELEASE-BLOCKER` 哨兵、或残留任何
  HTML 注释，一律以非 0 退出、发布流程直接失败，并把该改什么一次说清（免得删了哨兵
  重打 tag 又栽在注释上）。两处设计取舍：

  1. **检查放在脚本里，不做成 pytest。** 骨架在开发期是**合法**状态——开完骨架要一路
     累加条目，中间每次 push 都跑 `tests.yml`。做成断言会让整个开发周期 CI 长红，而
     长红会让人对红灯脱敏，比没有守卫更危险。这个脚本只被 `release.yml` 调用，正好卡在
     骨架「从合法变成错误」的那一刻。
  2. **用哨兵，不用字面量黑名单。**「待填」「开发中骨架」这类词表一改措辞就静默失效，
     等于又造一份会漂移的真相（硬规则 1 反对的正是这个）。哨兵是机器可读契约，骨架
     提示语随便改；删掉哨兵是一个有意识的「我确认这段收口了」的动作。HTML 注释那条
     是兜底——万一开骨架时忘了写哨兵，脚手架注释还在就仍拦得住。

- **`extract_changelog_notes.py` 此前零单测**——发版链路上唯一的关键脚本，`tests/` 下四个
  测试文件一个都不碰它。新增 [`tests/test_release_notes.py`](tests/test_release_notes.py)：
  切段边界（不吃进上一版内容、段末分隔线不进正文、末版取到文件尾）+ 两条阻塞判据 +
  「换一套骨架措辞后哨兵仍生效」。另有一条与 `release.yml` 互补的事后守卫——**已发布的
  历史段落必须全部干净**（release.yml 事前拦，这条在下个版本开发时立刻红，若某次真把
  骨架发出去了会指名道姓）。**有意不断言最新段落可发布**，理由同上第 1 条。

- **哨兵检查会把「讲哨兵机制的段落」误判成开发骨架**——本版发版当场踩到：上面那条新增的
  哨兵检查是**整段搜字面量**，而本段落正文正在讲这套机制、如实写出了哨兵名，于是 0.1.6
  被自己的检查拦住、发布流程直接失败。改 CHANGELOG 措辞躲开不算修——CLAUDE.md 的发版
  流程和后续每次讨论这个机制都会写出这个名字，躲一次下次照样栽。现在按哨兵的本来语义
  收窄：**只在 HTML 注释块内**才算哨兵（骨架的哨兵本来就写在注释里），未闭合的注释按吃到
  段末处理、骨架写坏了也不漏拦。代价是哨兵检查不再是独立防线（注释内的哨兵必然也被
  「残留 HTML 注释」那条兜住），它退化为**更精准的诊断**——报「这仍是开发骨架、该删哨兵块」
  比报「有脚手架注释」更能让人一眼知道该改什么。单测钉两头：正文提哨兵名不拦、注释里的
  哨兵（含未闭合）仍拦。

### 变更（Changed）

- **CLAUDE.md 的发版流程补「收口」这一步**——这是上述漏洞的另一半根因：原流程第 1 步写
  「在 CHANGELOG 写 `## [x.y.z] — 日期` 段落」，读起来像发版时才写；而实际做法是开骨架时
  写框架、一路累加、发版时才需要收口，**「收口」这个动作在文档里根本不存在**。现在拆成
  「开版本骨架」与「发版」两段，前者明确骨架必须含 `RELEASE-BLOCKER` 哨兵，后者第 1 步
  列全收口的四件事及其失败后果。守卫测试表由四个更新为五个。

---

## [0.1.5] — 2026-07-29

**`/paper-daily` 的「今日 / 最近 N 天」从写在文档里变成真能执行。** 一个叫「每日学术雷达」
的命令，此前实际时间粒度是**年**：日级日期在归一化那步被丢掉，SKILL.md 里写的「按天筛选」
宿主无从下手。这次四层一起补齐（arXiv 客户端带出 `date`、检索脚本输出契约加 `date`、
后置过滤支持日期闭区间、CLI 新增 `--days N` 与 `--date-from` / `--date-to`），并把 arXiv 的
原生日期区间与按提交时间倒序下推到 API——少了后者，「拉回前 N 篇」按的是相关度而不是最新，
`--per-source` 调多大都换不来时效性。给不出日级日期的源一律留 `null`、不用年份凑假日期，
0 命中的两种成因（词太多 / 该源不给日期）由新增的 `warnings` 数组说清。
安装侧补上 **WorkBuddy 提示词**（此前该宿主用户只能自己猜路径，而它的项目级目录恰好
是最容易写错的一处）。新增 `/paper-anchor`（从已写好的论断反向找文献支撑）实现完成，
但主清单里**仍是 `planned`**、两条人工验收项跑过后再翻 `released`。
已发布命令入口数不变（25 个），skill 目录数 23 → 24。

### 新增（Added）

- **`/paper-daily` 的「今日 / 最近 N 天」真的按天了**——此前这个时间窗**执行不了**：
  `search.py` 的输出契约里根本没有日级日期字段，SKILL.md 里写的「按 `submittedDate`
  内存筛选」宿主无从下手，一个叫「每日学术雷达」的命令实际粒度是**年**。四处一起修：

  1. `clients/arxiv.py` 早就解析了完整时间戳 `published`，但 `_metadata()` 只带出 `year`、
     日期在归一化这步被丢掉（`SourceHit.raw` 里还在）。现在带出日级 `date`（`YYYY-MM-DD`）。
  2. `paper-search/scripts/search.py` 的 `dedup_hits()` 只读 `metadata`，输出契约补上 `date`
     字段——**给不出的源为 `null`，不用 `year` 凑一个假日期**（目前只有 arXiv 提供日级日期）。
  3. `_postfilter` 支持 `date_from` / `date_to` 闭区间。日期缺失在设了窗口时**排除**（同 `year`
     的处理、不同于 `type`）：把无日期条目留在窗口内，等于把窗口外的旧文章当成新发。
  4. CLI 新增 `--days N`（含今天，`--days 1` = 今日）与 `--date-from` / `--date-to`（两者互斥）。
     日期换算收进脚本，不让宿主自己算——跨月算错是 LLM 的高频失误。

  arXiv 侧还补了两处原生能力下推（**只在设了日期窗口时生效**，无窗口路径的 URL 与缓存键
  逐字节不变）：`submittedDate:[...]` 闭区间，以及 `sortBy=submittedDate&sortOrder=descending`
  ——少了后者，「拉回前 N 篇」是按相关度的 N 篇而不是最新的 N 篇，`--per-source` 调多大都
  换不来时效性。

  查询串在窗口下改走 `(all:w1 AND all:w2 ...)` 布尔式。这不是洁癖，是 2026-07-29 对真实
  API 的实测结论：**裸多词与 `AND` 同时出现时只有第一个词生效**，返回的是窗口内的全站新发
  （星系尘埃、中子产生……与主题毫无关系）；整串加引号变精确短语又太窄（同一查询 0 条）；
  逐词 OR 太松（同样返回全站新发）。逐词 AND 是四种写法里唯一可用的。代价是比无窗口路径
  更严——同一 10 天窗口实测 3 词命中 12 条、5 词命中 10 条、**7 词命中 0 条**，所以超过 5 个
  词时脚本会在新增的 `warnings` 数组里提醒「0 命中可能是词太多而非当期无新发」。同理，
  给不提供日期的源加窗口必然 0 命中，也在 `warnings` 里说清「这是源不给日期、不是该源
  当期无新发」——这两条都是为了不让一个 0 被读成错误结论。

- **`/paper-anchor` 文献支撑补齐**（实现完成、主清单里 `status: planned`，两条人工验收项
  跑过后再翻 `released`）——补的是一个真实断点：`/paper-draft` 与 `/paper-outline` 早就把
  无支撑处标成「⚠️ 未经文献支撑」「⚠️ 纯结构占位」，`/paper-search` 又只从 RQ 出发做综述式
  检索，而**从已写好的论断反向找支撑**这条路此前无命令承接——用户得手工拼四步（logic 定位
  → 自己把论断改写成检索式 → search 检索 → 回 draft 挂锚点），中间两次人工翻译。导师说
  「这段缺文献支撑」是它的正面场景。形态：确定性内核 `scripts/anchor_scan.py`（按段落数
  四形态引用密度、定位零引用段与既有 ⚠️ 标记）+ 论断五分类（事实陈述 / 方法依据 / 理论框架
  / 对比创新 / 价值判断，各自的支撑要求与出口不同）+ 复用 `paper-search/scripts/search.py`
  真实检索 + 「该文五字段 vs 你的论断」字段级比对交用户判定。
  **它离学术不端最近的一步是 citation shopping（先有结论后找文献）**，所以每条缺口一律
  并列给「补文献」与「改弱表述或删除」两个出口、价值判断类只给后者且不进检索、产物禁
  「已为您找到支撑」这类完成态措辞——这三条由一道专属发布门（两个出口门，N≥3 次独立跑）
  验收。脚本只算「哪里引用为零」，**绝不判断「这里是否需要引用」**（方法章的操作步骤本来
  就可以零引用）。
- **WorkBuddy 安装提示词**——两个根 README 的安装段补第三个宿主，此前只有 Claude Code 与
  Codex 两段、WorkBuddy 用户只能自行猜路径。三处路径事实取自 WorkBuddy 的 skill 加载器
  实现（`getHomeSkillsDir` / `getProjectSkillsDir` / `scanSkillsDirectory`）而非推测：
  用户级 `~/.workbuddy/skills/`，**项目级却是 `.codebuddy/skills/`**（底层 CodeBuddy 内核
  写死，与用户级目录名不对称，这是最容易写错的一处），且它**不读 `.claude/skills/`**。
  另记两条它特有的装载行为：递归扫描到 5 层深、无 SKILL.md 的目录静默跳过（`_shared`
  因此安全），但技能名按目录层级拼接，多套一层 `skills/` 会让命令变成 `skills:paper-init`
  ——提示词里显式拦了这一条。

### 修复（Fixed）

- **`paper-daily` 降级矩阵 F3 写的 `network_status=partial` 在实现里不存在**——实现只发
  `ok` / `degraded` / `offline` 三个值（`datasources/models.py` 与 `probe.py`），部分源失败时
  发的是 `degraded`。宿主照 SKILL.md 去匹配 `partial` 永远匹配不上，F3 这一档形同没写。
  F2 的 `offline` 是对的，只改 F3。发现于一次真实的部分源失败（四源里 semantic_scholar 挂了）。

- **`--date-from` / `--date-to` 的校验不能只靠 `date.fromisoformat`**——Python 3.11 起它还
  接受无横线的 `20260729`，3.9 不接受（硬规则 7 要求 3.9+），同一份入参两个版本行为不同。
  更要紧的是无横线形式会流进 `_postfilter` 做字典序比较（`2026-07-29` vs `20260729`），
  比出来的结果是错的。现在先卡形状（长度 10 + 两个横线位）再解析。

- **两个根 README 的版本号漂移**——此前停在 v0.1.2，而 0.1.3、0.1.4 两次发版都只改了
  CHANGELOG 与四份清单，README 连漂三个版本没被发现（用户照 README 判断版本，会以为
  自己装旧了）。现同步为当前版本，并补守卫防复发：`test_plugin_manifest.py` 锁住两个
  README 的三处版本号（badge / 简介段 / 快速开始段）与 CHANGELOG 最新版本一致。原先
  第 2 类守卫只管清单层，README 恰恰是最显眼、最容易忘的那处。

### 重构（Refactored）

- **引用识别与文本切分提到共享层** `_shared/paper_shared/citations.py`——`paper-style` 与
  新增的 `paper-anchor` 都要认「哪里有引用」，各存一份正则必然漂移（硬规则 1 反对第二份
  真相）。**搬迁不是纯移动**：两个消费者对「什么是噪声」的定义相反——style 剥掉引用块与
  markdown 链接（算句长时它们是噪声），anchor 恰恰要靠它们认支撑（长引文是文本引证、
  `[Smith 2023](literature/…)` 就是挂上的锚点）。故加了 `drop_blockquote` 开关，并把三条
  顺序依赖（哪些函数必须吃原始文本、哪些必须吃已剥文本）写进模块 docstring——搞反不报错、
  只静默算错。`style_metrics.py` 改为 import、**行为不变**，其 51 条既有 pytest 是这次搬迁
  的等价性安全网；另加一条守卫测试防「第二份真相复活」（断言两处用的是同一个实现对象）。
  顺带修两个对两个 skill 都对的 bug：脚注定义行（`[^1]: 张三. 某文. 2020.` = 参考文献条目）
  不再被当成正文；缺口标记文本（`⚠️ 未经文献支撑（锚点 Lee 2024 未在 literature/）`）里的
  4 位年份不再被著者-出版年制正则命中——后者会让**明确标了缺支撑的段落反而被算成有引用**。

### 变更（Changed）

- **两个 README 去掉「已知边界见 CHANGELOG」的指向**——那条锚点形如
  `#015--2026-07-29`，随版本号与发版日期变，每次发版都得记着同步改，漏改就是静默
  死链（点过去停在页面顶部）。对读者的价值也有限：真要看边界，CHANGELOG 本来就在
  仓库首屏。逐命令的已知观察项仍以 `skills/_shared/commands.yaml` 为准，那条指向保留。

---

## [0.1.4] — 2026-07-29

**报告 HTML 改由脚本渲染，产物断网也能正常排版。** `/paper-topic`、`/paper-logic`、
`/paper-revise` 此前逐字手写 HTML，现在只写 Markdown，HTML 由共享渲染器从同一份 `.md`
机械投影而来。使用者能直接感到的两点：产物不再引任何 CDN 或 JS，**拔网线照样正常排版**
（此前断网会退化成无样式页面）；每次调用少烧约 1.1 万 token。代价是视觉上不再有各命令的
专属组件（事实卡、四链卡片边框、时间线圆锚点、徽章底色），统一为「档案纸面 + 表格 +
列表 + 四层染色」——那些组件承载的信息在 `.md` 里本就由 👤📋🪞❓ 与文字完整保留，
颜色只是同一信息的第二种编码。**其余 13 个产物型命令仍在手写 HTML、随后跟上**；
命令与 skill 目录数不变。

### 新增（Added）

- **共享报告渲染器**（`skills/_shared/paper_shared/report/` + CLI
  `skills/_shared/scripts/render_report.py`）：Markdown → 单文件 HTML 的确定性转换，
  样式内联、零外部依赖。四层语义色由渲染器从 `_shared/tailwind.config.js` 解析注入——
  色值仍只定义一次，改 config 即改全部产物，config 缺失时报错而非兜一份备份色值。
  按 👤📋🪞❓ 自动上色、元表标注行渲染成顶部图例；`paper-disclose` 的读者轴自动切
  r1-r4（同样的 👤 在那里是「导师带教」，按四层上色会上错）；`--embed-svg` 可把
  `paper-screen` 的 PRISMA 流程图内嵌进产物。

### 变更（Changed）

- 上述三个命令的落盘流程改为「写 `.md` → 跑渲染器」。各命令的
  `references/报告样式模板.html` 与 `样例.html` 保留作视觉参考、不再是产物的生成源；
  渲染脚本跑不了时命令**只交 `.md` 并显式声明「HTML 视图未生成」**，不手写一份顶替。

---

## [0.1.3] — 2026-07-28

**核验报告有了 HTML 视图；安装后可查看版本。** 两件事都是「让已有能力真的被用上」：
`/paper-verify` 此前只出 Markdown + JSON，40 条引用的核验结果读起来要靠肉眼扫，
现在默认多出一份单文件 HTML 报告——顶部先说有几条要动手、六态徽章可点着筛选、
DOI 可点开复核、待人工核对的检索词可一键复制；另新增 `skills/_shared/VERSION`
文件（随 `skills/` 安装走），`/paper-help` 会话首次回复时在顶部显示版本号行。
命令与 skill 目录数不变（仍是 25 个命令入口 / 23 个 skill 目录）。

### 新增（Added）

- **`/paper-verify` 核验报告 HTML 视图**（`skills/paper-verify/scripts/report_html.py`）：
  与 Markdown / JSON 同源于一份 payload，默认随核验生成 `verify-<时间戳>.html`
  （`--no-html` 可关；也能对旧报告单独重渲：`report_html.py --in verify-*.json`）。
  为读者省时间的部分：**裁决横幅**（第一句话回答「有几条要动手」）、**六态堆叠条**、
  分布表每态附一句「这一态意味着什么」、**需优先关注锚点直达**详情、
  **sticky 六态筛选轨**（40 条报告里只看已撤稿）、逐条卡片按态染左色带、
  **元数据不符逐字段对照表**（引用里写的 ↔ 数据源里的）、`<details>` 折叠证据链、
  DOI 渲染为 doi.org 可点链接、待人工核对条目的检索词一键复制 + 知网/万方入口可点。
- HTML 报告样式走 **Tailwind CDN + typography 插件**（与其余报告模板同一技术栈），
  `_shared/tailwind.config.js` 由渲染脚本**原样内联**进产物：产物落在 `.paper/review/`
  后相对路径 `../../_shared/tailwind.config.js` 指不到 skill 包（路径问题、与网络无关），
  内联后四层语义色仍只在那份 config 里定义一次，改 config 即改报告。
  内联时转义 `</`——config 注释里的 `</script>` 会提前闭合标签、让整份 config 静默失效。
  打印时自动展开全部证据链并隐去筛选轨，窄屏下 4 列表格重排为卡片、不丢任何一列。
- [`tests/paper-verify/test_report_html.py`](tests/paper-verify/test_report_html.py)
  34 条单测：六态标签取自 `report` 模块不重复定义、降级横幅 MD 与 HTML 同文案、
  用户粘贴内容的转义（报告会被转发，`<script>` / 属性注入必须无效）、
  内联 config 的 `</` 转义与「四层色值不在 CSS 侧复制」、空报告与缺字段条目不炸。
- `skills/_shared/VERSION` 纯文本版本标识文件（一行版本号），随所有安装方式走
  （散装 `sync_skills.py` + 插件市场都复制 `skills/`）。
- `/paper-help` 会话首次回复时在输出顶部显示 `📄 Paper-Tutor-Skills v<版本>` 行，
  版本号读 `_shared/VERSION`；读不到则省略版本行、不凭记忆编版本号。
- [`tests/test_plugin_manifest.py`](tests/test_plugin_manifest.py) 新增守卫：
  `_shared/VERSION` 与 CHANGELOG 最新版本一致（发版漏改 VERSION 会被测试拦下）。

### 变更（Changed）

- **核验报告的降级声明改为报告可见**：`network_status` 为 `offline` / `degraded` 时，
  Markdown 与 HTML 报告开头都会摆一条降级横幅（说明「核验不可用」或「没查成 ≠ 查了没有」）。
  此前该字段只写进 JSON，人读报告里看不到——而「降级必须明标」是核验类 skill 的
  代码层红线，藏在 JSON 里等于没标。两版共用 `report.NETWORK_BANNER` 一份文案。
- `verify.py` 的 stdout 摘要新增 `report_html` 路径字段，`/paper-verify` 完成时
  优先指向 HTML 报告（纯文本环境仍指 `.md`）。

---

## [0.1.2] — 2026-07-28

**核验准确性修复。** 四个 bug 都落在 `/paper-verify` 的判定链路上：三个让完全正确的引用
被误判有问题（其中 DOI 截断更坏，会让真实文献落「疑似不存在」），一个让撤稿检测完全失效。
全部以真实 API 响应实测验证（非 mock）。命令与 skill 内容不变（仍是 25 个命令入口 /
23 个 skill 目录），已知边界与 v0.1.0 相同，见下方 [v0.1.0 已知边界](#v010-已知边界)。

### 修复（Fixed）

- **撤稿检测此前完全失效**——Crossref 客户端读的是 `update-to`（本文*更新了*别人，
  即本文自己就是那份撤稿声明），而要判「本文*被*撤稿」须读 `updated-by`。两个字段方向
  相反，读反的后果是 `RETRACTED` 态在真实 API 下永不触发：实测 Wakefield 1998
  （`10.1016/S0140-6736(97)11096-0`）的 `update-to` 为 `None`，撤稿信息全在 `updated-by`。
  测试 fixture 当初也按 `update-to` 构造，**与实现错得一致**，于是单测长期绿灯、形成闭环
  自证——现已按真实响应形状重构 fixture，并加一条反向用例（本文*是*撤稿声明时不得判为
  已撤稿）锁住字段方向。
- **第一作者比对几乎必然误报**——判定层假设作者名是「姓, 名」（逗号前为姓、无逗号取首
  token），但 Crossref / OpenAlex / Semantic Scholar / arXiv 给的是 given-first
  （`Yann LeCun`），于是把名当成了姓。后果是任何一条**完全正确**的引用只要在这些源命中
  就落 `METADATA_MISMATCH`，`VERIFIED` 态在主路径上几乎不可达。改为「姓氏候选集合相交」
  判定：有逗号时逗号前即姓，无逗号时剔除首字母缩写、余下皆为候选——宁可少量漏报，也绝不
  让正确引用误报（PubMed / ERIC 的 family-first 与中文罗马化短姓一并覆盖）。
- **含括号的 DOI 被截断**——DOI 正则把 `)` 排除在字符集外（为避开尾随的 `(2020)`），
  但合法 DOI 可含成对括号：Lancet / Elsevier 老式 `10.1016/S0140-6736(97)11096-0` 被截成
  `10.1016/S0140-6736(97`，查不到，于是真实文献落「未找到（疑似不存在）」——把真文献误指
  为假，比漏检更坏。改为允许括号进入字符集，再回退尾部不成对的右括号。
- **APA 缩写写法让标题解析切在人名中间**——`A. J.` 这种点后带空格的缩写会让作者段与标题段
  的句号切分提前命中，`Wakefield, A. J., Murch, S. H., …` 解析出 `title='J., Murch, S'`，
  正确引用于是误报标题与作者双双不符。改为优先按 APA 的 `(年份).` 锚点切分，无此锚点时才
  退回原句号路径（GB/T 风格行为不变）。
- **撤稿数据来源不再硬编码**——判定摘要此前一律写「Retraction Watch」，而 OpenAlex 的
  `is_retracted` 并不来自 Retraction Watch。改为如实取自响应，并一并展示撤稿日期
  （硬规则④：降级与出处不美化）。

### 新增（Added）

- **撤稿检测双源冗余**——接入 OpenAlex `is_retracted`，撤稿判定不再单点依赖 Crossref。
  两源都报撤稿时展示信息更全的一条（Crossref 带 Retraction Watch 的撤稿日期与撤稿声明
  DOI），但如实列出全部报告撤稿的源。

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
