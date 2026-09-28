<template>
  <!-- 徽章：主徽章（primary-soft + primary）/ 中性（surface-alt + text-secondary）
       / 语义四色。金色只用于语义，不用蓝色顶替成功或错误。 -->
  <span class="app-badge" :class="`app-badge--${tone}`">
    <slot name="icon" />
    <slot />
  </span>
</template>

<script setup lang="ts">
export type BadgeTone = 'primary' | 'neutral' | 'success' | 'warning' | 'danger' | 'info'

withDefaults(defineProps<{ tone?: BadgeTone }>(), { tone: 'neutral' })
</script>

<style scoped>
.app-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 20px;
  padding: 0 7px;
  border-radius: 6px;
  border: 1px solid transparent;
  font-size: 11.5px;
  line-height: 1;
  white-space: nowrap;
  flex: none;
}

.app-badge--primary {
  color: var(--primary);
  background: var(--primary-soft);
  border-color: var(--primary-soft-border);
}

.app-badge--neutral {
  color: var(--text-secondary);
  background: var(--surface-alt);
  border-color: var(--border);
}

.app-badge--success {
  color: var(--success-text);
  background: var(--success-bg);
  border-color: var(--success-border);
}

.app-badge--warning {
  color: var(--warning-text);
  background: var(--warning-bg);
  border-color: var(--warning-border);
}

.app-badge--danger {
  color: var(--danger-text);
  background: var(--danger-bg);
  border-color: var(--danger-border);
}

.app-badge--info {
  color: var(--info-text);
  background: var(--info-bg);
  border-color: var(--info-border);
}
</style>
