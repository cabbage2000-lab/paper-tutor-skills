#!/usr/bin/env python3
"""paper-verify 核验报告 HTML 视图（payload → 单文件 HTML）。

定位同 `report.build_markdown`：纯渲染、无网络、无判定——输入是 verify.py 组装好的
同一份 payload，六态、证据链、出口指引一字不改地投影到 HTML，不产生任何研究内容。
六态标签与优先关注集合 import 自 `report`，不在此处重复定义（改一处即两版同步）。

**文件名不叫 render_html**（别「统一」回去）：paper-search/scripts/render_html.py 已占用
该模块名，两个 skill 的 scripts 目录都靠 sys.path 插入 + 顶层 import，同进程（pytest 全量
跑）时后者会被 sys.modules 缓存顶替，报 `has no attribute` ——改名是修这个冲突的根因。

**样式走 Tailwind CDN + 内联 config**（与 13 个提示词型模板 skill 同一技术栈）：
`<head>` 引 `cdn.tailwindcss.com?plugins=typography`，紧跟一段**原样读入**
`_shared/tailwind.config.js` 的内联 script——产物落在用户项目的 `.paper/review/` 后，
相对路径 `../../_shared/tailwind.config.js` 指不到 skill 包（那是路径问题、与有无网络无关），
故必须内联；内联时把 `</` 转义成 `<\\/`，否则 config 注释里的 `</script>` 会提前闭合标签、
让整份 config 静默失效（实测踩过）。原样读入而非复制一份，四层语义色仍是单一事实来源
（改 `_shared/tailwind.config.js` 即改本报告）。

样式表用 `<style type="text/tailwindcss">`：`:root` 的色/字栈变量由 `theme()` 派生，
其余规则照常写 `var(--l4)`，故 CSS 与组件库的 class 命名（`_shared/references/报告组件库.md`
§0.1 路径 B）保持一致。**CDN 依赖声明**：断网时 Tailwind 未加载 → 该样式块不被应用 →
产物降级为无样式 HTML（内容仍可读、排版失效），与 13 个模板同一折衷。

**为什么不套四层内容标注**：本报告是六态核验结果陈列，「来源」维度退化为「核验状态」
维度——同 paper-import 用 `.st` 状态徽章族替代四层符号的先例（四层内容标注.md §不适用的场景）。

阅读体验（本模块的产品目标——40 条报告里 3 秒定位到要动手的条目）：
  裁决横幅（几条要动手）→ 六态堆叠条 → 需优先关注卡片（锚点直达）
  → sticky 六态筛选器（只看已撤稿）→ 逐条卡片（DOI 可点、证据链折叠、核对词可复制）
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import sys
from typing import Any, Dict, List
from urllib.parse import quote

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import report  # noqa: E402

# 六态 → 视觉档（CSS class 后缀）。语义依据（报告组件库 §1.2 / §1.4）：
#   ok  绿  = 已核实（.badge.green 同色值）
#   l4  砖红 = 待用户处理（疑似不存在 / 已撤稿——撤稿用实心加重，投稿前必处理）
#   l2  赭石 = 事实差异陈列（元数据不符，摆对照不判对错）
#   l1  靛蓝 = 需人的劳动（待人工核对——人去知网查，靛蓝是「人」那一层的色）
#   ink 灰   = 没查成（无法核实，与「查了没有」如实区分）
STATUS_TONE = {
    "VERIFIED": "ok",
    "METADATA_MISMATCH": "l2",
    "RETRACTED": "l4solid",
    "NOT_FOUND": "l4",
    "UNVERIFIED": "gray",
    "PENDING_MANUAL": "l1",
}
# 每态一句「意味着什么」——只陈述查证结果与用户下一步，不指控动机（红线 1）
STATUS_MEANING = {
    "VERIFIED": "在开放 API 找到，且 DOI / 年份 / 标题 / 第一作者姓关键字段一致。",
    "METADATA_MISMATCH": "文献存在，但引用里的某些字段与源不一致——核对是否抄写有误。",
    "RETRACTED": "源数据标记该文已撤稿。投稿前必处理：替换或在文中说明撤稿情况。",
    "NOT_FOUND": "DOI 注册机构自证其不存在（查无此文）。可能是抄写错误、未注册预印本，"
                 "也可能是不存在的条目——如何处理由你判断。",
    "UNVERIFIED": "没查成（网络 / 超时 / 退避耗尽），不是「查了没有」。网络恢复后重跑。",
    "PENDING_MANUAL": "开放 API 未覆盖（中文库文献、无 DOI、解析失败等），需去知网 / 万方人工核对。"
                      "英文库查不到不等于不存在。",
}
# 人工核对入口（与 report.py 的 Markdown 核对包同源，此处渲染为可点击链接）
MANUAL_PORTALS = [
    ("知网高级检索", "https://kns.cnki.net/kns8/AdvSearch"),
    ("万方检索", "https://www.wanfangdata.com.cn/index.html"),
]

TAILWIND_CDN = "https://cdn.tailwindcss.com?plugins=typography"
# 共享设计 token 的权威文件（原样内联进产物，不在此处复制色值）
TAILWIND_CONFIG = pathlib.Path(__file__).resolve().parents[2] / "_shared" / "tailwind.config.js"

# 色与字栈全部由 theme() 从内联 config 派生——四层语义色的唯一来源是
# _shared/tailwind.config.js（产品死线）。红黄绿三档是「对应度」视觉编码、
# 非语义色，按组件库 §1.4 就地内联。
_CSS = """
:root{
  --paper:theme('colors.paper');--paper-edge:theme('colors.paper-edge');
  --rule:theme('colors.rule');
  --ink:theme('colors.ink.DEFAULT');--ink-soft:theme('colors.ink.soft');
  --ink-faint:theme('colors.ink.faint');
  --l1:theme('colors.l1.DEFAULT');--l1-bg:theme('colors.l1.bg');
  --l2:theme('colors.l2.DEFAULT');--l2-bg:theme('colors.l2.bg');
  --l3:theme('colors.l3.DEFAULT');--l3-bg:theme('colors.l3.bg');
  --l4:theme('colors.l4.DEFAULT');--l4-bg:theme('colors.l4.bg');
  --ok:#2f4a1c;--ok-bg:#d8e6c6;--ok-edge:#a8c08e;
  --serif:theme('fontFamily.serif');
  --sans:theme('fontFamily.sans');
}
*{box-sizing:border-box}
body{
  margin:0;background-color:var(--paper);color:var(--ink);
  font-family:var(--serif);font-size:16px;line-height:1.85;
  -webkit-font-smoothing:antialiased;
  background-image:linear-gradient(var(--paper-edge) 1px,transparent 1px),
    linear-gradient(90deg,var(--paper-edge) 1px,transparent 1px);
  background-size:28px 28px;background-position:-1px -1px;
}
.page{
  position:relative;max-width:880px;margin:3rem auto 5rem;padding:0 4rem 3.5rem;
  background:var(--paper);border:1px solid var(--rule);border-top:6px solid var(--ink);
  box-shadow:0 1px 0 var(--paper-edge),0 30px 60px -30px rgba(60,45,20,.25);
}
.page::before{
  content:"paper-verify · 引用核验档案";position:absolute;top:-6px;right:0;
  background:var(--ink);color:var(--paper);font-family:var(--sans);
  font-size:10px;letter-spacing:.14em;text-transform:uppercase;
  padding:5px 12px 4px;font-weight:600;
}
/* 有 JS 时档案标签移入 sticky 轨（否则被轨的背景遮住），无 JS 时留在页角 */
.js .page::before{display:none}
h1,h2,h3{font-family:var(--sans)}
a{color:var(--l1);text-decoration:underline;text-underline-offset:2px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.86em}

/* ── sticky 六态筛选轨（仅 JS 可用时显示——无 JS 时不摆无效控件） ── */
.railbar{display:none}
.js .railbar{
  display:flex;flex-wrap:wrap;align-items:center;gap:.5rem;
  position:sticky;top:0;z-index:20;margin:0 -4rem;padding:.65rem 1.5rem;
  background:rgba(246,242,234,.94);backdrop-filter:blur(6px);
  border-bottom:1px solid var(--rule);
  opacity:1!important;transform:none!important;animation:none!important;
}
.rail-brand{background:var(--ink);color:var(--paper);font-family:var(--sans);
  font-size:10px;letter-spacing:.14em;text-transform:uppercase;font-weight:600;
  padding:4px 10px 3px;margin-right:.3rem;white-space:nowrap}
.rail-label{font-family:var(--sans);font-size:10px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--ink-faint);margin-right:.2rem}
.chip{position:relative;display:inline-flex}
.chip input{position:absolute;inset:0;opacity:0;cursor:pointer;margin:0}
.chip span{
  display:inline-block;padding:.2rem .6rem;border-radius:2px;cursor:pointer;
  font-family:var(--sans);font-size:.8rem;font-weight:600;white-space:nowrap;
  border:1px solid var(--rule);color:var(--ink-soft);background:rgba(255,255,255,.5);
  transition:opacity .15s,background .15s;
}
.chip input:checked + span{outline:2px solid var(--ink);outline-offset:-1px}
.chip input:focus-visible + span{outline:2px solid var(--l1);outline-offset:2px}
.chip.t-ok span{background:var(--ok-bg);color:var(--ok);border-color:var(--ok-edge)}
.chip.t-l2 span{background:var(--l2-bg);color:var(--l2);border-color:var(--l2)}
.chip.t-l4 span,.chip.t-l4solid span{background:var(--l4-bg);color:var(--l4);border-color:var(--l4)}
.chip.t-l1 span{background:var(--l1-bg);color:var(--l1);border-color:var(--l1)}
.chip.t-gray span{background:#efece4;color:var(--ink-faint);border-color:var(--ink-faint)}
.rail-count{margin-left:auto;font-family:var(--sans);font-size:.78rem;color:var(--ink-faint)}
.rail-reset{font-family:var(--sans);font-size:.78rem;background:none;border:none;
  color:var(--l1);cursor:pointer;text-decoration:underline;padding:0}

/* ── 档案头 ── */
.doc-head{margin:2.5rem 0 2.5rem}
.doc-eyebrow{font-family:var(--sans);font-size:11px;letter-spacing:.28em;
  text-transform:uppercase;color:var(--ink-faint);margin-bottom:.6rem}
.doc-title{font-family:var(--serif);font-size:2.1rem;font-weight:700;
  line-height:1.25;margin:0 0 1rem;letter-spacing:.01em}
.doc-meta{display:flex;flex-wrap:wrap;gap:.5rem 1.5rem;padding-top:1rem;
  border-top:1px solid var(--rule);color:var(--ink-soft);font-size:.9rem}
.doc-meta b{color:var(--ink-faint);font-weight:500;margin-right:.4rem}

/* ── 横幅（降级明标 / 裁决） ── */
.banner{padding:1rem 1.25rem;margin:1.25rem 0;border:1px solid;border-left-width:4px;
  font-size:.95rem;line-height:1.75}
.banner-label{display:block;font-family:var(--sans);font-size:10px;font-weight:700;
  letter-spacing:.2em;text-transform:uppercase;margin-bottom:.35rem}
.banner.warn{background:var(--l4-bg);border-color:var(--l4);color:var(--ink)}
.banner.warn .banner-label{color:var(--l4)}
.banner.calm{background:var(--l3-bg);border-color:var(--l3);color:var(--ink)}
.banner.calm .banner-label{color:var(--l3)}
.banner p{margin:.3rem 0 0}
.banner a{font-family:var(--sans);font-size:.85rem}

/* ── 六态堆叠条 + 分布表 ── */
h2.section{font-size:1.05rem;font-weight:700;letter-spacing:.04em;
  margin:2.75rem 0 1.25rem;padding-bottom:.5rem;border-bottom:1px solid var(--rule);
  display:flex;align-items:baseline;justify-content:space-between;gap:1rem}
h2.section .sec-no{font-family:var(--serif);font-style:italic;font-weight:400;
  font-size:.85rem;color:var(--ink-faint);letter-spacing:normal}
.statusbar{display:flex;width:100%;height:28px;margin:.5rem 0 .75rem;
  border:1px solid var(--rule);border-radius:2px;overflow:hidden}
.statusbar .seg{display:flex;align-items:center;justify-content:center;gap:.25rem;
  font-family:var(--sans);font-size:11px;font-weight:700;color:var(--ink);
  white-space:nowrap;overflow:hidden;min-width:0;padding:0 .2rem}
.statusbar .seg + .seg{border-left:1px solid var(--paper)}
.seg.t-ok{background:var(--ok-bg)}
.seg.t-l2{background:var(--l2-bg)}
.seg.t-l4{background:var(--l4-bg)}
.seg.t-l4solid{background:var(--l4);color:var(--paper)}
.seg.t-l1{background:var(--l1-bg)}
.seg.t-gray{background:#e4e0d6;color:var(--ink-soft)}
table{width:100%;border-collapse:collapse;margin:1rem 0;font-size:.92rem}
th,td{border:1px solid var(--rule);padding:.5rem .75rem;text-align:left;
  vertical-align:top;line-height:1.7}
th{background:var(--l2-bg);color:var(--l2);font-family:var(--sans);
  font-size:.88rem;font-weight:700}
td.num{font-family:var(--serif);text-align:right;width:5rem}

/* ── 六态图例 ── */
.legend{margin:1.75rem 0;padding:1rem 1.25rem;background:rgba(255,255,255,.4);
  border:1px dashed var(--rule);font-size:.85rem}
.legend-title{font-family:var(--sans);font-size:10px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--ink-faint);margin-bottom:.5rem}
.legend ul{margin:0;padding:0;list-style:none;display:flex;flex-wrap:wrap;gap:.5rem 1.5rem}
.legend li{color:var(--ink-soft)}
.legend .note{margin-top:.5rem;font-size:.78rem;color:var(--ink-faint)}

/* ── 状态徽章 ── */
.st{display:inline-block;padding:1px 7px;border-radius:2px;font-family:var(--sans);
  font-size:10px;font-weight:700;letter-spacing:.04em;white-space:nowrap}
.st.t-ok{background:var(--ok-bg);color:var(--ok);border:1px solid var(--ok-edge)}
.st.t-l2{background:var(--l2-bg);color:var(--l2);border:1px solid var(--l2)}
.st.t-l4{background:var(--l4-bg);color:var(--l4);border:1px solid var(--l4)}
.st.t-l4solid{background:var(--l4);color:var(--paper);border:1px solid var(--l4)}
.st.t-l1{background:var(--l1-bg);color:var(--l1);border:1px solid var(--l1)}
.st.t-gray{background:#efece4;color:var(--ink-faint);border:1px solid var(--ink-faint)}

/* ── 需优先关注 ── */
.priority{list-style:none;margin:1rem 0;padding:0}
.priority li{padding:.75rem 1rem;margin-bottom:.6rem;background:rgba(255,255,255,.45);
  border:1px solid var(--rule);border-left:3px solid var(--l4);font-size:.95rem}
.priority .pr-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem}
.priority .pr-ref{font-family:var(--sans);font-weight:700;font-size:.9rem}
.priority .pr-jump{margin-left:auto;font-family:var(--sans);font-size:.8rem}
.priority .pr-sum{color:var(--ink-soft);display:block;margin-top:.2rem}

/* ── 逐条卡片 ── */
.ref{border:1px solid var(--rule);border-left:4px solid var(--rule);
  background:rgba(255,255,255,.35);padding:1.1rem 1.35rem;margin:0 0 1.1rem;
  scroll-margin-top:5rem}
.ref.is-hidden{display:none}
.ref.t-ok{border-left-color:var(--ok-edge)}
.ref.t-l2{border-left-color:var(--l2)}
.ref.t-l4,.ref.t-l4solid{border-left-color:var(--l4)}
.ref.t-l1{border-left-color:var(--l1)}
.ref.t-gray{border-left-color:var(--ink-faint)}
.ref.t-l4solid{background:var(--l4-bg)}
.ref-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem;margin-bottom:.5rem}
.ref-id{font-family:var(--sans);font-size:.9rem;font-weight:700;color:var(--ink)}
.ref-doi{margin-left:auto;font-family:var(--sans);font-size:.8rem}
.ref-raw{margin:.4rem 0 .6rem;padding:.5rem .9rem;border-left:3px solid var(--l1);
  background:var(--l1-bg);color:var(--l1);font-size:.92rem;line-height:1.7;
  overflow-wrap:anywhere}
.ref-sum{margin:.5rem 0;font-weight:600}
.ref-parsed{margin:.35rem 0;font-size:.85rem;color:var(--ink-faint);font-family:var(--sans)}
.ref-parsed b{color:var(--ink-soft);font-weight:500;margin-right:.25rem}
.fieldtable{margin:.6rem 0;font-size:.88rem}
.fieldtable td.f-name{font-family:var(--sans);font-weight:600;width:6.5rem;color:var(--ink)}
.fieldtable tr.hint td{color:var(--ink-faint)}
.fieldtable .sev{font-family:var(--sans);font-size:10px;font-weight:700;
  padding:0 5px;border-radius:2px}
.fieldtable .sev.mismatch{background:var(--l4-bg);color:var(--l4);border:1px solid var(--l4)}
.fieldtable .sev.hint{background:var(--l2-bg);color:var(--l2);border:1px solid var(--l2)}
details{margin:.6rem 0;font-size:.9rem}
summary{cursor:pointer;font-family:var(--sans);font-size:.85rem;color:var(--ink-soft);
  padding:.2rem 0;list-style-position:outside}
summary:hover{color:var(--ink)}
details ul{margin:.4rem 0 .2rem;padding-left:1.2rem;color:var(--ink-soft)}
details li{margin:.15rem 0}
.block{margin:.7rem 0;padding:.7rem 1rem;font-size:.9rem;line-height:1.75}
.block-label{display:block;font-family:var(--sans);font-size:10px;font-weight:700;
  letter-spacing:.16em;text-transform:uppercase;margin-bottom:.35rem}
.block.manual{background:var(--l1-bg);border-left:3px solid var(--l1)}
.block.manual .block-label{color:var(--l1)}
.block.guide{background:var(--l3-bg);border-left:3px solid var(--l3)}
.block.guide .block-label{color:var(--l3)}
.block.fmt{background:var(--l2-bg);border-left:3px solid var(--l2)}
.block.fmt .block-label{color:var(--l2)}
.block ul{margin:.2rem 0;padding-left:1.2rem}
.block .clause{font-family:var(--sans);font-size:.8rem;color:var(--ink-faint)}
.querybox{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem;margin:.4rem 0}
.querybox code{background:rgba(255,255,255,.65);border:1px solid var(--rule);
  padding:.2rem .5rem;overflow-wrap:anywhere}
.copybtn{font-family:var(--sans);font-size:.78rem;padding:.2rem .6rem;cursor:pointer;
  background:var(--paper);border:1px solid var(--l1);color:var(--l1);border-radius:2px}
.copybtn:hover{background:var(--l1-bg)}
.copied{font-family:var(--sans);font-size:.78rem;color:var(--l3)}

/* ── 页脚 ── */
footer{margin-top:3.5rem;padding-top:1.25rem;border-top:2px double var(--rule);
  color:var(--ink-soft);font-size:.85rem;line-height:1.7}
footer .seal{font-family:var(--sans);font-size:10px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--ink-faint);margin-bottom:.5rem}
footer p{margin:.35rem 0}
.totop{display:block;text-align:right;font-family:var(--sans);font-size:.8rem;
  margin-top:1rem}

@media (prefers-reduced-motion:no-preference){
  .page > *{opacity:0;transform:translateY(8px);animation:rise .6s ease forwards}
  .page > *:nth-child(1){animation-delay:.03s}
  .page > *:nth-child(2){animation-delay:.09s}
  .page > *:nth-child(3){animation-delay:.15s}
  .page > *:nth-child(4){animation-delay:.21s}
  .page > *:nth-child(5){animation-delay:.27s}
  .page > *:nth-child(6){animation-delay:.33s}
  .page > *:nth-child(n+7){animation-delay:.39s}
  @keyframes rise{to{opacity:1;transform:none}}
}
@media (max-width:760px){
  body{font-size:15px}
  .page{margin:0;padding:0 1.25rem 2rem;border-left:none;border-right:none;max-width:none}
  /* 选择器须与 .js .railbar 同特异性——媒体查询不提升特异性，写 .railbar 会被它压掉 */
  /* 窄屏换行而非横滚——横滚会把后面的筛选项藏起来，导航控件不该藏 */
  .js .railbar{margin:0 -1.25rem;padding:.5rem 1rem;gap:.4rem}
  .js .rail-brand,.js .rail-label{display:none}   /* 窄屏让位给筛选 chip */
  .rail-count{margin-left:.5rem;flex:0 0 auto}
  .doc-title{font-size:1.6rem}
  .ref-doi,.priority .pr-jump{margin-left:0}
  /* 表格重排为卡片：窄屏 4 列表格必然挤压，改行内堆叠且不丢任何一列 */
  .rtable thead{display:none}
  .rtable tr{display:block;border:1px solid var(--rule);margin-bottom:.5rem;
    padding:.5rem .75rem;background:rgba(255,255,255,.4)}
  .rtable td{display:block;border:none;padding:.1rem 0}
  .rtable td.num{text-align:left;width:auto}
  .rtable td[data-label]::before{content:attr(data-label)"：";color:var(--ink-faint);
    font-family:var(--sans);font-size:.8rem}
}
@media print{
  body{background:#fff}
  .page{box-shadow:none;margin:0;max-width:none;border:none;border-top:6px solid #000;padding:0}
  .page::before,.railbar,.copybtn,.totop{display:none!important}
  .page > *{opacity:1!important;transform:none!important;animation:none!important}
  .ref{break-inside:avoid;background:none}
  details > summary ~ *{display:block!important}
  a{text-decoration:none;color:var(--ink)}
}
"""

_JS = """
document.documentElement.classList.add('js');
(function(){
  var boxes=[].slice.call(document.querySelectorAll('.railbar input[type=checkbox]'));
  var cards=[].slice.call(document.querySelectorAll('.ref'));
  var counter=document.getElementById('railCount');
  var reset=document.getElementById('railReset');
  function apply(){
    var on=boxes.filter(function(b){return b.checked;}).map(function(b){return b.value;});
    var shown=0;
    cards.forEach(function(c){
      var hit=on.length===0||on.indexOf(c.dataset.status)>=0;
      c.classList.toggle('is-hidden',!hit);
      if(hit){shown++;}
    });
    if(counter){
      counter.textContent=on.length===0
        ? '共 '+cards.length+' 条'
        : shown+' / '+cards.length+' 条';
    }
    if(reset){reset.hidden=on.length===0;}
  }
  boxes.forEach(function(b){b.addEventListener('change',apply);});
  if(reset){
    reset.addEventListener('click',function(){
      boxes.forEach(function(b){b.checked=false;});
      apply();
    });
  }
  apply();
  // 点「需优先关注」的跳转链接时，若该态被筛掉则先放开筛选，否则跳过去是空的
  document.querySelectorAll('.pr-jump').forEach(function(a){
    a.addEventListener('click',function(){
      var target=document.querySelector(a.getAttribute('href'));
      if(target&&target.classList.contains('is-hidden')){
        boxes.forEach(function(b){b.checked=false;});
        apply();
      }
    });
  });
  // 检索词复制（核对包）：clipboard 不可用时退回手动选中，不吞掉失败
  document.querySelectorAll('.copybtn').forEach(function(btn){
    btn.addEventListener('click',function(){
      var text=btn.dataset.copy||'';
      var tip=btn.nextElementSibling;
      function done(msg){if(tip){tip.textContent=msg;}}
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(function(){done('已复制');},
          function(){done('复制失败，请手动选中');});
      }else{
        done('本环境不支持一键复制，请手动选中');
      }
    });
  });
  // 打印时展开全部证据链（CSS 覆盖 details 不可靠，用事件兜底）
  window.addEventListener('beforeprint',function(){
    document.querySelectorAll('details').forEach(function(d){
      if(!d.open){d.open=true;d.dataset.printed='1';}
    });
  });
  window.addEventListener('afterprint',function(){
    document.querySelectorAll('details[data-printed]').forEach(function(d){
      d.open=false;delete d.dataset.printed;
    });
  });
})();
"""


def _e(text: Any) -> str:
    """转义为 HTML 文本——引用原文、标题、DOI 全部来自用户输入，一律过这道。"""
    return html.escape("" if text is None else str(text))


def _doi_url(doi: str) -> str:
    return "https://doi.org/" + quote(str(doi).strip(), safe="/:;()<>[]_-.")


def _tone(status: str) -> str:
    return STATUS_TONE.get(status, "gray")


def _label(status: str):
    return report.STATUS_LABEL.get(status, ("•", status))


def _inline_tailwind_config() -> str:
    """把 `_shared/tailwind.config.js` 原样读进 `<script>`（不复制色值，只搬运）。

    必须转义 `</`：该文件注释里有 `<script src="../_shared/tailwind.config.js"></script>`
    示例，HTML 解析器不看 JS 注释，遇到 `</script>` 就闭合标签——后半段 config 会变成
    页面文本、config 静默不生效（四层色 class 全失效但页面照样出，很难自查）。
    JS 里 `<\\/` 与 `</` 等价，转义不改语义。
    """
    try:
        cfg = TAILWIND_CONFIG.read_text(encoding="utf-8")
    except OSError:
        # 只有 skill 目录被破坏 / 脚本被单独拷走时到这儿。留可 grep 的注释便于诊断，
        # 不在此处兜一份色值（那就成了第二份真相）。
        return ("<!-- 未找到 _shared/tailwind.config.js：自定义色 class 将回落 Tailwind "
                "默认主题，请检查 skill 目录是否完整 -->")
    return "<script>\n" + cfg.replace("</", r"<\/") + "\n</script>"


def _present_statuses(payload: Dict[str, Any]) -> List[str]:
    """报告里实际出现的态，按六态权威顺序排列（不出现的态不摆空控件）。"""
    by_status = payload.get("stats", {}).get("by_status", {}) or {}
    return [s for s in report.STATUS_ORDER if by_status.get(s)]


def build_html(payload: Dict[str, Any]) -> str:
    """把 JSON payload 渲染成单文件 HTML 报告（Tailwind CDN + 内联 config，见模块说明）。"""
    created = payload.get("created_at", "") or ""
    day = created[:10]
    out: List[str] = [
        "<!DOCTYPE html>", '<html lang="zh-CN">', "<head>", '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>引用核验报告{(' · ' + day) if day else ''}</title>",
        f'<script src="{TAILWIND_CDN}"></script>',
        _inline_tailwind_config(),
        '<style type="text/tailwindcss">' + _CSS + "</style>",
        "</head>", "<body>",
        '<article class="page">',
    ]
    _render_railbar(out, payload)
    _render_head(out, payload)
    _render_network(out, payload)
    _render_verdict(out, payload)
    _render_distribution(out, payload)
    _render_legend(out, payload)
    _render_priority(out, payload)
    _render_sources(out, payload)
    _render_items(out, payload)
    _render_footer(out)
    out += ["</article>", "<script>" + _JS + "</script>", "</body>", "</html>"]
    return "\n".join(out)


def _render_railbar(out, payload):
    """sticky 六态筛选轨——40 条报告里「只看已撤稿」的入口。"""
    statuses = _present_statuses(payload)
    by_status = payload.get("stats", {}).get("by_status", {}) or {}
    total = payload.get("stats", {}).get("total", 0)
    out.append('<nav class="railbar" aria-label="按核验状态筛选">')
    out.append('<span class="rail-brand">paper-verify</span>')
    out.append('<span class="rail-label">筛选</span>')
    for s in statuses:
        emoji, label = _label(s)
        n = by_status.get(s, 0)
        # chip 用完整标签的括号前缀（「未找到（疑似不存在）」→「未找到」）保筛选轨单行；
        # 完整标签挂 title，且在分布表 / 图例 / 每条徽章处一律完整呈现，措辞不新造。
        out.append(
            f'<label class="chip t-{_tone(s)}" title="{_e(label)} {n} 条">'
            f'<input type="checkbox" value="{_e(s)}" aria-label="{_e(label)}">'
            f'<span>{emoji} {_e(label.split("（")[0])} {n}</span></label>'
        )
    out.append(f'<span class="rail-count" id="railCount">共 {total} 条</span>')
    out.append('<button type="button" class="rail-reset" id="railReset" hidden>清除筛选</button>')
    out.append("</nav>")


def _render_head(out, payload):
    stats = payload.get("stats", {}) or {}
    created = payload.get("created_at", "") or ""
    meta = [("日期", created[:10]), ("核验条数", stats.get("total", 0))]
    if stats.get("elapsed_s") is not None:
        meta.append(("耗时", f"{stats['elapsed_s']} 秒"))
    if stats.get("sources_queried"):
        meta.append(("查询源", "、".join(stats["sources_queried"])))
    if payload.get("run_id"):
        meta.append(("批次", payload["run_id"]))
    if payload.get("input_fingerprint"):
        meta.append(("输入指纹", payload["input_fingerprint"]))
    out.append('<header class="doc-head">')
    out.append('<div class="doc-eyebrow">Paper-Verify · 引用核验档案</div>')
    out.append('<h1 class="doc-title">引用存在性核验报告</h1>')
    out.append('<div class="doc-meta">')
    for k, v in meta:
        out.append(f"<span><b>{_e(k)}</b>{_e(v)}</span>")
    out.append("</div></header>")


def _render_network(out, payload):
    """降级明标（核验类 skill 的代码层红线：绝不静默用模型记忆顶替）。"""
    status = payload.get("network_status", "ok")
    banner = report.NETWORK_BANNER.get(status)   # 措辞与 Markdown 版同源，不另写一份
    if not banner:
        return
    title, detail = banner
    out.append('<section class="banner warn" role="alert">')
    out.append(f'<span class="banner-label">⚠️ 降级声明 · network_status={_e(status)}</span>')
    out.append(f"<b>{_e(title)}</b><p>{_e(detail)}</p>")
    out.append("</section>")


def _render_verdict(out, payload):
    """裁决横幅——报告的第一句话回答「有没有要动手的」。"""
    items = payload.get("items", []) or []
    priority = [it for it in items if it.get("status") in report.PRIORITY_STATUSES]
    if not priority:
        out.append('<section class="banner calm">')
        out.append('<span class="banner-label">本次核验裁决</span>')
        out.append("<b>无需优先处理的条目</b>"
                   "<p>未出现「已撤稿 / 元数据不符 / 未找到（疑似不存在）」。"
                   "标「待人工核对」「无法核实」的条目仍需按各条出口指引处理。</p>")
        out.append("</section>")
        return
    counts = []
    for s in report.PRIORITY_STATUSES:
        n = sum(1 for it in priority if it.get("status") == s)
        if n:
            emoji, label = _label(s)
            counts.append(f"{emoji} {label} {n} 条")
    out.append('<section class="banner warn">')
    out.append('<span class="banner-label">本次核验裁决</span>')
    out.append(f"<b>{len(priority)} 条需优先处理：{_e('、'.join(counts))}</b>")
    out.append('<p>逐条证据见下方「需优先关注」，点条目可直达详情。'
               '「疑似不存在」是查证结果（查无此文），不是编造指控——如何处理由你判断。</p>')
    out.append("</section>")


def _render_distribution(out, payload):
    stats = payload.get("stats", {}) or {}
    total = stats.get("total", 0) or 0
    by_status = stats.get("by_status", {}) or {}
    statuses = _present_statuses(payload)
    out.append("<section>")
    out.append('<h2 class="section">一、六态分布<span class="sec-no">§ Distribution</span></h2>')
    if total and statuses:
        out.append('<div class="statusbar" role="img" aria-label="六态占比横条">')
        for s in statuses:
            n = by_status.get(s, 0)
            pct = n / total * 100
            emoji, label = _label(s)
            # 窄段只留 emoji（数字会被裁），宽段 emoji + 数量；精确值一律挂 title
            inner = f"{emoji} {n}" if pct >= 12 else emoji
            out.append(
                f'<div class="seg t-{_tone(s)}" style="flex:0 0 {pct:.4f}%" '
                f'title="{_e(label)} {n} 条（{pct:.0f}%）">{inner}</div>'
            )
        out.append("</div>")
    out.append('<table class="rtable"><thead><tr><th>核验状态</th><th>数量</th><th>占比</th>'
               "<th>这一态意味着什么</th></tr></thead><tbody>")
    for s in statuses:
        n = by_status.get(s, 0)
        emoji, label = _label(s)
        pct = f"{n / total * 100:.0f}%" if total else "0%"
        out.append(
            f"<tr><td><span class=\"st t-{_tone(s)}\">{emoji} {_e(label)}</span></td>"
            f'<td class="num" data-label="数量">{n}</td>'
            f'<td class="num" data-label="占比">{pct}</td>'
            f"<td>{_e(STATUS_MEANING[s])}</td></tr>"
        )
    out.append("</tbody></table></section>")


def _render_legend(out, payload):
    """六态图例——本报告的「来源」维度退化为「核验状态」维度（同 import 的 .st 先例）。"""
    out.append('<section class="legend">')
    out.append('<div class="legend-title">核验状态图例 · Verification States</div>')
    out.append("<ul>")
    for s in report.STATUS_ORDER:
        emoji, label = _label(s)
        out.append(f'<li><span class="st t-{_tone(s)}">{emoji} {_e(label)}</span></li>')
    out.append("</ul>")
    out.append('<div class="note">六态判定全部来自真实 API 响应 + 确定性规则，'
               '不含「AI 的新判断」层——凡无法追溯到某条 API 证据的结论，即不写入本报告。</div>')
    out.append("</section>")


def _render_priority(out, payload):
    priority = [it for it in payload.get("items", []) or []
                if it.get("status") in report.PRIORITY_STATUSES]
    if not priority:
        return
    out.append("<section>")
    out.append('<h2 class="section">二、需优先关注<span class="sec-no">§ Priority</span></h2>')
    out.append('<ul class="priority">')
    for it in priority:
        s = it.get("status", "")
        emoji, label = _label(s)
        rid = _e(it.get("ref_id", ""))
        out.append(
            f'<li><div class="pr-head"><span class="pr-ref">{rid}</span>'
            f'<span class="st t-{_tone(s)}">{emoji} {_e(label)}</span>'
            f'<a class="pr-jump" href="#ref-{rid}">查看详情 ↓</a></div>'
            f'<span class="pr-sum">{_e(it.get("evidence_summary", ""))}</span></li>'
        )
    out.append("</ul></section>")


def _render_sources(out, payload):
    sources = payload.get("sources_checked", []) or []
    auto = [s.get("name_zh", "") for s in sources if s.get("coverage") == "自动核验"]
    guided = [s.get("name_zh", "") for s in sources if s.get("coverage") == "待人工核对"]
    out.append("<section>")
    out.append('<h2 class="section">三、已查源清单<span class="sec-no">§ Sources</span></h2>')
    out.append('<table class="rtable"><thead><tr><th>覆盖方式</th><th>数据源</th></tr>'
               "</thead><tbody>")
    if auto:
        out.append("<tr><td>自动核验（真实 API 响应）</td>"
                   f'<td data-label="数据源">{_e("、".join(auto))}</td></tr>')
    if guided:
        out.append("<tr><td>待人工核对（无开放 API，给检索方案）</td>"
                   f'<td data-label="数据源">{_e("、".join(guided))}</td></tr>')
    if not auto and not guided:
        out.append("<tr><td colspan=\"2\">（无）</td></tr>")
    out.append("</tbody></table></section>")


def _render_items(out, payload):
    items = payload.get("items", []) or []
    out.append("<section>")
    out.append('<h2 class="section">四、逐条详情'
               f'<span class="sec-no">§ {len(items)} Refs</span></h2>')
    for it in items:
        _render_item(out, it)
    out.append("</section>")


def _render_item(out, it):
    status = it.get("status", "")
    tone = _tone(status)
    emoji, label = _label(status)
    rid = _e(it.get("ref_id", ""))
    parsed = it.get("parsed", {}) or {}
    out.append(f'<article class="ref t-{tone}" id="ref-{rid}" data-status="{_e(status)}">')
    out.append('<div class="ref-head">')
    out.append(f'<span class="ref-id">{rid}</span>')
    out.append(f'<span class="st t-{tone}">{emoji} {_e(label)}</span>')
    if parsed.get("doi"):
        doi = parsed["doi"]
        out.append(f'<span class="ref-doi">DOI <a href="{_e(_doi_url(doi))}" '
                   f'target="_blank" rel="noopener">{_e(doi)}</a></span>')
    out.append("</div>")

    if it.get("raw_text"):
        out.append(f'<div class="ref-raw">{_e(it["raw_text"])}</div>')
    if it.get("evidence_summary"):
        out.append(f'<p class="ref-sum">{_e(it["evidence_summary"])}</p>')

    # 解析所得：解析器是启发式的，把它解析成什么如实摆出来供用户复核
    bits = [(k, parsed.get(v)) for k, v in
            (("标题", "title"), ("年份", "year"), ("期刊", "venue"), ("类型", "type"))]
    if parsed.get("authors"):
        bits.insert(1, ("作者", "、".join(str(a) for a in parsed["authors"][:3])
                        + ("…" if len(parsed["authors"]) > 3 else "")))
    shown = [(k, v) for k, v in bits if v]
    if shown:
        out.append('<p class="ref-parsed">解析所得 · '
                   + " ".join(f"<b>{_e(k)}</b>{_e(v)}" for k, v in shown) + "</p>")
    if parsed.get("parse_status") == "unparsed":
        out.append('<p class="ref-parsed">⚠️ 该条未能自动解析——'
                   "字段可能不全，建议改贴 .bib 或拆成单条核验。</p>")

    _render_field_notes(out, it)
    _render_evidence(out, it)
    if status == "PENDING_MANUAL":
        _render_manual_kit(out, it)
    if it.get("exit_guidance"):
        out.append('<div class="block guide"><span class="block-label">出口指引</span>'
                   f'{_e(it["exit_guidance"])}</div>')
    _render_format_issues(out, it)
    out.append("</article>")


def _render_field_notes(out, it):
    notes = it.get("field_notes") or []
    if not notes:
        return
    out.append('<table class="fieldtable rtable"><thead><tr><th>字段</th><th>引用里写的</th>'
               "<th>数据源里的</th><th>判定</th></tr></thead><tbody>")
    for n in notes:
        sev = n.get("severity", "")
        sev_zh = "不符" if sev == "mismatch" else "仅提示"
        row_cls = "" if sev == "mismatch" else ' class="hint"'
        detail = f" {n.get('detail', '')}" if n.get("detail") else ""
        out.append(
            f"<tr{row_cls}><td class=\"f-name\">{_e(n.get('field', ''))}</td>"
            f'<td data-label="引用里写的">{_e(n.get("ref_value", ""))}</td>'
            f'<td data-label="数据源里的">{_e(n.get("source_value", ""))}</td>'
            f'<td><span class="sev {_e(sev)}">{sev_zh}</span>{_e(detail)}</td></tr>'
        )
    out.append("</tbody></table>")


def _render_evidence(out, it):
    """证据链折叠区——路由 / 逐源查询 / 命中源元数据，供用户自行复核。"""
    ev = it.get("evidence") or {}
    queries = ev.get("queries") or []
    hits = ev.get("hits") or []
    n_hit = sum(1 for q in queries if q.get("outcome") == "hit")
    n_err = sum(1 for q in queries if q.get("outcome") == "error")
    tail = f"命中 {n_hit} · 未命中 {len(queries) - n_hit - n_err} · 未查成 {n_err}" \
        if queries else "无查询记录"
    out.append(f"<details><summary>证据链（{_e(tail)}）</summary><ul>")
    if ev.get("doi_ra"):
        out.append(f"<li>DOI 注册机构路由：{_e(ev['doi_ra'])}</li>")
    if ev.get("route_note"):
        out.append(f"<li>{_e(ev['route_note'])}</li>")
    for q in queries:
        extra = []
        if q.get("query_kind"):
            extra.append(f"按 {q['query_kind']}")
        if q.get("error"):
            extra.append(f"错误 {q['error']}")
        if q.get("from_cache"):
            extra.append("来自本地缓存")
        suffix = f"（{'、'.join(extra)}）" if extra else ""
        out.append(f"<li>{_e(q.get('source', ''))}：{_e(q.get('outcome', ''))}{_e(suffix)}</li>")
    for h in hits:
        meta = h.get("metadata") or {}
        parts = [str(meta[k]) for k in ("title", "year", "venue") if meta.get(k)]
        if meta.get("authors"):
            parts.insert(1, str(meta["authors"][0]) + " 等")
        line = f"{_e(h.get('source', ''))} 命中：{_e(' · '.join(parts))}" if parts \
            else f"{_e(h.get('source', ''))} 命中"
        if meta.get("doi"):
            line += (f' · <a href="{_e(_doi_url(meta["doi"]))}" target="_blank" '
                     f'rel="noopener">{_e(meta["doi"])}</a>')
        if h.get("fetched_at"):
            line += f"（取回于 {_e(h['fetched_at'])}）"
        out.append(f"<li>{line}</li>")
    if not queries and not hits and not ev.get("doi_ra"):
        out.append("<li>（本条未产生查询记录）</li>")
    out.append("</ul></details>")


def _render_manual_kit(out, it):
    """人工核对包——检索词可一键复制、检索入口可点击（Markdown 版的可操作化）。"""
    parsed = it.get("parsed", {}) or {}
    terms = [str(parsed[k]) for k in ("title",) if parsed.get(k)]
    if parsed.get("authors"):
        terms.append(str(parsed["authors"][0]))
    if parsed.get("year"):
        terms.append(str(parsed["year"]))
    query = " ".join(terms) or (it.get("raw_text") or "")
    out.append('<div class="block manual"><span class="block-label">🔍 人工核对包</span>')
    if query:
        out.append('<div class="querybox"><code>' + _e(query) + "</code>"
                   f'<button type="button" class="copybtn" data-copy="{_e(query)}">'
                   "复制检索词</button><span class=\"copied\" aria-live=\"polite\"></span></div>")
    portals = " · ".join(f'<a href="{_e(u)}" target="_blank" rel="noopener">{_e(n)}</a>'
                         for n, u in MANUAL_PORTALS)
    out.append(f"<p>检索入口：{portals}</p>")
    out.append("<p>核对要点：找到后回填 DOI / 卷期页 / 文献类型；"
               "在本报告同名 JSON 的该条 <code>manual_result</code> 填 "
               "<code>{verified:true, doi:\"...\", note:\"...\", checked_at:\"...\"}</code>，"
               "重跑 verify 即升级为「已核实」。</p>")
    out.append("</div>")


def _render_format_issues(out, it):
    issues = it.get("format_issues") or []
    if not issues:
        return
    out.append('<div class="block fmt"><span class="block-label">格式提示 · GB/T 7714</span><ul>')
    for fi in issues:
        out.append(f"<li>{_e(fi.get('problem', ''))}"
                   f"<span class=\"clause\">（{_e(fi.get('clause', ''))}）</span><br>"
                   f"规范化示例：{_e(fi.get('suggestion', ''))}</li>")
    out.append("</ul></div>")


def _render_footer(out):
    out.append("<footer>")
    out.append('<div class="seal">Human–AI Division of Labor</div>')
    out.append("<p><b>人机分工</b>：本报告由 AI 自动取证（真实 API 响应）+ 规则判定（六态映射），"
               "「疑似不存在」「元数据不符」均为客观证据推断、非动机指控；"
               "最终判断（是否编造、如何处理）由用户负责。</p>")
    out.append("<p>AI 不替用户判定学术不端、不指控动机、不替用户改写参考文献表。"
               "中文文献一律走「待人工核对」，英文库查不到不等于不存在。</p>")
    out.append('<a class="totop" href="#">↑ 回到顶部</a>')
    out.append("</footer>")


def write_html(payload: Dict[str, Any], html_path) -> None:
    """把 payload 落盘为 HTML（verify.py 调用）。"""
    pathlib.Path(html_path).write_text(build_html(payload), encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="核验报告 JSON → 单文件 HTML 视图（纯渲染，可对旧报告重跑）。")
    p.add_argument("--in", dest="src", required=True, help="核验报告 JSON（verify-*.json）")
    p.add_argument("--out", dest="dst", help="输出 HTML（默认同名 .html）")
    args = p.parse_args(argv)
    src = pathlib.Path(args.src)
    dst = pathlib.Path(args.dst) if args.dst else src.with_suffix(".html")
    write_html(json.loads(src.read_text(encoding="utf-8")), dst)
    sys.stderr.write(f"已生成 {dst}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
