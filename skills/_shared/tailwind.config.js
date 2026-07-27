// tailwind.config.js — Paper-Tutor-Skills 报告模板共享设计 token
// ====================================================================
// 各 skill 报告样式模板.html 在 <head> 里引入 Tailwind CDN 后紧跟：
//   <script src="../_shared/tailwind.config.js"></script>
// 本文件加载即执行 tailwind.config = {...}，使 Tailwind CDN 模式
// 识别自定义 colors / fontFamily / typography 扩展。
//
// 设计 token 权威：docs/specs/2026-07-26-报告模板重构设计.md §3
// 四层语义色色值是产品死线、不得修改。

tailwind.config = {
  theme: {
    extend: {
      colors: {
        // 纸面与墨色（学术档案基底）
        paper:        '#f6f2ea',
        'paper-edge': '#ece5d6',
        rule:         '#c9bfa8',
        ink: {
          DEFAULT: '#1f1b16',
          soft:    '#5a5247',
          faint:   '#8a8071',
        },

        // 四层语义色 —— 产品死线，色值不得改
        // 👤 用户原话=靛蓝 / 📋 常见事实=赭石 / 🪞 系统归纳=青灰 / ❓ 待用户决定=砖红
        l1: { DEFAULT: '#2b4a6f', bg: '#e6edf4' },
        l2: { DEFAULT: '#7a6230', bg: '#f0e9d8' },
        l3: { DEFAULT: '#4a6b5c', bg: '#e4ece8' },
        l4: { DEFAULT: '#9a3b2e', bg: '#f3e3df' },
      },

      fontFamily: {
        serif: [
          '"Source Han Serif SC"', '"Noto Serif SC"', '"Songti SC"', '"STSong"',
          '"PingFang SC"', '"Microsoft YaHei"', 'Georgia', 'serif',
        ],
        sans: [
          '"PingFang SC"', '"Source Han Sans SC"', '"Microsoft YaHei"',
          '"Helvetica Neue"', 'Arial', 'sans-serif',
        ],
      },

      // typography 插件：覆盖 prose 默认主题，对齐学术档案气质
      typography: (theme) => ({
        DEFAULT: {
          css: {
            '--tw-prose-body':     theme('colors.ink.DEFAULT'),
            '--tw-prose-headings': theme('colors.ink.DEFAULT'),
            '--tw-prose-links':    theme('colors.l1.DEFAULT'),
            '--tw-prose-bold':     theme('colors.ink.DEFAULT'),
            '--tw-prose-borders':  theme('colors.rule'),
            '--tw-prose-bg':       theme('colors.paper'),
            fontFamily:            theme('fontFamily.serif').join(', '),
            lineHeight:            '1.85',
          },
        },
      }),
    },
  },
};
