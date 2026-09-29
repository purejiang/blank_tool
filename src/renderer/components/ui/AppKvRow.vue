<template>
  <!-- 描述列表的一行：label（可选固定宽）+ value + 可选行内动作。
       `mono` 用于版本号/路径/端口名这类等宽值；`keyMono` 用于 §run_id 这种
       本身就是标识符的键（RunDetailDrawer 口径）。 -->
  <div class="app-kv-row">
    <span class="app-kv-key" :class="{ 'app-kv-key--mono': keyMono }" :style="labelWidth ? { minWidth: labelWidth } : undefined">
      {{ label }}
    </span>
    <span class="app-kv-value" :class="{ 'app-kv-value--mono': mono }"><slot /></span>
    <span v-if="$slots.action" class="app-kv-action"><slot name="action" /></span>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    /** value 用等宽字体（路径 / 版本 / 标识符） */
    mono?: boolean
    /** label 用等宽字体（键本身就是标识符） */
    keyMono?: boolean
    /** 固定 label 列宽，如 '110px' / '140px'；不传则按内容自适应 */
    labelWidth?: string
  }>(),
  {},
)
</script>

<style scoped>
.app-kv-row {
  display: flex;
  align-items: baseline;
  gap: var(--gap-md);
  min-width: 0;
  padding: var(--sp-4) 0;
  font-size: var(--fs-12);
}

.app-kv-key {
  flex: none;
  color: var(--text-muted);
}

.app-kv-key--mono {
  font-family: var(--font-family-monospace);
  color: var(--text-secondary);
}

.app-kv-value {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--text-secondary);
  word-break: break-all;
  white-space: pre-wrap;
}

.app-kv-value--mono {
  font-family: var(--font-family-monospace);
}

.app-kv-action {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--sp-4);
}
</style>
