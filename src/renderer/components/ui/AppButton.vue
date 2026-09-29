<template>
  <!-- 统一按钮：8 个语义变体 + 三档尺寸 + 图标槽 + 键盘焦点环（由 ui.css 提供）。
       **应用里的按钮一律走这里**，不要再裸写 <n-button>（有测试拦着，见
       tests/unit/styles/ui-kit-adoption.test.ts）。

       变体 → Naive 属性映射，颜色全部来自 token（见 theme/overrides.ts）：
         primary      → type=primary，实底主色 + on-primary 字
         secondary    → secondary 软底（primary-soft + primary 字 + soft 边）
         outline      → tertiary 描边（透明底 + primary 字 + border 边）
         ghost        → quaternary 幽灵（透明底 + text-secondary 字，hover surface-alt）
         danger       → 软底危险（danger-bg + danger-text + danger-border）
         danger-ghost → 纯文字危险（透明底 + danger-text 字，hover danger-bg）——删除类首选
         warning      → 软底警告（warning-bg + warning-text）
         dashed       → 虚线描边（用于「添加一项」这类次要创建动作）

       为什么还需要组件级 themeOverrides？因为 Naive 在 `type="default"` 下把
       secondary / tertiary / quaternary 的**文字色读无后缀的 self.textColor**、
       **边框读无后缀的 self.border**（Button.mjs 的 typeTextColor 与 borderProps
       分支），并**忽略 `textColorSecondary` / `borderTertiary` 这类带后缀的键**。
       实测：裸 `<n-button secondary>` 的文字色是 text-secondary，不是主色。
       所以这几行不是冗余 —— 它们是唯一能表达这套变体的方式，不要删。 -->
  <n-button
    class="app-btn"
    :type="naiveType"
    :secondary="!!secondary"
    :tertiary="!!tertiary"
    :quaternary="!!quaternary"
    :dashed="!!dashed"
    :theme-overrides="variantOverrides"
    :size="size"
    :disabled="disabled"
    :loading="loading"
    :block="block"
    :circle="iconOnly"
    :aria-label="ariaLabel"
    :title="title"
    attr-type="button"
    v-bind="$attrs"
    @click="emit('click', $event)"
  >
    <template v-if="$slots.icon" #icon>
      <slot name="icon" />
    </template>
    <slot />
  </n-button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NButton } from 'naive-ui'

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'outline'
  | 'ghost'
  | 'danger'
  | 'danger-ghost'
  | 'warning'
  | 'dashed'

/** Naive 自己的尺寸名，1:1 透传，不再做 sm/md 二次映射。 */
export type ButtonSize = 'tiny' | 'small' | 'medium'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariant
    /** tiny = 24px（设计稿 .btn.sm）/ small = 30px（.btn）/ medium = 34px */
    size?: ButtonSize
    disabled?: boolean
    loading?: boolean
    block?: boolean
    /** 只有图标时必须给 aria-label（可访问性要求） */
    ariaLabel?: string
    title?: string
    iconOnly?: boolean
  }>(),
  { variant: 'outline', size: 'small' },
)

const emit = defineEmits<{ (e: 'click', event: MouseEvent): void }>()

/** Naive 自带的类型/形态属性；其余一律靠 variantOverrides 里的无后缀键。 */
const naiveType = computed(() => {
  switch (props.variant) {
    case 'primary':
      return 'primary' as const
    case 'danger':
    case 'danger-ghost':
      return 'error' as const
    case 'warning':
      return 'warning' as const
    default:
      return 'default' as const
  }
})

const secondary = computed(() => props.variant === 'secondary')
const tertiary = computed(() => props.variant === 'outline')
const quaternary = computed(() => props.variant === 'ghost' || props.variant === 'danger-ghost')
const dashed = computed(() => props.variant === 'dashed')

/**
 * 组件级覆盖。值写成 CSS 变量：主题切换自动跟随，这里不出现任何硬编码颜色。
 */
const variantOverrides = computed(() => {
  switch (props.variant) {
    case 'secondary':
      // 软底：primary-soft 底 + primary 字 + primary-soft-border 边。
      // 底色走 ConfigProvider 的 colorSecondary / colorHoverSecondary（已是对的值），
      // 这里只需补 Naive 在本分支**读不到**的那两个：文字色与边框都取无后缀键。
      return {
        textColor: 'var(--primary)',
        textColorHover: 'var(--primary-hover)',
        textColorPressed: 'var(--primary-active)',
        textColorFocus: 'var(--primary-hover)',
        border: '1px solid var(--primary-soft-border)',
        borderHover: '1px solid var(--primary-soft-border)',
        borderPressed: '1px solid var(--primary-soft-border)',
        borderFocus: '1px solid var(--primary-soft-border)',
        rippleColor: 'var(--primary)',
      }
    case 'outline':
      // 描边：透明底 + primary 字 + border 边，hover 变 primary-soft。
      // 底色走 ConfigProvider 的 colorTertiary / colorTertiaryHover。
      return {
        textColor: 'var(--primary)',
        textColorHover: 'var(--primary-hover)',
        textColorPressed: 'var(--primary-active)',
        textColorFocus: 'var(--primary-hover)',
        border: '1px solid var(--border)',
        borderHover: '1px solid var(--primary-soft-border)',
        borderPressed: '1px solid var(--primary-soft-border)',
        borderFocus: '1px solid var(--primary)',
        rippleColor: 'var(--primary)',
      }
    case 'ghost':
      // 幽灵：透明底 + text-secondary 字，hover 背景 surface-alt。
      // 底色与 hover 底走 ConfigProvider 的 colorQuaternary / colorQuaternaryHover。
      return {
        textColor: 'var(--text-secondary)',
        textColorHover: 'var(--text)',
        textColorPressed: 'var(--text)',
        textColorFocus: 'var(--text)',
        border: '1px solid transparent',
        borderHover: '1px solid transparent',
        borderPressed: '1px solid transparent',
        borderFocus: '1px solid transparent',
        rippleColor: 'var(--text-secondary)',
      }
    case 'danger':
      // 软底危险：走 type="error" 的**带后缀**键（实心分支读它们），
      // 覆盖掉全局的实心红（见 theme/overrides.ts 的说明）。
      return {
        colorError: 'var(--danger-bg)',
        colorHoverError: 'var(--danger-bg)',
        colorPressedError: 'var(--danger-bg)',
        colorFocusError: 'var(--danger-bg)',
        textColorError: 'var(--danger-text)',
        textColorHoverError: 'var(--danger-text)',
        textColorPressedError: 'var(--danger-text)',
        textColorFocusError: 'var(--danger-text)',
        borderError: '1px solid var(--danger-border)',
        borderHoverError: '1px solid var(--danger-border)',
        borderPressedError: '1px solid var(--danger-border)',
        borderFocusError: '1px solid var(--danger-border)',
        rippleColor: 'var(--danger-text)',
      }
    case 'danger-ghost':
      // 纯文字危险（删除类首选）。实测要点（易错，别照抄上面几档）：
      //   · 文字色读**无后缀** self.textColor ✅
      //   · 底色读 colorQuaternary*（这一档不是 colorError）→ 想要 danger-bg 的
      //     hover 反馈必须覆盖 colorQuaternaryHover
      //   · 边框读**带后缀**的 borderError*（type 决定），不是无后缀 border
      // 这一档也是全仓 14+ 个删除按钮曾经文字色 = danger-bg（几乎不可见）的修复点。
      return {
        textColor: 'var(--danger-text)',
        textColorHover: 'var(--danger-text)',
        textColorPressed: 'var(--danger-text)',
        textColorFocus: 'var(--danger-text)',
        colorQuaternary: 'transparent',
        colorQuaternaryHover: 'var(--danger-bg)',
        colorQuaternaryPressed: 'var(--danger-bg)',
        colorQuaternaryFocus: 'var(--danger-bg)',
        borderError: '1px solid transparent',
        borderHoverError: '1px solid transparent',
        borderPressedError: '1px solid transparent',
        borderFocusError: '1px solid transparent',
        rippleColor: 'var(--danger-text)',
      }
    case 'warning':
      // 软底警告：type="warning" 的实心分支读带后缀键
      return {
        colorWarning: 'var(--warning-bg)',
        colorHoverWarning: 'var(--warning-bg)',
        colorPressedWarning: 'var(--warning-bg)',
        colorFocusWarning: 'var(--warning-bg)',
        textColorWarning: 'var(--warning-text)',
        textColorHoverWarning: 'var(--warning-text)',
        textColorPressedWarning: 'var(--warning-text)',
        textColorFocusWarning: 'var(--warning-text)',
        borderWarning: '1px solid var(--warning-border)',
        borderHoverWarning: '1px solid var(--warning-border)',
        borderPressedWarning: '1px solid var(--warning-border)',
        borderFocusWarning: '1px solid var(--warning-border)',
        rippleColor: 'var(--warning-text)',
      }
    case 'dashed':
      // 虚线「添加一项」。这一档走 Naive 的 `ghost || dashed` 分支，实测要点：
      //   · 文字色读**textColorGhost***（该分支**完全不读** self.textColor，
      //     所以上面几档那套无后缀写法在这里无效）
      //   · 边框读无后缀 self.border ✅（border-style 由 Naive 的
      //     .n-button--dashed 类改成 dashed）
      //   · 背景在该分支里被 Naive 写死成 `#0000`（不可覆盖），所以虚线按钮
      //     **没有 hover 底色**，hover 反馈只靠边框变色。
      return {
        textColorGhost: 'var(--primary)',
        textColorGhostHover: 'var(--primary-hover)',
        textColorGhostPressed: 'var(--primary-active)',
        textColorGhostFocus: 'var(--primary-hover)',
        border: '1px solid var(--primary-soft-border)',
        borderHover: '1px solid var(--primary)',
        borderPressed: '1px solid var(--primary)',
        borderFocus: '1px solid var(--primary)',
        rippleColor: 'var(--primary)',
      }
    default:
      // primary 完全由 ConfigProvider 的 theme/overrides.ts 提供，无需组件级覆盖
      return undefined
  }
})
</script>

<style scoped>
/* 极小尺寸下压一点内边距，保证 24px 高度里图标与文字不挤 */
.app-btn :deep(.n-button__content) {
  gap: var(--sp-6);
}
</style>
