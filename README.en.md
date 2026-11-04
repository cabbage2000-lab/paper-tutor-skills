# Paper-Tutor-Skills

![license](https://img.shields.io/badge/license-PolyForm--NC-blue)
![language](https://img.shields.io/badge/language-简体中文优先-green)
![status](https://img.shields.io/badge/status-v0.2.0-blue)
![host](https://img.shields.io/badge/host-Claude%20Code%20%7C%20Codex%20%7C%20WorkBuddy-grey)

[简体中文](README.md) | **English**

Paper-Tutor-Skills is an academic tutoring skill suite for researchers. Current version: **v0.2.0**. This release consolidates the suite into **5 command entry points** across 5 skill directories: one setup/navigation entry and 4 research commands. Existing capabilities remain internal workflows. See the authoritative [public registry](skills/_shared/commands.yaml).

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
| Show open-access status and legal access routes | Provide paywall-circumvention routes |

"Not writing for you" is not a limitation — it is a commitment to research integrity. Faced with requests like "just write a paper for me," Paper-Tutor-Skills will first empathize with your goal, then explain the risks in your own language, and finally offer a first step with visible results in 5 minutes — set up the directory, organize your materials, start from topic clarification.

## Five entry points

| Command | Purpose | Example |
| --- | --- | --- |
| `/paper-help` | Get started, create a project, inspect progress, diagnose the environment | Help me set up a research folder |
| `/paper-research` | Topics, search/import/screen literature, daily tracking, methods, proposals | Find recent literature for my research question |
| `/paper-write` | Outlines, paragraph drafting, abstracts, style, figures and plotting code | Build an introduction outline from my notes |
| `/paper-check` | Citations, reference format, arguments, claims, simulated review, revision replies | Verify this manuscript’s references |
| `/paper-submit` | Submission preparation, AI disclosure, Word/LaTeX/PDF exports | Export my existing manuscript to Word |

Describe the task in natural language after an entry point, or simply describe your need. These are not fixed mode arguments or another menu of subcommands. Clear requests enter the relevant workflow immediately; ambiguous requests receive a short clarification. Research decisions and existing confirmation checkpoints remain with you. Literature-support completion remains in development.

## Quick Start

**5 command entry points** (v0.2.0). Start with `/paper-help Help me create a research project`.

### Install or upgrade

Clone this repository into a temporary folder, then run from its root:

```bash
python3 scripts/install_skills.py --target ~/.codex/skills --dry-run
python3 scripts/install_skills.py --target ~/.codex/skills
```

| Host | User skills | Project skills |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex | `~/.codex/skills/` | `.codex/skills/` |
| WorkBuddy | `~/.workbuddy/skills/` | `.codebuddy/skills/` |

Install the entire bundle, including internal workflow directories and `_shared`. Only 5 paper-* directories contain `SKILL.md`; the remaining directories provide dependencies. The installer checks ownership before writing, moves replaced package directories into `.paper-tutor-backups/` beside the target skills directory, and preserves unrelated skills. Conflicting directories cause an error before mutation. The backup path is printed.

Do not upgrade by merging folders: obsolete `SKILL.md` files would survive and keep the old menu entries visible. Restart the session after upgrading. Old shortcuts are no longer registered; use a new entry point with a natural-language request. Research files and `.paper/` records require no migration.

Existing Claude Code and Codex plugin manifests remain supported. Plugin users should update through their host’s plugin management, without running the directory installer on plugin caches. Do not combine plugin and directory installs. Claude Code plugin commands may include the namespace, for example `/paper-tutor:paper-check`.

Plugin installation commands (choose your host):

```text
# In a Claude Code session
/plugin marketplace add cabbage2000-lab/paper-tutor-skills
/plugin install paper-tutor@paper-tutor-marketplace

# In a terminal for Codex
codex plugin marketplace add cabbage2000-lab/paper-tutor-skills
codex plugin add paper-tutor@paper-tutor-marketplace
```

### Example requests

- `/paper-research Import this bibliography and compare it with my draft citations`.
- `/paper-write Extract an abstract from this manuscript`.
- `/paper-check Check reference formatting only`.
- `/paper-check Help organize these reviewer comments and draft point-by-point replies`.
- `/paper-submit Build an AI disclosure from my actual usage records`.

See the [consolidation design](docs/command-consolidation.md) for mapping and compatibility details.

## Why it's trustworthy

Paper-Tutor-Skills has baked its research integrity commitments into verifiable engineering design:

- **Six verification states**: Each citation's verification result is one of six states — VERIFIED, METADATA_MISMATCH, RETRACTED, NOT_FOUND, UNVERIFIED, PENDING_MANUAL. Positioned as **existence verification** (existence ≠ appropriate citation), based on real API responses, never on model memory.

  > Quantitative thresholds (fabrication detection rate, real-citation false positive rate, Chinese-literature false harm, etc.) are not currently part of the required release gate — they are run on demand and backfilled into [`evals/`](evals/README.md). However, "real API responses as the sole source of truth, never model memory" is a product baseline that is never traded off.
- **Bilingual (CN/EN) search**: English literature is automatically retrieved via open APIs (arXiv, OpenAlex, Semantic Scholar, Crossref); Chinese literature takes a "automatic + guided" hybrid path — **Chinese journal articles with DOIs get their records fetched automatically via DOI content negotiation** (title / authors / journal / volume-issue-pages / abstract, available for ISTIC-registered Chinese core journals; DOIs registered by CNKI itself return no record and fall back to manual checking), while the rest get structured CNKI / Wanfang search plans (query expressions + filter conditions) for you to execute and fill in, or you can use the sites' own "export citation" feature and have the export parsed into the table automatically. **Search output declares the coverage method of each source** (automatic / filled-in / not covered) — without this notice, you might mistake "not in English databases" for "no one has studied this." Chinese literature that APIs cannot reach is never flagged as fabricated — it falls into PENDING_MANUAL with a manual verification package attached.
- **No host lock-in**: The implementation does not depend on any host-specific mechanism; orchestration and checkpoint resumption use pure file conventions. Directory conventions are an enhancement, not a dependency — if a standard directory is detected, outputs go to their proper places; otherwise they land in the current directory with a notice.

## Repository structure

Four areas: `skills/` (skill packages + `_shared/` shared layer, [development spec](skills/README.md)), `tests/` ([behavioral acceptance and corpus](tests/README.md)), `evals/` ([bare model vs. with-skill side-by-side comparison](evals/README.md)), `docs/` ([product PRD](docs/prd/paper-tutor-skills-prd-v1.md), in Chinese, and a [full-workflow example](docs/examples/学术论文全流程示例.md)). Other design documents (specs, implementation plans, review records) are internal drafts, not published with the repo — **this README and the PRD are the source of truth for public information**.

## Contributing

To participate in development or customization, first read the development spec in [skills/README.md](skills/README.md) (skill package standard structure, release gate, cross-cutting requirements) and [CONTRIBUTING.md](CONTRIBUTING.md). The release gate has three items: unit tests on core deterministic logic pass, at least one happy path manually walked through with real input, and the internal `workflows.yaml` capability's `status` flipped in the same commit. Quantitative thresholds, multi-scenario behavioral acceptance, and bare-model comparison are not required — run them on demand.

## License

This project is licensed under the **PolyForm Noncommercial License 1.0** — the source is fully open, permitting personal study, research, teaching, non-commercial distribution, and modification, **but prohibiting any commercial use** (including but not limited to selling, bundling into paid products, commercial service integration). Full license text in the [LICENSE](LICENSE) file at the repository root, or at [PolyForm](https://polyformproject.org/licenses/noncommercial/1.0.0/).
