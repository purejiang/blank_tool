<template>
  <!-- 概览数字卡（首页用）：标签 + 数值 + 备注，可带图标与语义色调。 -->
  <AppCard class="app-stat" hoverable>
    <div class="app-stat-row">
      <span class="app-stat-icon" :class="`app-stat-icon--${tone}`">
        <slot name="icon" />
      </span>
      <div class="app-stat-body">
        <div class="app-stat-label">{{ label }}</div>
        <div class="app-stat-value">{{ value }}</div>
        <div v-if="hint" class="app-stat-hint">{{ hint }}</div>
      </div>
    </div>
  </AppCard>
</template>

<script setup lang="ts">
import AppCard from './AppCard.vue'

withDefaults(
  defineProps<{
    label: string
    value: string | number
    hint?: string
    tone?: 'primary' | 'success' | 'warning' | 'danger'
  }>(),
  { tone: 'primary' },
)
</script>

<style scoped>
.app-stat-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.app-stat-icon {
  width: 36px;
  height: 36px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-control);
  background: var(--surface-alt);
  color: var(--text-muted);
}

.app-stat-icon--primary {
  color: var(--primary);
  background: var(--primary-soft);
}

.app-stat-icon--success {
  color: var(--success-text);
  background: var(--success-bg);
}

.app-stat-icon--warning {
  color: var(--warning-text);
  background: var(--warning-bg);
}

.app-stat-icon--danger {
  color: var(--danger-text);
  background: var(--danger-bg);
}

.app-stat-body {
  min-width: 0;
}

.app-stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.app-stat-value {
  margin-top: 2px;
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.app-stat-hint {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--text-muted);
}
</style>
