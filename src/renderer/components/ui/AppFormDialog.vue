<template>
  <!-- 表单/信息对话框骨架：`n-modal preset="card"` + 统一宽度 + 页脚。
       替代 6 处复制粘贴的 n-modal 外壳（EnvsPage / PluginsPage /
       WorkflowsListPage / RunInputsDialog / WorkflowInfoDialog / WorkflowEditorPage
       的问题弹窗），它们各自内联 `:style="{ width: '4xxpx' }"`。

       Naive 的 `preset="card"` 属性原样透传，只统一 width / maskClosable / 页脚排布，
       所以行为与改前一致。 -->
  <n-modal
    :show="show"
    preset="card"
    :title="title"
    :style="{ width }"
    :mask-closable="maskClosable"
    :closable="closable"
    :aria-label="title"
    @update:show="emit('update:show', $event)"
  >
    <slot />
    <template v-if="$slots.footer" #footer>
      <AppDialogFooter><slot name="footer" /></AppDialogFooter>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { NModal } from 'naive-ui'

import AppDialogFooter from './AppDialogFooter.vue'

withDefaults(
  defineProps<{
    show: boolean
    title?: string
    /** 面板宽度。默认 460px（与改前各站点的 420~560px 区间中位对齐） */
    width?: string
    maskClosable?: boolean
    closable?: boolean
  }>(),
  { width: '460px', maskClosable: true, closable: true },
)

const emit = defineEmits<{ (e: 'update:show', value: boolean): void }>()
</script>
