<template>
  <!-- 搜索输入框：clearable + 可选放大镜。
       替代 TaskListView `.tl-search`(240px)、RunListView `.rl-search`(220px)、
       WorkflowsListPage 的裸 n-input，以及 WorkflowNodePalette 里那套手写的
       `<label class="search"><AppIcon/><input/></label>`（第二种实现）。 -->
  <n-input
    class="app-search-input"
    :value="modelValue"
    :style="{ width }"
    :size="size"
    :placeholder="placeholder"
    clearable
    @update:value="emit('update:modelValue', $event)"
  >
    <template v-if="showIcon" #prefix>
      <AppIcon name="search" size="sm" />
    </template>
  </n-input>
</template>

<script setup lang="ts">
import { NInput } from 'naive-ui'

import AppIcon from './AppIcon.vue'

withDefaults(
  defineProps<{
    modelValue?: string
    placeholder?: string
    /** 宽度。默认 240px（与 TaskListView 现有口径一致） */
    width?: string
    size?: 'tiny' | 'small' | 'medium'
    /** 放大镜前缀。默认关，保持三个既有站点的现状；新页面建议开 */
    showIcon?: boolean
  }>(),
  { width: '240px', size: 'small', showIcon: false },
)

const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>()
</script>

<style scoped>
.app-search-input {
  flex: none;
}
</style>
