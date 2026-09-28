<template>
  <!-- 运行/节点状态徽章：**图标 + 文字 + 颜色**三通道表达，不只靠颜色区分。 -->
  <AppBadge :tone="tone">
    <template #icon>
      <AppIcon :name="icon" size="sm" :class="{ 'sb-spin': status === 'running' }" />
    </template>
    {{ t(statusI18nKey(status)) }}
  </AppBadge>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@components/ui/AppIcon.vue'

import AppBadge, { type BadgeTone } from './AppBadge.vue'
import { statusI18nKey, type RunStatusKey } from '@components/tasks/runFormat'

const props = defineProps<{ status: RunStatusKey }>()

const { t } = useI18n()

const tone = computed<BadgeTone>(() => {
  switch (props.status) {
    case 'running':
      return 'info'
    case 'succeeded':
      return 'success'
    case 'failed':
      return 'danger'
    case 'skipped':
    case 'cancelled':
      return 'neutral'
    default:
      return 'neutral'
  }
})

const icon = computed(() => {
  switch (props.status) {
    case 'running':
      return 'spinner'
    case 'succeeded':
      return 'check'
    case 'failed':
      return 'x-circle'
    case 'skipped':
      return 'minus-circle'
    case 'cancelled':
      return 'ban'
    default:
      return 'help'
  }
})
</script>

<style scoped>
.sb-spin {
  animation: sb-rotate 1s linear infinite;
}

@keyframes sb-rotate {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .sb-spin {
    animation: none;
  }
}
</style>
