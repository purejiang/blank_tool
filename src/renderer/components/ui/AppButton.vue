<template>
  <!-- 统一按钮：四种用色变体 + 图标槽 + 键盘焦点环（由 ui.css 的 :focus-visible 提供）。
       变体 → Naive type 映射，颜色全部来自 tokens.css（见 theme/overrides.ts）：
         primary   → primary 实底 + on-primary 字
         secondary → primary-soft 底 + primary 字 + primary-soft-border 边
         outline   → 透明底 + primary 字 + border 边，hover 变 primary-soft
         ghost     → 透明底 + text-secondary 字，hover 变 surface-alt
         danger    → danger 语义色（仅用于破坏性操作） -->
  <n-button
    class="app-btn"
    :type="naiveType"
    :theme-overrides="variantOverrides"
    :size="size === 'sm' ? 'tiny' : 'small'"
    :disabled="disabled"
    :loading="loading"
    :block="block"
    :circle="iconOnly"
    :aria-label="ariaLabel"
    :title="title"
    attr-type="button"
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

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariant
    size?: 'sm' | 'md'
    disabled?: boolean
    loading?: boolean
    block?: boolean
    /** 只有图标时必须给 aria-label（可访问性要求） */
    ariaLabel?: string
    title?: string
    iconOnly?: boolean
  }>(),
  { variant: 'outline', size: 'sm' },
)

const emit = defineEmits<{ (e: 'click', event: MouseEvent): void }>()

const naiveType = computed(() => (props.variant === 'primary' ? ('primary' as const) : ('default' as const)))

/**
 * 非主按钮一律用 `type="default"` + 组件级 theme-overrides 实现设计稿的四套用色。
 * 值写成 CSS 变量：主题切换自动跟随，且这里不出现任何硬编码颜色。
 */
const variantOverrides = computed(() => {
  switch (props.variant) {
    case 'secondary':
      // 次按钮：primary-soft 底 + primary 字 + primary-soft-border 边
      return {
        color: 'var(--primary-soft)',
        colorHover: 'var(--primary-soft)',
        colorPressed: 'var(--primary-soft)',
        colorFocus: 'var(--primary-soft)',
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
      // 描边按钮：透明底 + primary 字 + border 边，hover 背景 primary-soft
      return {
        color: 'transparent',
        colorHover: 'var(--primary-soft)',
        colorPressed: 'var(--primary-soft)',
        colorFocus: 'var(--primary-soft)',
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
      // 幽灵按钮：透明底 + text-secondary 字，hover 背景 surface-alt
      return {
        color: 'transparent',
        colorHover: 'var(--surface-alt)',
        colorPressed: 'var(--surface-alt)',
        colorFocus: 'var(--surface-alt)',
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
      // 破坏性操作：danger 语义色（不用实心大红）
      return {
        color: 'var(--danger-bg)',
        colorHover: 'var(--danger-bg)',
        colorPressed: 'var(--danger-bg)',
        colorFocus: 'var(--danger-bg)',
        textColor: 'var(--danger-text)',
        textColorHover: 'var(--danger-text)',
        textColorPressed: 'var(--danger-text)',
        textColorFocus: 'var(--danger-text)',
        border: '1px solid var(--danger-border)',
        borderHover: '1px solid var(--danger-border)',
        borderPressed: '1px solid var(--danger-border)',
        borderFocus: '1px solid var(--danger-border)',
        rippleColor: 'var(--danger-text)',
      }
    default:
      return undefined
  }
})
</script>

<style scoped>
/* 极小尺寸下压一点内边距，保证 24px 高度里图标与文字不挤 */
.app-btn :deep(.n-button__content) {
  gap: 6px;
}
</style>
