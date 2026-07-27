// echarts-theme.js — Paper-Tutor-Skills 报告 ECharts 主题
// ====================================================================
// 各图表模板在 <head> 里引入 ECharts CDN 后紧跟：
//   <script src="../_shared/echarts-theme.js"></script>
// 本文件加载即执行 echarts.registerTheme('paper', {...})，
// 图表初始化统一写 echarts.init(dom, 'paper', { renderer: 'svg' })。
//
// 图表交互统一规范（设计稿 §4.4，产品死线）：
// - Tooltip：开、静态显示精确值、禁富文本/按钮/超链接
// - Hover：轻量高亮（数据点放大）、禁 crosshair/zone highlighting
// - 入场动画：单次 600ms、prefers-reduced-motion 时降 0ms
// - 循环动画：关、禁 spinner/pulse/glow
// - Legend：关（轴标签自说明）
// - Split area：关（分区=达标带=优劣暗示）、splitLine 极淡保留
// - Data zoom/brush/timeline：全关
// - 配色：单色优先用 l2 赭石、多系列依次取色板、禁渐变发光
// - 面积填充：α ≤ 0.1、仅辅助识形
// - 数据标签：开、衬线宋体 11px ink-soft
// - Renderer：SVG（屏幕阅读器可读 + 打印矢量清晰）
// - Responsive：容器 width:100%、height:320-340px、监听 resize

if (typeof echarts !== 'undefined') {
  echarts.registerTheme('paper', {
    color: [
      '#7a6230',  // l2 赭石（单系列首选：模拟常见）
      '#2b4a6f',  // l1 靛蓝（👤 用户原话）
      '#4a6b5c',  // l3 青灰（🪞 系统归纳）
      '#9a3b2e',  // l4 砖红（❓ 待用户决定）
      '#5a5247',  // ink-soft
      '#8a8071',  // ink-faint
    ],
    backgroundColor: 'transparent',
    textStyle: {
      fontFamily: '"PingFang SC", "Microsoft YaHei", sans-serif',
      color: '#1f1b16',
    },
    title: {
      textStyle: { color: '#1f1b16', fontWeight: 600 },
      subtextStyle: { color: '#5a5247' },
    },
    legend: {
      textStyle: { color: '#5a5247' },
      inactiveColor: '#8a8071',
    },
    tooltip: {
      backgroundColor: 'rgba(246, 242, 234, 0.95)',
      borderColor: '#c9bfa8',
      borderWidth: 1,
      textStyle: { color: '#1f1b16', fontSize: 12 },
      extraCssText: 'box-shadow: 0 2px 8px rgba(60,45,20,.12);',
    },
    radar: {
      axisName: {
        color: '#5a5247',
        fontFamily: '"Source Han Serif SC", "Songti SC", serif',
        fontSize: 12,
      },
      splitLine: { lineStyle: { color: '#c9bfa8' } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: '#8a8071' } },
    },
    categoryAxis: {
      axisLine: { lineStyle: { color: '#c9bfa8' } },
      axisTick: { lineStyle: { color: '#c9bfa8' } },
      axisLabel: { color: '#5a5247' },
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#5a5247' },
      splitLine: { lineStyle: { color: '#ece5d6' } },
    },
  });
}
