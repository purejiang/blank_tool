<template>
  <!--
    统一的「图标按钮」：全站所有只有图标、没有文案的按钮都走这一个组件。

    规则靠类型强制，而不是靠人记：
      - label 是必填的 —— 图标按钮没有可见文案，所以*必须*有悬停提示；
        它同时作为 aria-label（可见文案缺失时的可访问名）
      - 有文案的按钮不要用本组件，也不应该带提示（除非提示承载的是禁用原因，
        或标签之外的补充信息，见 RunControls / PackagePage 的既有例外）

    结构上必须有一层 <span> 根节点，三个理由都是硬约束：
      1. n-dropdown 之类的 trigger 需要单元素根节点；n-tooltip 当根节点时是
         「触发元素 + teleport」的碎片，dropdown 会绑不上
      2. Naive 的 disabled 按钮不派发鼠标事件 —— 外面套一层后悬停事件照常冒泡，
         禁用态下的提示不会丢（ToolInstallModal 里曾用 .tim-btn-wrap 手写补丁）
      3. 父级用 :deep(.n-button) 之类定位（如 RunHistory 的 margin-left:auto）时
         需要一个稳定的包裹元素可指向

    $attrs 全部下沉到内部 n-button（type/size/disabled/loading/quaternary/text/
    circle/class/data-testid 照传），所以替换 n-button 不会影响既有选择器与测试。
  -->
  <span class="app-icon-btn">
    <n-tooltip :placement="placement" trigger="hover">
      <template #trigger>
        <n-button
          v-bind="$attrs"
          :aria-label="ariaLabel || label"
          @click="emit('click', $event)"
        >
          <template #icon>
            <n-icon :size="iconSize" :color="iconColor"><component :is="icon" /></n-icon>
          </template>
          <!-- 默认插槽透传：少数按钮在图标之外还有角标（RunControls 的抓包圆点） -->
          <slot />
        </n-button>
      </template>{{ label }}</n-tooltip>
  </span>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import { NButton, NIcon, NTooltip } from 'naive-ui'

defineOptions({ inheritAttrs: false })

withDefaults(defineProps<{
  /** 图标组件（lucide-vue-next 的图标） */
  icon: Component
  /** 悬停提示文案；同时作为 aria-label（除非单独给了 ariaLabel） */
  label: string
  /** 可访问名与提示文案不同的少数场合（如「功能」菜单的提示会随状态变化） */
  ariaLabel?: string
  placement?: 'top' | 'top-start' | 'top-end' | 'bottom' | 'bottom-start' | 'bottom-end' | 'left' | 'right'
  iconSize?: number
  /** 图标颜色（如置顶态变绿）；不传则继承按钮颜色 */
  iconColor?: string
}>(), {
  placement: 'top',
  iconSize: 14,
})

const emit = defineEmits<{ (e: 'click', ev: MouseEvent): void }>()
</script>

<style scoped>
.app-icon-btn {
  display: inline-flex;
  align-items: center;
  /* 包裹层取代按钮成为 flex 项，默认不参与收缩，避免挤掉图标 */
  flex: none;
}
</style>
