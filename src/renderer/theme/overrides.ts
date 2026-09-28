import type { GlobalTheme } from 'naive-ui'

/**
 * Naive UI 主题覆盖（**运行时读取设计 token**）。
 *
 * 颜色不允许在这个文件里硬编码：全部通过 `token()` 从 assets/styles/tokens.css
 * 的 CSS 变量取值。主题切换时 ThemeService 先写 documentElement 的 data-theme，
 * 再通知 App 重算这里，所以取值拿到的永远是当前模式的实际颜色。
 *
 * 取不到值时才用第二参数兜底（首帧 / 非浏览器环境），保证不会出现空色值。
 */
function readToken(name: string, fallback: string): string {
  if (typeof document === 'undefined' || typeof getComputedStyle !== 'function') return fallback
  try {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return value || fallback
  } catch {
    return fallback
  }
}

/** 焦点环：`0 0 0 3px var(--ring)` 的实体值（规范要求所有可交互元素都有）。 */
function focusRing(dark: boolean): string {
  const ring = readToken('--ring', dark ? 'rgba(96,165,250,0.25)' : 'rgba(37,99,235,0.18)')
  return `0 0 0 3px ${ring}`
}

function buildOverrides(dark: boolean) {
  const bg = readToken('--bg', dark ? '#0B1220' : '#F8FAFC')
  const surface = readToken('--surface', dark ? '#111827' : '#FFFFFF')
  const surfaceAlt = readToken('--surface-alt', dark ? '#1E293B' : '#F1F5F9')
  const border = readToken('--border', dark ? '#334155' : '#E2E8F0')
  const text = readToken('--text', dark ? '#F1F5F9' : '#0F172A')
  const textSecondary = readToken('--text-secondary', dark ? '#CBD5E1' : '#475569')
  const textMuted = readToken('--text-muted', dark ? '#94A3B8' : '#94A3B8')

  const primary = readToken('--primary', dark ? '#60A5FA' : '#2563EB')
  const primaryHover = readToken('--primary-hover', dark ? '#3B82F6' : '#1D4ED8')
  const primaryActive = readToken('--primary-active', dark ? '#2563EB' : '#1E40AF')
  const primarySoft = readToken('--primary-soft', dark ? '#16233B' : '#EFF6FF')
  const primarySoftBorder = readToken('--primary-soft-border', dark ? '#1E3A8A' : '#BFDBFE')
  const onPrimary = readToken('--on-primary', dark ? '#0B1220' : '#FFFFFF')

  const successBg = readToken('--success-bg', dark ? 'rgba(16,185,129,0.12)' : '#ECFDF5')
  const successBorder = readToken('--success-border', dark ? 'rgba(16,185,129,0.38)' : '#A7F3D0')
  const successText = readToken('--success-text', dark ? '#6EE7B7' : '#065F46')
  const warningBg = readToken('--warning-bg', dark ? 'rgba(245,158,11,0.12)' : '#FFFBEB')
  const warningBorder = readToken('--warning-border', dark ? 'rgba(245,158,11,0.38)' : '#FDE68A')
  const warningText = readToken('--warning-text', dark ? '#FCD34D' : '#92400E')
  const dangerBg = readToken('--danger-bg', dark ? 'rgba(239,68,68,0.12)' : '#FEF2F2')
  const dangerBorder = readToken('--danger-border', dark ? 'rgba(239,68,68,0.38)' : '#FECACA')
  const dangerText = readToken('--danger-text', dark ? '#FCA5A5' : '#991B1B')
  const infoBg = readToken('--info-bg', dark ? '#16233B' : '#EFF6FF')
  const infoBorder = readToken('--info-border', dark ? '#1E3A8A' : '#BFDBFE')
  const infoText = readToken('--info-text', dark ? '#93C5FD' : '#1E3A8A')

  const radiusCard = readToken('--radius-card', '14px')
  const radiusControl = readToken('--radius-control', '8px')
  const shadowCard = readToken('--shadow-card', '0 1px 2px rgba(15,23,42,.06)')

  return {
    common: {
      fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
      fontSize: '13px',
      // 面 / 文字 / 描边
      bodyColor: bg,
      cardColor: surface,
      modalColor: surface,
      popoverColor: surface,
      tableColor: surface,
      inputColor: surface,
      actionColor: surfaceAlt,
      hoverColor: surfaceAlt,
      borderColor: border,
      dividerColor: border,
      textColor1: text,
      textColor2: textSecondary,
      textColor3: textMuted,
      placeholderColor: textMuted,
      scrollbarColor: border,
      scrollbarColorHover: textMuted,
      // 主色（蓝色单色体系：primary 就是蓝）
      primaryColor: primary,
      primaryColorHover: primaryHover,
      primaryColorPressed: primaryActive,
      primaryColorSuppl: primaryHover,
      // 语义色：成功/警告/错误/信息各自独立，不用蓝色顶替
      successColor: successText,
      successColorHover: successText,
      successColorPressed: successText,
      successColorSuppl: successText,
      warningColor: warningText,
      warningColorHover: warningText,
      warningColorPressed: warningText,
      warningColorSuppl: warningText,
      errorColor: dangerText,
      errorColorHover: dangerText,
      errorColorPressed: dangerText,
      errorColorSuppl: dangerText,
      infoColor: infoText,
      infoColorHover: infoText,
      infoColorPressed: infoText,
      infoColorSuppl: infoText,
      borderRadius: radiusControl,
      borderRadiusSmall: radiusControl,
    },
    Button: {
      // 主按钮：primary / on-primary
      colorPrimary: primary,
      colorHoverPrimary: primaryHover,
      colorPressedPrimary: primaryActive,
      colorFocusPrimary: primaryHover,
      borderPrimary: `1px solid ${primary}`,
      borderHoverPrimary: `1px solid ${primaryHover}`,
      borderPressedPrimary: `1px solid ${primaryActive}`,
      borderFocusPrimary: `1px solid ${primaryHover}`,
      textColorPrimary: onPrimary,
      textColorHoverPrimary: onPrimary,
      textColorPressedPrimary: onPrimary,
      textColorFocusPrimary: onPrimary,
      // 次按钮（soft）：primary-soft 底 + primary 字
      colorSecondary: primarySoft,
      colorHoverSecondary: primarySoft,
      colorPressedSecondary: primarySoft,
      borderSecondary: `1px solid ${primarySoftBorder}`,
      borderHoverSecondary: `1px solid ${primarySoftBorder}`,
      borderPressedSecondary: `1px solid ${primarySoftBorder}`,
      textColorSecondary: primary,
      textColorHoverSecondary: primaryHover,
      textColorPressedSecondary: primaryActive,
      // 描边按钮：透明底 + primary 字 + border 边
      colorTertiary: 'transparent',
      colorHoverTertiary: primarySoft,
      colorPressedTertiary: primarySoft,
      borderTertiary: `1px solid ${border}`,
      borderHoverTertiary: `1px solid ${primarySoftBorder}`,
      borderPressedTertiary: `1px solid ${primarySoftBorder}`,
      textColorTertiary: primary,
      textColorHoverTertiary: primaryHover,
      textColorPressedTertiary: primaryActive,
      // 幽灵按钮：透明底 + text-secondary
      colorQuaternary: 'transparent',
      colorHoverQuaternary: surfaceAlt,
      colorPressedQuaternary: surfaceAlt,
      borderQuaternary: '1px solid transparent',
      borderHoverQuaternary: '1px solid transparent',
      borderPressedQuaternary: '1px solid transparent',
      textColorQuaternary: textSecondary,
      textColorHoverQuaternary: text,
      textColorPressedQuaternary: text,
      // 尺寸（设计稿 .btn 30 / .btn.sm 24）
      heightSmall: '30px',
      heightTiny: '24px',
      fontSizeSmall: '12.5px',
      fontSizeTiny: '12px',
      borderRadiusSmall: radiusControl,
      borderRadiusTiny: radiusControl,
      // 危险按钮（删除类）
      colorError: dangerBg,
      colorHoverError: dangerBg,
      colorPressedError: dangerBg,
      borderError: `1px solid ${dangerBorder}`,
      borderHoverError: `1px solid ${dangerBorder}`,
      borderPressedError: `1px solid ${dangerBorder}`,
      textColorError: dangerText,
      textColorHoverError: dangerText,
      textColorPressedError: dangerText,
      rippleColor: primary,
    },
    Input: {
      color: surface,
      colorFocus: surface,
      border: `1px solid ${border}`,
      borderHover: `1px solid ${primarySoftBorder}`,
      borderFocus: `1px solid ${primary}`,
      boxShadowFocus: focusRing(dark),
      textColor: text,
      placeholderColor: textMuted,
      caretColor: primary,
      borderRadius: radiusControl,
      heightSmall: '30px',
      fontSizeSmall: '12.5px',
    },
    InternalSelection: {
      color: surface,
      colorActive: surface,
      border: `1px solid ${border}`,
      borderHover: `1px solid ${primarySoftBorder}`,
      borderFocus: `1px solid ${primary}`,
      borderActive: `1px solid ${primary}`,
      boxShadowFocus: focusRing(dark),
      boxShadowActive: focusRing(dark),
      textColor: text,
      placeholderColor: textMuted,
      caretColor: primary,
      borderRadius: radiusControl,
      heightSmall: '30px',
      fontSizeSmall: '12.5px',
      arrowColor: textMuted,
    },
    InternalSelectMenu: {
      color: surface,
      optionTextColor: textSecondary,
      optionTextColorActive: primary,
      optionColorPending: surfaceAlt,
      optionCheckColor: primary,
      borderRadius: radiusControl,
      boxShadow: shadowCard,
    },
    Card: {
      color: surface,
      colorModal: surface,
      borderColor: border,
      borderRadius: radiusCard,
      titleTextColor: text,
      textColor: textSecondary,
      paddingSmall: '14px 16px',
    },
    Tag: {
      color: surfaceAlt,
      textColor: textSecondary,
      border: `1px solid ${border}`,
      borderRadius: '6px',
      heightSmall: '20px',
      fontSizeSmall: '11.5px',
    },
    Menu: {
      itemHeight: '34px',
      borderRadius: radiusControl,
      itemColorHover: surfaceAlt,
      itemColorActive: primarySoft,
      itemColorActiveHover: primarySoft,
      itemTextColor: textSecondary,
      itemTextColorHover: text,
      itemTextColorActive: primary,
      itemTextColorActiveHover: primary,
      itemIconColor: textMuted,
      itemIconColorHover: text,
      itemIconColorActive: primary,
      itemIconColorActiveHover: primary,
    },
    Dialog: { color: surface, borderRadius: radiusCard, titleTextColor: text, textColor: textSecondary },
    Modal: { color: surface, borderRadius: radiusCard },
    Drawer: { color: surface, borderRadius: radiusCard },
    Popover: { color: surface, borderRadius: radiusControl, boxShadow: shadowCard },
    Tooltip: { color: surface, textColor: text, borderRadius: radiusControl },
    Dropdown: {
      color: surface,
      optionTextColor: textSecondary,
      optionTextColorActive: primary,
      optionColorHover: surfaceAlt,
      borderRadius: radiusControl,
      boxShadow: shadowCard,
    },
    Switch: { railColorActive: primary, buttonColor: surface },
    Checkbox: { colorChecked: primary, borderChecked: `1px solid ${primary}`, checkMarkColor: onPrimary },
    Radio: {
      buttonColorActive: primarySoft,
      buttonTextColorActive: primary,
      buttonBorderColorActive: primarySoftBorder,
      dotColorActive: primary,
    },
    Alert: {
      colorInfo: infoBg,
      colorSuccess: successBg,
      colorWarning: warningBg,
      colorError: dangerBg,
      borderInfo: `1px solid ${infoBorder}`,
      borderSuccess: `1px solid ${successBorder}`,
      borderWarning: `1px solid ${warningBorder}`,
      borderError: `1px solid ${dangerBorder}`,
      titleTextColorInfo: infoText,
      titleTextColorSuccess: successText,
      titleTextColorWarning: warningText,
      titleTextColorError: dangerText,
      contentTextColorInfo: infoText,
      contentTextColorSuccess: successText,
      contentTextColorWarning: warningText,
      contentTextColorError: dangerText,
      iconColorInfo: infoText,
      iconColorSuccess: successText,
      iconColorWarning: warningText,
      iconColorError: dangerText,
      borderRadius: radiusControl,
    },
    Message: { color: surface, textColor: text, borderRadius: radiusControl, boxShadow: shadowCard },
    Notification: { color: surface, textColor: text, borderRadius: radiusCard, boxShadow: shadowCard },
    Skeleton: { color: surfaceAlt, colorEnd: border },
    Progress: { railColor: surfaceAlt, fillColor: primary },
    Spin: { color: primary },
  }
}

/**
 * 当前主题对应的覆盖对象。每次主题变化都重新构造（读的是当时的 CSS 变量值）。
 */
export const selectOverrides = (theme: GlobalTheme | null) => buildOverrides(!!theme)
