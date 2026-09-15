/**
 * tokens.ts — 全站唯一的样式 token 源（single source of truth）。
 *
 * 两条消费链都由本文件派生，禁止在别处再写一份色值：
 *   1. CSS 变量 → scripts/generate-theme-css.mjs 生成
 *      · 颜色（本文件 colorTokens）→ assets/styles/themes.css（亮/暗两块）
 *      · 非颜色（本文件 staticTokens）→ assets/styles/variables.css
 *   2. Naive UI → theme/overrides.ts 从本文件取值组装 GlobalThemeOverrides
 *
 * 命名：键即 CSS 变量名去掉 `--app-` 前缀（kebab-case），
 * 例：'body-bg' → --app-body-bg。
 *
 * 铁律：新增色相必须 light / dark 两边都加，否则另一主题下会静默落到别的
 * 颜色。改完运行 `npm run theme:css` 重新生成 CSS（有测试守卫两者一致）。
 */

/** 颜色 token，按 data-theme 分亮 / 暗两套。 */
export const colorTokens = {
  light: {
    // ---- 表面 / 边框 ----
    'body-bg': '#F1F5F9',
    'sidebar-bg': '#E2E8F0',
    'sidebar-border': '#CBD5E1',
    'card-bg': '#FFFFFF',
    'card-border': '#E2E8F0',
    'input-bg': '#FFFFFF',
    'input-border': '#CBD5E1',
    'code-bg': '#F1F5F9',
    'drop-zone-bg': '#F8FAFC',
    'drop-zone-border': '#94A3B8',
    'storage-bg': 'rgba(0, 0, 0, 0.04)',

    // ---- 文字 ----
    'text-primary': '#0F172A',
    'text-secondary': '#334155',
    'text-muted': '#475569',
    'text-dim': '#64748B',

    // ---- 语义色 + 同色底 ----
    'green': '#16A34A',
    'green-hover': '#15803D',
    'green-bg': 'rgba(22, 163, 74, 0.1)',
    'green-bg-hover': 'rgba(22, 163, 74, 0.06)',
    'green-bg-active': 'rgba(22, 163, 74, 0.12)',
    'blue': '#2563EB',
    'blue-hover': '#1D4ED8',
    'blue-bg': 'rgba(37, 99, 235, 0.1)',
    'yellow': '#B45309',
    'yellow-bg': 'rgba(180, 83, 9, 0.12)',
    'purple': '#7C3AED',
    'purple-bg': 'rgba(124, 58, 237, 0.1)',
    'red': '#DC2626',
    'red-bg': 'rgba(220, 38, 38, 0.1)',

    // ---- 交互态 ----
    'hover': 'rgba(0, 0, 0, 0.04)',
    'hover-strong': 'rgba(0, 0, 0, 0.08)',

    // ---- 杂项 ----
    'scrollbar-thumb': '#CBD5E1',
    'scrollbar-hover': '#94A3B8',
    'placeholder-color': '#CBD5E1',
  },
  dark: {
    // ---- 表面 / 边框 ----
    'body-bg': '#0F172A',
    'sidebar-bg': '#0C1322',
    'sidebar-border': '#1E293B',
    'card-bg': '#1E293B',
    'card-border': '#334155',
    'input-bg': '#1E293B',
    'input-border': '#334155',
    'code-bg': '#0C1322',
    'drop-zone-bg': '#0C1322',
    'drop-zone-border': '#334155',
    'storage-bg': 'rgba(15, 23, 42, 0.5)',

    // ---- 文字 ----
    'text-primary': '#F8FAFC',
    'text-secondary': '#CBD5E1',
    'text-muted': '#94A3B8',
    'text-dim': '#64748B',

    // ---- 语义色 + 同色底 ----
    'green': '#22C55E',
    'green-hover': '#16A34A',
    'green-bg': 'rgba(34, 197, 94, 0.1)',
    'green-bg-hover': 'rgba(34, 197, 94, 0.06)',
    'green-bg-active': 'rgba(34, 197, 94, 0.12)',
    'blue': '#3B82F6',
    'blue-hover': '#2563EB',
    'blue-bg': 'rgba(59, 130, 246, 0.1)',
    'yellow': '#F59E0B',
    'yellow-bg': 'rgba(245, 158, 11, 0.14)',
    'purple': '#A78BFA',
    'purple-bg': 'rgba(167, 139, 250, 0.14)',
    'red': '#EF4444',
    'red-bg': 'rgba(239, 68, 68, 0.14)',

    // ---- 交互态 ----
    'hover': 'rgba(34, 197, 94, 0.06)',
    'hover-strong': 'rgba(34, 197, 94, 0.12)',

    // ---- 杂项 ----
    'scrollbar-thumb': '#334155',
    'scrollbar-hover': '#475569',
    'placeholder-color': '#334155',
  },
} as const

/** 非颜色 token：两种主题共用（间距 / 圆角 / 字体 / 阴影 / 布局 / 控制台）。 */
export const staticTokens = {
  // ---- 字体：页面只有这两个字体栈（Inter 由 index.html 加载） ----
  'font': "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif",
  'font-mono': "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",

  // ---- 间距 ----
  'space-xs': '4px',
  'space-sm': '8px',
  'space-md': '16px',
  'space-lg': '24px',
  'space-xl': '32px',

  // ---- 圆角 ----
  'radius-sm': '4px',
  'radius-md': '8px',
  'radius-lg': '12px',

  // ---- 阴影 ----
  'shadow-sm': '0 1px 2px rgba(0, 0, 0, 0.05)',
  'shadow-md': '0 4px 6px rgba(0, 0, 0, 0.07)',
  'shadow-lg': '0 10px 15px rgba(0, 0, 0, 0.1)',

  // ---- 布局：单一页面宽度，切页不再跳宽 ----
  'page-max-width': '1040px',

  // ---- 日志控制台：恒定深色（两种主题下都保持深底），
  //      所以刻意不引用颜色 token ----
  'console-bg': '#0F1115',
  'console-fg': '#C8D0DA',
  'console-dim': '#5C6672',
  'console-err': '#FF7A85',
  'console-err-dim': '#8A4A52',
  'console-warn': '#F0C060',
} as const

export type ColorTheme = keyof typeof colorTokens
export type ColorTokenName = keyof typeof colorTokens.light
export type StaticTokenName = keyof typeof staticTokens

/** 便捷读取：`appColor('dark')['card-bg']`；类型上等价于直接索引 colorTokens。 */
export function appColor(theme: ColorTheme) {
  return colorTokens[theme]
}
