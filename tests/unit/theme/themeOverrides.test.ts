import { describe, it, expect } from 'vitest'
import { themeOverridesDark, themeOverridesLight, selectOverrides } from '@/renderer/theme/overrides'
import { colorTokens } from '@/renderer/theme/tokens'

/**
 * Naive UI 覆盖表的黄金值锁定。
 *
 * 期望值 = 重构前（tokens 单源之前）的观感；2026-09 统一后，原 5 处
 * 「Naive ≠ token」的分歧已对齐 token，本文件同步更新 —— 任何进一步的
 * 视觉变化都必须显式改这里，防止无声夹带。
 */

describe('themeOverrides 黄金值', () => {
  it('dark 覆盖与重构前逐项一致', () => {
    expect(themeOverridesDark).toEqual({
      common: {
        bodyColor: '#0F172A',
        cardColor: '#1E293B',
        modalColor: '#1E293B',
        popoverColor: '#1E293B',
        borderColor: '#334155',
        borderRadius: '8px',
        primaryColor: '#22C55E',
        primaryColorHover: '#16A34A',
        primaryColorPressed: '#15803D',
        infoColor: '#3B82F6',
        successColor: '#22C55E',
        warningColor: '#F59E0B',
        errorColor: '#EF4444',
        textColor1: '#F8FAFC',
        textColor2: '#CBD5E1',
        textColor3: '#94A3B8',
        scrollbarColor: '#334155',
        scrollbarColorHover: '#475569',
        scrollbarWidth: '6px',
        scrollbarHeight: '6px',
        scrollbarBorderRadius: '3px',
        inputColor: '#1E293B',
        actionColor: '#334155',
        // 由 token(--app-green-bg-active) 取值后 rgba 写法归一化（带空格）：
        // 与原紧凑写法 rgba(34,197,94,0.12) 是同一个颜色，仅字符串格式不同。
        hoverColor: 'rgba(34, 197, 94, 0.12)',
      },
      Input: {
        border: '1px solid #334155',
        borderHover: '1px solid #22C55E',
        borderFocus: '1px solid #22C55E',
        borderRadius: '8px',
      },
      InternalSelection: {
        border: '1px solid #334155',
        borderHover: '1px solid #22C55E',
        borderFocus: '1px solid #22C55E',
        borderRadius: '8px',
      },
      Menu: {
        itemColorHover: 'rgba(34, 197, 94, 0.06)',
        itemColorActive: 'rgba(34, 197, 94, 0.12)',
        itemColorActiveHover: 'rgba(34, 197, 94, 0.06)',
        itemColorActiveCollapsed: 'rgba(34, 197, 94, 0.12)',
      },
    })
  })

  it('light 覆盖与重构前逐项一致', () => {
    expect(themeOverridesLight).toEqual({
      common: {
        bodyColor: '#F1F5F9',
        cardColor: '#FFFFFF',
        modalColor: '#FFFFFF',
        popoverColor: '#FFFFFF',
        borderColor: '#E2E8F0',
        borderRadius: '8px',
        primaryColor: '#16A34A',
        primaryColorHover: '#15803D',
        primaryColorPressed: '#166534',
        infoColor: '#2563EB',
        successColor: '#16A34A',
        warningColor: '#B45309',
        errorColor: '#DC2626',
        textColor1: '#0F172A',
        textColor2: '#334155',
        textColor3: '#475569',
        scrollbarColor: '#CBD5E1',
        scrollbarColorHover: '#94A3B8',
        scrollbarWidth: '6px',
        scrollbarHeight: '6px',
        scrollbarBorderRadius: '3px',
        inputColor: '#FFFFFF',
        actionColor: '#E2E8F0',
        hoverColor: 'rgba(22, 163, 74, 0.06)',
      },
      Input: {
        border: '1px solid #CBD5E1',
        borderHover: '1px solid #16A34A',
        borderFocus: '1px solid #16A34A',
        borderRadius: '8px',
      },
      InternalSelection: {
        border: '1px solid #CBD5E1',
        borderHover: '1px solid #16A34A',
        borderFocus: '1px solid #16A34A',
        borderRadius: '8px',
      },
      Menu: {
        itemColorHover: 'rgba(0, 0, 0, 0.04)',
        itemColorActive: 'rgba(0, 0, 0, 0.08)',
        itemColorActiveHover: 'rgba(0, 0, 0, 0.04)',
        itemColorActiveCollapsed: 'rgba(0, 0, 0, 0.08)',
      },
    })
  })

  it('selectOverrides 按 Naive 主题对象选择亮/暗', () => {
    expect(selectOverrides({} as never)).toBe(themeOverridesDark)
    expect(selectOverrides(null)).toBe(themeOverridesLight)
  })

  it('原 5 处分歧项已与 token 同源（防止再次漂移）', () => {
    expect(themeOverridesLight.common.warningColor).toBe(colorTokens.light['yellow'])
    expect(themeOverridesLight.common.textColor2).toBe(colorTokens.light['text-secondary'])
    expect(themeOverridesLight.common.textColor3).toBe(colorTokens.light['text-muted'])
    expect(themeOverridesLight.common.hoverColor).toBe(colorTokens.light['green-bg-hover'])
    expect(themeOverridesDark.Input.border).toBe(`1px solid ${colorTokens.dark['input-border']}`)
    expect(themeOverridesDark.InternalSelection.border).toBe(`1px solid ${colorTokens.dark['input-border']}`)
  })
})
