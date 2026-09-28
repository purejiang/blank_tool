<template>
  <!-- 提示条：成功/警告/错误/信息四态，各用对应语义色（不用蓝色冒充成功或错误）。
       图标 + 文案同时表达状态，不只靠颜色（可访问性要求）。 -->
  <div
    class="app-notice"
    :class="`app-notice--${tone}`"
    :role="tone === 'danger' ? 'alert' : 'status'"
  >
    <AppIcon :name="icon" class="app-notice-icon" />
    <div class="app-notice-body">
      <div v-if="title" class="app-notice-title">{{ title }}</div>
      <div class="app-notice-text"><slot /></div>
    </div>
    <div v-if="$slots.action" class="app-notice-action"><slot name="action" /></div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@components/ui/AppIcon.vue'

export type NoticeTone = 'success' | 'warning' | 'danger' | 'info'

const props = withDefaults(defineProps<{ tone?: NoticeTone; title?: string }>(), { tone: 'info' })

const icon = computed(() => {
  switch (props.tone) {
    case 'success':
      return 'check'
    case 'warning':
      return 'alert'
    case 'danger':
      return 'x-circle'
    default:
      return 'info'
  }
})
</script>

<style scoped>
.app-notice {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-control);
  border: 1px solid transparent;
  font-size: 12.5px;
  line-height: 1.5;
}

.app-notice--success {
  color: var(--success-text);
  background: var(--success-bg);
  border-color: var(--success-border);
}

.app-notice--warning {
  color: var(--warning-text);
  background: var(--warning-bg);
  border-color: var(--warning-border);
}

.app-notice--danger {
  color: var(--danger-text);
  background: var(--danger-bg);
  border-color: var(--danger-border);
}

.app-notice--info {
  color: var(--info-text);
  background: var(--info-bg);
  border-color: var(--info-border);
}

.app-notice-icon {
  flex: none;
  margin-top: 1px;
}

.app-notice-body {
  flex: 1;
  min-width: 0;
}

.app-notice-title {
  font-weight: 600;
}

.app-notice-action {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
