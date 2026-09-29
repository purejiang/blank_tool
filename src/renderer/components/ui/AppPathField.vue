<template>
  <!-- 路径字段：只读/可编辑输入框 + 「浏览」按钮。
       替代 SettingsPage `.environ-path-input`(2 处)、TaskEditorPage `.te-workdir-row`、
       PortInput `.pi-path-row` 三套手写的「input + button」组合。 -->
  <div class="app-path-field">
    <n-input
      class="app-path-field-input"
      :value="modelValue"
      :placeholder="placeholder"
      :readonly="readonly"
      :disabled="disabled"
      :size="size"
      @update:value="emit('update:modelValue', $event)"
    />
    <AppButton
      variant="outline"
      :size="size === 'small' ? 'small' : 'tiny'"
      :disabled="disabled"
      :aria-label="browseLabel"
      :title="browseLabel"
      @click="emit('browse')"
    >
      <template #icon><AppIcon name="folder" /></template>
      {{ browseLabel }}
    </AppButton>
  </div>
</template>

<script setup lang="ts">
import { NInput } from 'naive-ui'

import AppIcon from './AppIcon.vue'
import AppButton from './AppButton.vue'

withDefaults(
  defineProps<{
    modelValue?: string
    placeholder?: string
    readonly?: boolean
    disabled?: boolean
    /** 按钮文案，由调用方传（仓库里有两个既有 key：settings.browse / workflow.editor.dialog.browse） */
    browseLabel: string
    size?: 'small' | 'medium'
  }>(),
  { readonly: true, size: 'small' },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'browse'): void
}>()
</script>

<style scoped>
.app-path-field {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  width: 100%;
  min-width: 0;
}

.app-path-field-input {
  flex: 1 1 auto;
  min-width: 0;
}
</style>
