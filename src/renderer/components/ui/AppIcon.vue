<template>
  <svg class="i" :class="sizeClass" :style="sizeStyle" aria-hidden="true" focusable="false">
    <use :href="`#i-${name}`" />
  </svg>
</template>

<script setup lang="ts">
/**
 * 统一图标组件。
 *
 * 形状来自 assets/icons/sprite.ts 的 sprite（`<use href="#i-xxx">`），
 * 尺寸/描边口径与设计契约 docs/ui-prompts/ui-preview.html §2 的 `svg.i` 一致：
 * 默认 15px、stroke 1.8、round cap/join、fill:none、颜色继承 currentColor。
 *
 * 替换 lucide-vue-next 的原因：lucide 的描边/端点约定与设计契约不同，两套混用
 * 会出现"同一排按钮图标粗细不一"。现在全项目只有这一套。
 *
 * 颜色：没有 color 属性，直接用 CSS `color` 控制（`stroke: currentColor` 会跟随）。
 * 原来 `<n-icon color="var(--x)">` 的写法换成 `style="color: var(--x)"`。
 */
import { computed } from 'vue'

import { ICON_SYMBOLS } from '@assets/icons/sprite'

const props = withDefaults(
  defineProps<{
    /** 图标名（不含 `i-` 前缀），对应 sprite.ts 里的 symbol id */
    name: string
    /**
     * sm 12px / md 15px（默认）/ lg 18px；传数字则按 px 精确控制
     * （只在空态插画这类"图标当插图用"的地方才需要，别拿它当常规档位）。
     */
    size?: 'sm' | 'md' | 'lg' | number
  }>(),
  { size: 'md' },
)

const sizeClass = computed(() =>
  typeof props.size === 'string' && props.size !== 'md' ? props.size : undefined,
)

const sizeStyle = computed(() =>
  typeof props.size === 'number'
    ? { width: `${props.size}px`, height: `${props.size}px` }
    : undefined,
)

// 开发态兜底：名字写错时 sprite 会静默渲染成空白，最难查，所以直接报警。
if (import.meta.env?.DEV) {
  const known = new Set(Array.from(ICON_SYMBOLS.matchAll(/id="i-([a-z0-9-]+)"/g), (m) => m[1]))
  if (!known.has(props.name)) {
    console.warn(`[AppIcon] 未知图标 "i-${props.name}"，请到 assets/icons/sprite.ts 补 symbol`)
  }
}
</script>

<style scoped>
.i {
  width: 15px;
  height: 15px;
  flex: none;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.i.sm {
  width: 12px;
  height: 12px;
}

.i.lg {
  width: 18px;
  height: 18px;
}
</style>
