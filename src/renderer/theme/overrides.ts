import type { GlobalTheme, GlobalThemeOverrides } from 'naive-ui'
import { colorTokens, staticTokens } from './tokens'

/**
 * Naive UI 覆盖表 —— 由 tokens.ts 派生。
 *
 * 一致性：与 tokens 同义的值一律引用 token（禁止再写一份字面色）；只有下列
 * 「Naive 现有观感 ≠ token」的分歧项保留字面值，标注 `≠ token(...)`，使本批
 * 保持零视觉变化。是否统一到 token 值属批 2 决策（见样式审计表 P2）：
 *   light: textColor2 / textColor3 / warningColor / hoverColor
 *   dark:  Input+InternalSelection.border
 * 另有 3 个 Naive 语义角色没有对应 token（primaryColorPressed / actionColor /
 * modal|popoverColor 复用 card 色），同样以注释说明来源。
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
    primaryColorPressed: '#15803D', // 无对应 token（值同 light 的 green-hover）
    infoColor: D['blue'],
    successColor: D['green'],
    warningColor: D['yellow'],
    errorColor: D['red'],
    textColor1: D['text-primary'],
    textColor2: D['text-secondary'],
    textColor3: D['text-muted'],
    scrollbarColor: D['scrollbar-thumb'],
    inputColor: D['input-bg'],
    actionColor: '#334155', // 无对应 token（值同 card-border，语义不同故不引用）
    hoverColor: D['green-bg-active'],
  },
  Input: {
    border: '1px solid #475569', // ≠ token(--app-input-border #334155)
    borderHover: `1px solid ${D['green']}`,
    borderFocus: `1px solid ${D['green']}`,
    borderRadius: RADIUS_MD,
  },
  InternalSelection: {
    border: '1px solid #475569', // ≠ token(--app-input-border #334155)
    borderHover: `1px solid ${D['green']}`,
    borderFocus: `1px solid ${D['green']}`,
    borderRadius: RADIUS_MD,
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
    primaryColorPressed: '#166534', // 无对应 token
    infoColor: L['blue'],
    successColor: L['green'],
    warningColor: '#D97706',        // ≠ token(--app-yellow #B45309)
    errorColor: L['red'],
    textColor1: L['text-primary'],
    textColor2: '#475569',          // ≠ token(--app-text-secondary #334155)，值同 light 的 --app-text-muted
    textColor3: '#94A3B8',          // ≠ token(--app-text-muted #475569)，值同 dark 的 --app-text-muted
    scrollbarColor: L['scrollbar-thumb'],
    inputColor: L['input-bg'],
    actionColor: '#E2E8F0',         // 无对应 token（值同 --app-sidebar-bg，语义不同故不引用）
    hoverColor: 'rgba(22,163,74,0.08)', // ≠ token(--app-green-bg-hover rgba(22,163,74,0.06))
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
}

export const selectOverrides = (theme: GlobalTheme | null) =>
  theme ? themeOverridesDark : themeOverridesLight
