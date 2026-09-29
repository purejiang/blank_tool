<template>
  <!-- JSON / 结构化文本域：等宽 + 自动高度。
       替代 EnvsPage `.envs-json`、PluginsPage `.plugins-json` 两处同体的
       `font-family: var(--font-family-monospace); font-size: 12px` 覆盖。 -->
  <n-input
    class="app-json-input"
    type="textarea"
    :value="modelValue"
    :placeholder="placeholder"
    :autosize="{ minRows, maxRows }"
    :disabled="disabled"
    :readonly="readonly"
    @update:value="emit('update:modelValue', $event)"
  />
</template>

<script setup lang="ts">
import { NInput } from 'naive-ui'

withDefaults(
  defineProps<{
    modelValue?: string
    placeholder?: string
    minRows?: number
    maxRows?: number
    disabled?: boolean
    readonly?: boolean
  }>(),
  { minRows: 4, maxRows: 10 },
)

const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>()
</script>

<style scoped>
/* Naive 的 textarea / input 内层元素要 `:deep()` 才够得着 */
.app-json-input :deep(.n-input__textarea-el),
.app-json-input :deep(.n-input__input-el) {
  font-family: var(--font-family-monospace);
  font-size: var(--fs-12);
  line-height: 1.6;
}
</style>
