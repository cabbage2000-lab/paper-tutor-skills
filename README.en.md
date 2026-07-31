# Paper-Tutor-Skills

![license](https://img.shields.io/badge/license-PolyForm--NC-blue)
![language](https://img.shields.io/badge/language-简体中文优先-green)
![status](https://img.shields.io/badge/status-v0.1.7-blue)
![host](https://img.shields.io/badge/host-Claude%20Code%20%7C%20Codex%20%7C%20WorkBuddy-grey)

[简体中文](README.md) | **English**

Paper-Tutor-Skills is a suite of academic tutoring agent skills for Chinese-speaking researchers, dropped into the coding agent you already use (Claude Code / Codex / WorkBuddy). AI handles efficiency (retrieval, organization, verification, structuring); humans handle research decisions (ideas, judgment, data, conclusions). Designed for Chinese-speaking graduate students and researchers — students self-studying research, instructors mentoring students through research training, and pre-submission batch self-checks (same tool, no behavioral change). Currently at **v0.1.7**: 25 command entry points (`/paper-init`, `/paper-help`, `/paper-doctor`, `/paper-daily` as workspace infrastructure + 21 research commands covering topic / search / writing / review / submission full lifecycle) across 24 skill directories. The authoritative command list and per-command known gaps live in [`skills/_shared/commands.yaml`](skills/_shared/commands.yaml).

## Design Philosophy

**AI provides knowledge, method, and process coaching; Skills provide practice tools; engineering methods help record and review. The final research thinking, judgment, and output remain the learner's own.**

Paper-Tutor-Skills positions AI as a **tutor and coach**, not an executor of research tasks; positions Skills as **learning and practice tools**, not one-click automation for completing research; and brings software-engineering practices — structuring, version control, process audit trails, traceability — into academic research learning, so long-cycle work can be interrupted, resumed, and reviewed. Built on the universal agent skills standard (SKILL.md + references/), not locked to any single host.

**Non-negotiable baseline**: no fabrication (citation verification rests on real API responses, never on model memory); honest audit trails (usage records truthfully reflect the human-AI division of labor, never beautified). This baseline is not traded off against other goals.

## ✅ What it does / ⛔ What it won't do

| ✅ Paper-Tutor-Skills will | ⛔ Paper-Tutor-Skills won't |
| --- | --- |
| Search literature, organize review materials | Generate research ideas or original conclusions |
| Verify whether citations actually exist | Run experiments / code, fabricate data or citations |
| Scaffold a standard research directory | Produce drafts end-to-end without human confirmation |
| Structure outlines, polish language | Help evade AI detection, issue ethical waivers |
| Generate human-machine division-of-labor records | Accept others' manuscripts under review |

"Not writing for you" is not a limitation — it is a commitment to research integrity. Faced with requests like "just write a paper for me," Paper-Tutor-Skills will first empathize with your goal, then explain the risks in your own language, and finally offer a first step with visible results in 5 minutes — set up the directory, organize your materials, start from topic clarification.

## Research Workflow × Paper-Tutor-Skills Capabilities

| Stage | Paper Command | What it does | Status |
| --- | --- | --- | --- |
| **Setup** | `/paper-init` | Scaffold a standard research directory (one round of Q&A, plus a project info config and optional host config file) | ✅ Released |
| **Navigation** | `/paper-help` | Command navigator — find the right paper command for the moment | ✅ Released |
| **Health check** | `/paper-doctor` | Environment readiness check — verify verify/search can run, what's missing, how to fix | ✅ Released |
| **Daily** | `/paper-daily` | Daily research radar — scoop detection + new-release skimming; no scoring, no ranking | ✅ Released |
| **Topic & Proposal** | `/paper-topic` `/paper-search` `/paper-screen` `/paper-method` `/paper-proposal` | Topic clarification, literature search, PRISMA systematic-review screening, research design advice, proposal assembly | ✅ Released |
| **Execution** | —(no command) | Data collection / experiments / analysis are real-world stages left to the human — this is the boundary between "AI handles efficiency, human handles research decisions," not a gap | 🚫 Explicitly not covered |
| **Writing** | `/paper-outline` `/paper-draft` `/paper-logic` `/paper-abstract` `/paper-import` `/paper-figure` `/paper-plot` `/paper-style` | Outline, draft, argument-chain check, abstract, bibliography import, figure diagnosis/design, plotting code generation, style calibration | ✅ Released |
| **Review & Revision** | `/paper-verify` `/paper-format` `/paper-claim` `/paper-review` `/paper-revise` | Citation existence verification, GB/T 7714 format check, overclaim check, simulated review, revision assistance | ✅ Released |
| **Publication & Post-publication** | `/paper-disclose` `/paper-submit` `/paper-typeset` | AI usage disclosure generation, submission preparation, publishing chain (LaTeX / DOCX / PDF + GB/T 7714 citation rendering) | ✅ Released |

## Quick Start

**25 command entry points are released** (v0.1.7), covering the full 5-stage academic research lifecycle; see the table above for the per-command breakdown. You can try one today (`/paper-doctor` has an [acceptance record](tests/paper-doctor/README.md)).

### Installation

**Copy the block below that matches your agent and paste it to them** — the agent does the install; you don't type a single command.

**Install into Claude Code** 👇

```text
Please install the Paper-Tutor-Skills academic tutoring suite for me:

1. Clone https://github.com/cabbage2000-lab/paper-tutor-skills into a temp directory
2. Make sure ~/.claude/skills/ exists (create it if not), then copy **every subdirectory**
   under the repo's skills/ into it — all of them, none left out (24 paper-* plus 1 _shared)
   - Overwrite directories of the same name; that's how updates work
   - Leave every skill from other sources alone — do NOT wipe the directory
   - _shared/ has no SKILL.md and never shows up as a command, but every skill references it
     via ../_shared/, so omitting it breaks all of them; it must be installed too
3. Delete the temp directory
4. Tell me where it landed and which commands are now available
```

**Install into Codex** 👇

```text
Please install the Paper-Tutor-Skills academic tutoring suite for me:

1. Clone https://github.com/cabbage2000-lab/paper-tutor-skills into a temp directory
2. Make sure ~/.codex/skills/ exists (create it if not), then copy **every subdirectory**
   under the repo's skills/ into it — all of them, none left out (24 paper-* plus 1 _shared)
   - Overwrite directories of the same name; that's how updates work
   - Leave every skill from other sources alone — do NOT wipe the directory
   - _shared/ has no SKILL.md and never shows up as a command, but every skill references it
     via ../_shared/, so omitting it breaks all of them; it must be installed too
3. Delete the temp directory
4. Tell me where it landed and which commands are now available
```

**Install into WorkBuddy** 👇

```text
Please install the Paper-Tutor-Skills academic tutoring suite for me:

1. Clone https://github.com/cabbage2000-lab/paper-tutor-skills into a temp directory
2. Make sure ~/.workbuddy/skills/ exists (create it if not), then copy **every subdirectory**
   under the repo's skills/ into it — all of them, none left out (24 paper-* plus 1 _shared)
   - Copy the subdirectories themselves; do NOT nest the whole skills/ folder inside —
     WorkBuddy names skills after their directory path, so one extra level turns the
     commands into skills:paper-init
   - Overwrite directories of the same name; that's how updates work
   - Leave every skill from other sources alone — do NOT wipe the directory
   - _shared/ has no SKILL.md and never shows up as a command, but every skill references it
     via ../_shared/, so omitting it breaks all of them; it must be installed too
3. Delete the temp directory
4. Tell me where it landed and which commands are now available
```

**Start a new session** afterwards — already-open sessions won't pick up the new commands. On WorkBuddy you can also confirm the install in its Skills (技能) panel.

> **Want it in one project only?** Replace the user-level path in the prompt with that project's project-level directory: `.claude/skills/` for Claude Code, `.codex/skills/` for Codex, and **`.codebuddy/skills/` for WorkBuddy** — note that's not `.workbuddy/`: its user-level directory is `~/.workbuddy/`, but the project-level one keeps the underlying CodeBuddy engine's `.codebuddy/`. That asymmetry is a measured finding, and getting it wrong means no commands appear at all.
>
> **On a different host?** Same prompt, just point it at that host's skills directory. Installing to the wrong path means no commands show up at all, with no error to tell you why — the three hosts' directories are **mutually invisible** (**neither Codex nor WorkBuddy reads `.claude/skills/`, and Claude Code does not read `.codex/skills/`**), so using several hosts means installing a copy for each.
>
> **Want to try just one first?** Replace step 2 with "only copy skills/paper-init and skills/_shared".

#### Prefer typing commands yourself? Claude Code and Codex support one-shot plugin installs

This repo is itself a plugin marketplace. The plugin route buys you one thing extra: single-command updates. WorkBuddy takes the prompt route above (this repo does not yet ship a WorkBuddy plugin manifest verified on that host).

Claude Code — run these in a session:

```text
/plugin marketplace add cabbage2000-lab/paper-tutor-skills
/plugin install paper-tutor@paper-tutor-marketplace
```

All 25 commands appear grouped under the `paper-tutor:` prefix (`/paper-tutor:paper-init`, `/paper-tutor:paper-verify`, …). Update with `/plugin update paper-tutor`.

Codex — run these in your terminal:

```bash
codex plugin marketplace add cabbage2000-lab/paper-tutor-skills
codex plugin add paper-tutor@paper-tutor-marketplace
```

Commands appear directly as `/paper-init`, `/paper-verify` (Codex does not prefix them with the plugin name).

Both routes install the same skills — **don't do both**, or you'll end up with two copies and duplicated commands. The plugin form only changes how commands are displayed; the plain `skills/` layout is untouched, so loading on other hosts is unaffected.

### Try it in 30 seconds

After installation, create an empty directory anywhere and tell your AI assistant:

> Use /paper-init to help me set up a research directory

It will ask you four questions in one go:

1. **Project name** (becomes the directory name, e.g. "The impact of ChatGPT on undergraduate writing efficiency")
2. **Scope** (just this one project, or a multi-project workspace)
3. **Location** (defaults to the current directory)
4. **Whether to use git version control** (defaults to yes)

After you confirm the plan, it only creates the directory skeleton + README + .gitignore — never pre-creating the trace directory or generating any research content. After subsequent commands are released, the trace directory `.paper/` will be created automatically on your first use.

## How to ask: example prompts by research stage

**You don't need to memorize command names.** Say where you're stuck in your own words and the host will match the right skill; if you have no idea which one to use, just ask `/paper-help` — one round of questions and it locates you (reply "show me what I've used" and it scans `.paper/` for a full research overview). You can of course also invoke a command name explicitly, e.g. `/paper-verify` — both routes are equivalent.

> **Asking is the opening move, not a one-shot exchange.** Every command first asks about your situation, then stops at checkpoints for your call, and writes nothing to disk before you confirm. Research decisions stay with you — what you get back are options, facts, side-by-side comparisons, and questions, not answers. Spanning days or sessions is fine: the `.paper/` audit trail lets every stage resume in a fresh session.

Prompts below are shown in Chinese (with English glosses) because the suite is Chinese-first — the phrasing is what a Chinese-speaking graduate student would actually type.

### Getting started & daily use (cross-stage infrastructure, usable anytime)

| What you'd say | Lands on | What you get |
| --- | --- | --- |
| "帮我建个放论文材料的文件夹" (set up a folder for my paper materials) / "新开一个课题，目录怎么摆才规范" | `/paper-init` | Standard research directory skeleton + README + `.gitignore` + `project.paper.yaml` (project long-term memory) |
| "Paper 都能干什么" (what can Paper do) / "我想写论文但不知道从哪开始" / "我用到哪一步了" | `/paper-help` | 1–3 best-matching commands + why each; or a stage-grouped research overview |
| "为什么核验跑不起来" (why won't verification run) / "这些数据源通不通、要不要配 key" | `/paper-doctor` | Five-dimension readiness report (runtime / data sources / network / credentials / cache) + what's missing and how to fix it |
| "我这个 idea 被人抢发了吗" (has someone scooped my idea) / "今天 arXiv 这方向有什么新论文" | `/paper-daily` | Scoop check + new-release skim digest (HTML+MD+JSON); gives high/medium/low relevance labels but no scoring, no ranking |

### Stage A · Topic & proposal

| What you'd say | Lands on | What you get |
| --- | --- | --- |
| "我想研究 AI 和教育，但不知道具体做什么" (I want to study AI and education but can't pin down what) / "我这个题你看行不行" | `/paper-topic` | Layer-by-layer options that are objectively common in that field (no recommending, no ranking; every set ends with "none of these, let me say it myself") → the RQ **you** settled on + a process report |
| "有没有人研究过 X" (has anyone studied X) / "这方向国内外做到哪一步了" / "帮我搜搜文献" | `/paper-search` | `literature/文献笔记表.md` + a search log; every run declares each source's coverage method (auto-retrieved / filled in by you / not covered) |
| "这批文献怎么筛" (how do I screen this batch) / "纳排标准怎么定" / "PRISMA 流程图的数字对不上" | `/paper-screen` | Two-round screening ledger + a PRISMA flow diagram that passed count-conservation checks + data-extraction table skeleton (include/exclude is your call, paper by paper) |
| "问卷能回答我的问题吗" (can a survey answer my question) / "方法怎么选" / "我的研究需要伦理审查吗" | `/paper-method` | Method–RQ match dimensions, or common method families for that direction; human subjects trigger a mandatory six-item ethics-review checklist (institutional confirmation required) |
| "我要开题了，报告怎么组" (my proposal defense is coming up) / "选题依据这节怎么写" | `/paper-proposal` | Proposal skeleton following Chinese degree-thesis institutional sections + excerpts pulled from your real topic/search/method outputs (research content, novelty claims left as placeholders for you) |

### Stage B · Doing the research: **no commands here**

Data collection, experiments, and analysis are physical-world stages, explicitly left to you. So "帮我跑个实验" (run an experiment for me) or "帮我编一组数据凑结论" (make up data to fit my conclusion) gets turned down — that's the "AI handles efficiency, human handles research decisions" boundary, not a gap.

### Stage C · Writing

| What you'd say | Lands on | What you get |
| --- | --- | --- |
| "论文分几章好" (how many chapters) / "帮我把大纲列一下" / "帮我想想结构" | `/paper-outline` | Chapter outline draft with literature anchors, chapter by chapter for you to approve; points with no note backing are marked "⚠️ structural placeholder only" |
| "这段引言写不下去" (I'm stuck on this intro paragraph) / "基于大纲帮我展开方法这一段" | `/paper-draft` | Paragraph-level first drafts, each anchored to real notes where possible and flagged ⚠️ where not; you can paste 1–2 paragraphs of your own writing as a style sample (style only, never content) |
| "这几章读着不像一个人写的" (these chapters don't read like one author) / "我的句子是不是太长了" / "被 AIGC 判成 AI 生成要申诉" | `/paper-style` | Six feature groups computed mechanically by script + cross-chapter deviations ranked by coefficient of variation; can be saved as `风格基线.md` for `/paper-draft` to reuse |
| "RQ 和结论对得上吗" (do my RQ and conclusion line up) / "我的论证有没有漏" / "方法能不能回答我的问题" | `/paper-logic` | RQ→method→results→conclusion structural correspondence, laid out (structure only, not content truth; verdict words like "broken / weak" are forbidden) |
| "帮我从正文提炼摘要" (distill an abstract from my body text) / "关键词选几个" | `/paper-abstract` | Abstract draft where every sentence traces back to a body-text source; sentences are newly generated by AI, disclosed at the top as "sentence-generation level" |
| "知网导出的题录帮我整理进来" (import my CNKI records) / "核对下题录和草稿引用对不对得上" | `/paper-import` | Records organized into the notes table + a records-vs-draft consistency report (lays out correspondences only; existence checking belongs to `/paper-verify`) |
| "我该画什么图" (what chart should I use) / "帮我看看这张图有什么问题" / "配色怎么选才色盲友好" | `/paper-figure` | Five-dimension diagnosis, or five-component design advice (chart type / caption / palette / axes / tooling), with hex values and palette provenance |
| "给我一个画柱状图的 matplotlib 脚本" (give me a matplotlib script for a bar chart) / "帮我写段代码画箱线图" | `/paper-plot` | Runnable `.py` / `.R` code (v1.0 covers 7 chart types × matplotlib/ggplot2); without real pasted data it always uses `PAPER_PLACEHOLDER` |

### Stage D · Review & revision

| What you'd say | Lands on | What you get |
| --- | --- | --- |
| "这些参考文献是真的吗" (are these references real) / "投稿前帮我自查一下引用" / "这条 DOI 能查到吗" | `/paper-verify` | Per-citation six-state result (verified / metadata mismatch / retracted / not found / unverified / pending manual), grounded in real API responses; Chinese literature always lands in pending-manual with a verification package, never flagged as suspected fabrication |
| "参考文献格式符合国标吗" (do my references meet the national standard) | `/paper-format` (built into verify) | Per-entry GB/T 7714-2015 citation-format issues (pure rule-based) |
| "我的结论有没有说过头" (am I overclaiming) | `/paper-claim` (built into verify) | Conclusion-vs-results side-by-side; the comparison only, no verdict |
| "审稿人会提什么意见" (what will reviewers raise) / "盲审会挂吗" / "答辩委员可能追问什么" | `/paper-review` | Simulated comments from three perspectives (journal review / thesis blind review / defense committee) + per-dimension scores (simulated common dimensions, not a "publishable" judgment). It asks about manuscript provenance first — **someone else's manuscript that you hold as a reviewer is refused outright** |
| "这些审稿意见怎么回" (how do I respond to these comments) / "逐点回复怎么写" / "改稿建议" | `/paper-revise` | Revision-suggestion comparison table + point-by-point response letter draft; every item marked ❓ for you to accept or decline |

### Stage E · Publication & post-publication

| What you'd say | Lands on | What you get |
| --- | --- | --- |
| "要交一份 AI 使用说明" (I need to submit an AI usage statement) / "列一下我到底用了哪些 AI" | `/paper-disclose` | A disclosure compiled by the four assistance levels (ideation / outline structure / sentence generation / language polish), read only from real `.paper/` traces with missing levels marked; switchable across four audiences (advisor / graduate school / journal / AIGC detection) |
| "投稿要交什么材料" (what do I need for submission) / "这个期刊要什么" / "cover letter 怎么写" | `/paper-submit` | Submission checklist + requirement categories common to that class of journal + cover-letter talking-point skeleton (no fabricated impact factors, no picking the journal for you) |
| "投稿要 Word 版" (the journal wants a Word version) / "帮我转成 LaTeX" / "参考文献要按国标渲染" | `/paper-typeset` | `.docx` / `.tex` / `.pdf` artifacts + a conversion record (swaps the container without changing a single character; if pandoc / xelatex is missing you get the four-part fallback — what wasn't produced, why, install guidance, and the exact command to run by hand — never a faked artifact) |

### Prompts that get turned down — each with an exit route

| What you might ask | Why not | Where it points you |
| --- | --- | --- |
| "直接帮我写一篇关于 X 的论文" (just write me a paper on X) | Ghostwritten text won't survive defense questioning or integrity checks, and authorship responsibility stays yours | → Start with `/paper-topic`, or outline via `/paper-outline` and co-write section by section with `/paper-draft` |
| "帮我编几条参考文献凑数" (make up a few references) / "帮我编一组数据" | Fabricating citations and data is research misconduct | → Real retrieval via `/paper-search`; data is yours to collect (Stage B belongs to you) |
| "帮我降 AI 率" (lower my AI-detection score) / "改到检测不出来" / "帮我查重降重" | Wrong direction — this suite helps you disclose honestly, not hide | → `/paper-disclose` for an AI usage statement; `/paper-style` for false-positive appeal evidence; plagiarism checking goes through your institution's official channel |
| "我这研究应该不用伦理审查吧" (I probably don't need ethics review, right?) | Ethics review must go through an institutional IRB; AI issues no waivers | → `/paper-method` gives the six-item checklist; approval goes through your institution's proper channel |
| "帮我评一下这份我在审的稿子" (review this manuscript I'm refereeing) | Violates peer-review confidentiality | → `/paper-review` only reviews your own manuscript or your students' |
| "哪个方向更值得做" (which direction is more worth doing) / "哪篇最重要" / "给我的论文打个分" | Research value judgments are yours | → Commands lay out objectively common options and cues, then hand the judgment back to you as a question |

### End to end: what a project's questions look like

```text
 1. "set up a project directory"                                  → /paper-init
 2. "I want to study short video's effect on teen attention,
     but can't pin down what exactly"                             → /paper-topic   (you settle the RQ)
 3. "has anyone studied this?"                                    → /paper-search  (notes table)
 4. "how do I screen this batch?"                                 → /paper-screen  (only for systematic reviews)
 5. "can a survey answer my RQ? minors involved — ethics review?" → /paper-method
 6. "my proposal defense is coming up"                            → /paper-proposal
 ── collecting data, running experiments, analysis: AI stays out; this part is yours ──
 7. "how many chapters?"                                          → /paper-outline
 8. "stuck on this methods paragraph"                             → /paper-draft
 9. "do my RQ and conclusion line up?"                            → /paper-logic
10. "distill an abstract"                                         → /paper-abstract
11. "are these citations real / GB/T compliant / overclaimed?"     → /paper-verify (incl. format / claim)
12. "what will reviewers raise?"                                  → /paper-review
13. "comments are in — how do I respond point by point?"          → /paper-revise
14. "AI usage statement" / "what to submit" / "Word version"      → /paper-disclose → /paper-submit → /paper-typeset
```

Each step can be its own session — the traces in `.paper/` carry the context forward, so you never have to cram a whole project into one conversation.

## Why it's trustworthy

Paper-Tutor-Skills has baked its research integrity commitments into verifiable engineering design:

- **Six verification states**: Each citation's verification result is one of six states — VERIFIED, METADATA_MISMATCH, RETRACTED, NOT_FOUND, UNVERIFIED, PENDING_MANUAL. Positioned as **existence verification** (existence ≠ appropriate citation), based on real API responses, never on model memory.

  > Quantitative thresholds (fabrication detection rate, real-citation false positive rate, Chinese-literature false harm, etc.) are not currently part of the required release gate — they are run on demand and backfilled into [`evals/`](evals/README.md). However, "real API responses as the sole source of truth, never model memory" is a product baseline that is never traded off.
- **Bilingual (CN/EN) search**: English literature is automatically retrieved via open APIs (arXiv, OpenAlex, Semantic Scholar, Crossref); Chinese literature takes a "automatic + guided" hybrid path — **Chinese journal articles with DOIs get their records fetched automatically via DOI content negotiation** (title / authors / journal / volume-issue-pages / abstract, available for ISTIC-registered Chinese core journals; DOIs registered by CNKI itself return no record and fall back to manual checking), while the rest get structured CNKI / Wanfang search plans (query expressions + filter conditions) for you to execute and fill in, or you can use the sites' own "export citation" feature and have the export parsed into the table automatically. **Search output declares the coverage method of each source** (automatic / filled-in / not covered) — without this notice, you might mistake "not in English databases" for "no one has studied this." Chinese literature that APIs cannot reach is never flagged as fabricated — it falls into PENDING_MANUAL with a manual verification package attached.
- **No host lock-in**: The implementation does not depend on any host-specific mechanism; orchestration and checkpoint resumption use pure file conventions. Directory conventions are an enhancement, not a dependency — if a standard directory is detected, outputs go to their proper places; otherwise they land in the current directory with a notice.

## Repository structure

Four areas: `skills/` (skill packages + `_shared/` shared layer, [development spec](skills/README.md)), `tests/` ([behavioral acceptance and corpus](tests/README.md)), `evals/` ([bare model vs. with-skill side-by-side comparison](evals/README.md)), `docs/` ([product PRD](docs/prd/paper-tutor-skills-prd-v1.md), in Chinese, and a [full-workflow example](docs/examples/学术论文全流程示例.md)). Other design documents (specs, implementation plans, review records) are internal drafts, not published with the repo — **this README and the PRD are the source of truth for public information**.

## Contributing

To participate in development or customization, first read the development spec in [skills/README.md](skills/README.md) (skill package standard structure, release gate, cross-cutting requirements) and [CONTRIBUTING.md](CONTRIBUTING.md). The release gate has three items: unit tests on core deterministic logic pass, at least one happy path manually walked through with real input, and `commands.yaml`'s `status` flipped in the same commit. Quantitative thresholds, multi-scenario behavioral acceptance, and bare-model comparison are not required — run them on demand.

## License

This project is licensed under the **PolyForm Noncommercial License 1.0** — the source is fully open, permitting personal study, research, teaching, non-commercial distribution, and modification, **but prohibiting any commercial use** (including but not limited to selling, bundling into paid products, commercial service integration). Full license text in the [LICENSE](LICENSE) file at the repository root, or at [PolyForm](https://polyformproject.org/licenses/noncommercial/1.0.0/).
