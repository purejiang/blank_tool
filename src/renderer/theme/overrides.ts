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
  const radiusChip = readToken('--radius-chip', '8px')
  const shadowCard = readToken('--shadow-card', '0 1px 2px rgba(15,23,42,.06)')

  // 控件密度与字号（tokens.css 的「非颜色维度」块）。这三个高度是设计稿口径：
  // .btn.sm = 24px（Naive tiny）/ .btn = 30px（Naive small）/ medium = 34px。
  const controlHTiny = readToken('--control-h-tiny', '24px')
  const controlHSm = readToken('--control-h-sm', '30px')
  const controlHMd = readToken('--control-h-md', '34px')
  const fsTiny = readToken('--fs-12', '12px')
  const fsSmall = readToken('--fs-12-5', '12.5px')
  const fsMd = readToken('--fs-14', '14px')
  const fsAux = readToken('--fs-11-5', '11.5px')
  const fsBody = readToken('--fs-13', '13px')

  return {
    common: {
      fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
      fontSize: fsBody,
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
    /**
     * ⚠️ Naive Button 的一个反直觉之处，改这里之前务必先读：
     * 当 `type="default"` 时，`secondary` / `tertiary` / `quaternary` 三个变体的
     * **文字色读的是无后缀的 `self.textColor`**、**边框读无后缀的 `self.border`**
     * （见 node_modules/naive-ui/es/button/src/Button.mjs 的 `typeTextColor` 与
     * borderProps 分支：`typeIsDefault ? self.textColor : ...`）。
     * 因此 `textColorSecondary` / `textColorTertiary` / `textColorQuaternary` /
     * `borderSecondary` / `borderTertiary` / `borderQuaternary` 这几个键在
     * `type="default"` 下**永远不会被读取**。下面保留它们只为 Naive 自身的
     * `type="tertiary"` 等路径，不要以为改了它们就能改掉次按钮的字色。
     * 应用层那套语义变体（primary/secondary/outline/ghost/danger…）由
     * components/ui/AppButton.vue 的组件级 themeOverrides 提供，它正是靠
     * 「写无后缀键」来生效的 —— 那几十行不是冗余，不能删。
     */
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
      // 尺寸（设计稿 .btn 30 / .btn.sm 24；medium 沿用 Naive 的 34px，只是显式化）
      heightTiny: controlHTiny,
      heightSmall: controlHSm,
      heightMedium: controlHMd,
      fontSizeTiny: fsTiny,
      fontSizeSmall: fsSmall,
      fontSizeMedium: fsMd,
      borderRadiusSmall: radiusControl,
      borderRadiusTiny: radiusControl,
      borderRadiusMedium: radiusControl,
      // 危险按钮（删除类）。
      // ⚠️ 这里用「实心红」，**不是**应用里那种软底（danger-bg + danger-text）风格：
      // Naive 的 `type="error" quaternary`（纯文字/幽灵态）读的也是 `colorError`
      // 当**文字色**（见 Button.mjs 的 `tertiary || quaternary` 分支 —— 它取
      // `self[createKey('color', mergedType)]`）。此前把 colorError 设成 dangerBg，
      // 结果全仓 14+ 个 `type="error" quaternary` 删除按钮的文字色变成 #FEF2F2，
      // 在浅色主题下几乎不可见（2026 实测：解析值 text=#FEF2F2）。
      // 现在全局统一成规范口径：实心 = dangerText 底 + on-primary 字，纯文字/幽灵 = dangerText 字。
      // 应用想要的那种「软底危险按钮」由 components/ui/AppButton.vue 的
      // `variant="danger"` 用组件级覆盖提供，那是刻意的例外，不是全局默认。
      colorError: dangerText,
      colorHoverError: dangerText,
      colorPressedError: dangerText,
      borderError: `1px solid ${dangerText}`,
      borderHoverError: `1px solid ${dangerText}`,
      borderPressedError: `1px solid ${dangerText}`,
      textColorError: onPrimary,
      textColorHoverError: onPrimary,
      textColorPressedError: onPrimary,
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
    // ⚠️ Tag 的 size → key 映射：`size="tiny"` 读 heightTiny/fontSizeTiny，
    // `size="small"` 读 heightSmall/fontSizeSmall。此前只覆盖了 small，于是 tiny
    // 落到 common 的 16px/12px「暗档」——同一种标签两个尺寸、且小的那档不受 token 管。
    // 现在把两档都显式钉住（tiny 的 16px/12px 就是改前的实际生效值，视觉不变）。
    // 圆角原先硬编码 '6px'（全仓最后一个裸圆角字面量），改用 --radius-chip，
    // 与 AppBadge 收敛到同一档。
    Tag: {
      color: surfaceAlt,
      textColor: textSecondary,
      border: `1px solid ${border}`,
      borderRadius: radiusChip,
      heightTiny: '16px',
      heightSmall: '20px',
      fontSizeTiny: fsTiny,
      fontSizeSmall: fsAux,
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
