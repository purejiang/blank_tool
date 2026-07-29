import type { GlobalTheme } from 'naive-ui'

export const themeOverridesDark = {
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
    inputColor: '#1E293B',
    actionColor: '#334155',
    hoverColor: 'rgba(34,197,94,0.12)',
  },
  Input: {
    border: '1px solid #475569',
    borderHover: '1px solid #22C55E',
    borderFocus: '1px solid #22C55E',
    borderRadius: '8px',
  },
  InternalSelection: {
    border: '1px solid #475569',
    borderHover: '1px solid #22C55E',
    borderFocus: '1px solid #22C55E',
    borderRadius: '8px',
  },
}

export const themeOverridesLight = {
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
    warningColor: '#D97706',
    errorColor: '#DC2626',
    textColor1: '#0F172A',
    textColor2: '#475569',
    textColor3: '#94A3B8',
    scrollbarColor: '#CBD5E1',
    inputColor: '#FFFFFF',
    actionColor: '#E2E8F0',
    hoverColor: 'rgba(22,163,74,0.08)',
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
}

export const selectOverrides = (theme: GlobalTheme | null) =>
  theme ? themeOverridesDark : themeOverridesLight
