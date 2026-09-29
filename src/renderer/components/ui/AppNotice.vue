<template>
  <!-- 提示条：成功/警告/错误/信息四态，各用对应语义色（不用蓝色冒充成功或错误）。
       图标 + 文案同时表达状态，不只靠颜色（可访问性要求）。

       这是应用里**唯一**的提示条：`n-alert` 全仓 15 处（含 5 处完全同构的
       「加载失败 + 重试」）都收编到这里。 -->
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
    <div v-if="$slots.action" class="app-actions app-notice-action"><slot name="action" /></div>
    <button
      v-if="closable"
      type="button"
      class="app-notice-close"
      :aria-label="t('common.close')"
      :title="t('common.close')"
      @click="emit('close')"
    >
      <AppIcon name="x" size="sm" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import AppIcon from './AppIcon.vue'

export type NoticeTone = 'success' | 'warning' | 'danger' | 'info'

const props = withDefaults(
  defineProps<{ tone?: NoticeTone; title?: string; closable?: boolean }>(),
  { tone: 'info' },
)

const emit = defineEmits<{ (e: 'close'): void }>()

const { t } = useI18n()

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
  gap: var(--gap-sm);
  padding: var(--sp-10) var(--sp-12);
  border-radius: var(--radius-control);
  border: 1px solid transparent;
  font-size: var(--fs-12-5);
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
  align-items: flex-start;
}

.app-notice-close {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: var(--sp-2);
  color: inherit;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: var(--radius-chip);
  opacity: 0.7;
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.app-notice-close:hover {
  opacity: 1;
}
</style>
