import type { GlobalTheme, GlobalThemeOverrides } from 'naive-ui'
import { colorTokens, staticTokens } from './tokens'

/**
 * Naive UI 覆盖表 —— 由 tokens.ts 派生。
 *
 * 一致性：与 tokens 同义的值一律引用 token，本文件不含「第二份调色板」。
 * 仅剩的字面值都是 Naive 有、token 无的语义角色：
 *   · primaryColorPressed（亮/暗各一，token 里无「按下态」色）
 *   · actionColor（hover/action 底色，值与既有 token 巧合相同但语义不同，故不引用）
 *   · modalColor / popoverColor 复用 card 色（无独立 token）
 *
 * 2026-09 统一（原 Naive 覆盖值与 token 存在 5 处分歧，已全部对齐 token）：
 *   light warningColor  #D97706 → --app-yellow        #B45309
 *   light textColor2    #475569 → --app-text-secondary #334155
 *   light textColor3    #94A3B8 → --app-text-muted     #475569
 *   light hoverColor    rgba(22,163,74,.08) → --app-green-bg-hover rgba(22,163,74,.06)
 *   dark  Input/InternalSelection.border #475569 → --app-input-border #334155
 * 黄金值测试（tests/unit/theme/themeOverrides.test.ts）同步更新并新增
 * token 同源断言，锁死这次对齐。
 */
const L = colorTokens.light
const D = colorTokens.dark
const RADIUS_MD = staticTokens['radius-md']

export const themeOverridesDark: GlobalThemeOverrides = {
  common: {
    bodyColor: D['body-bg'],
    cardColor: D['card-bg'],
    modalColor: D['card-bg'],   // 无独立 token：弹层与卡片同色
    popoverColor: D['card-bg'], // 同上
    borderColor: D['card-border'],
    borderRadius: RADIUS_MD,
    primaryColor: D['green'],
    primaryColorHover: D['green-hover'],
    primaryColorPressed: D['green-pressed'],
    infoColor: D['blue'],
    successColor: D['green'],
    warningColor: D['yellow'],
    errorColor: D['red'],
    textColor1: D['text-primary'],
    textColor2: D['text-secondary'],
    textColor3: D['text-muted'],
    scrollbarColor: D['scrollbar-thumb'],
    // Naive 自绘滚动条与原生条保持一致：hover 色走 token、几何走 scrollbar-* token
    // （此前 hover 用 Naive 默认的 alpha 叠加，与原生条 hover 变深的行为不一致）
    scrollbarColorHover: D['scrollbar-hover'],
    scrollbarWidth: staticTokens['scrollbar-size'],
    scrollbarHeight: staticTokens['scrollbar-size'],
    scrollbarBorderRadius: staticTokens['scrollbar-radius'],
    inputColor: D['input-bg'],
    actionColor: D['action-bg'],
    hoverColor: D['green-bg-active'],
  },
  Input: {
    border: `1px solid ${D['input-border']}`,
    borderHover: `1px solid ${D['green']}`,
    borderFocus: `1px solid ${D['green']}`,
    borderRadius: RADIUS_MD,
  },
  InternalSelection: {
    border: `1px solid ${D['input-border']}`,
    borderHover: `1px solid ${D['green']}`,
    borderFocus: `1px solid ${D['green']}`,
    borderRadius: RADIUS_MD,
  },
  // 菜单项底色由 naive-overrides.css 迁入（原为 3 个 !important 覆盖）：
  // 选中/hover 是 Naive 一等主题字段，走 themeOverrides 不需要 !important。
  // itemColorActiveHover 取 hover 值以保持原观感（原先 :hover 规则胜过 --selected）。
  // 按下态（:active）无对应字段，仍留在 CSS。
  Menu: {
    itemColorHover: D['hover'],
    itemColorActive: D['hover-strong'],
    itemColorActiveHover: D['hover'],
    itemColorActiveCollapsed: D['hover-strong'],
  },
}

export const themeOverridesLight: GlobalThemeOverrides = {
  common: {
    bodyColor: L['body-bg'],
    cardColor: L['card-bg'],
    modalColor: L['card-bg'],   // 无独立 token：弹层与卡片同色
    popoverColor: L['card-bg'], // 同上
    borderColor: L['card-border'],
    borderRadius: RADIUS_MD,
    primaryColor: L['green'],
    primaryColorHover: L['green-hover'],
    primaryColorPressed: L['green-pressed'],
    infoColor: L['blue'],
    successColor: L['green'],
    warningColor: L['yellow'],
    errorColor: L['red'],
    textColor1: L['text-primary'],
    textColor2: L['text-secondary'],
    textColor3: L['text-muted'],
    scrollbarColor: L['scrollbar-thumb'],
    scrollbarColorHover: L['scrollbar-hover'],
    scrollbarWidth: staticTokens['scrollbar-size'],
    scrollbarHeight: staticTokens['scrollbar-size'],
    scrollbarBorderRadius: staticTokens['scrollbar-radius'],
    inputColor: L['input-bg'],
    actionColor: L['action-bg'],
    hoverColor: L['green-bg-hover'],
  },
  Input: {
    border: `1px solid ${L['input-border']}`,
    borderHover: `1px solid ${L['green']}`,
    borderFocus: `1px solid ${L['green']}`,
    borderRadius: RADIUS_MD,
  },
  InternalSelection: {
    border: `1px solid ${L['input-border']}`,
    borderHover: `1px solid ${L['green']}`,
    borderFocus: `1px solid ${L['green']}`,
    borderRadius: RADIUS_MD,
  },
  Menu: {
    itemColorHover: L['hover'],
    itemColorActive: L['hover-strong'],
    itemColorActiveHover: L['hover'],
    itemColorActiveCollapsed: L['hover-strong'],
  },
}

export const selectOverrides = (theme: GlobalTheme | null) =>
  theme ? themeOverridesDark : themeOverridesLight
