# 安全策略

## 报告漏洞

如果你发现安全漏洞，请**不要**在公开 issue 中提交。请使用 GitHub 的私密漏洞报告功能：

仓库 → Security → Report a vulnerability

我们会尽快确认收到并跟进。在修复发布前，请勿公开披露漏洞细节。

## 支持的版本

当前版本 **v0.1.1**（2026-07-28）。安全修复只针对最新 `main` 分支——不为历史版本回补，请先升到最新。

## 报告范围

Paper-Tutor-Skills 是一组 agent skills（提示词 + Python 脚本），调用公开学术 API（arXiv、OpenAlex、Semantic Scholar、Crossref、PubMed、ERIC）。以下属于安全范围：

- 可能导致用户数据泄露或被篡改的缺陷。
- 调用外部 API 时的注入或信息泄露风险。
- skill 提示词可能被利用绕过"副手不代笔"边界的情况。

以下**不属于**安全范围：

- API 本身的可用性或限流问题（请向对应 API 提供方报告）。
- 本地使用时用户自行修改 skill 行为导致的问题。
