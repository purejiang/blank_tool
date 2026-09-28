<template>
  <!-- 运行/节点状态徽章：**图标 + 文字 + 颜色**三通道表达，不只靠颜色区分。 -->
  <AppBadge :tone="tone">
    <template #icon>
      <n-icon size="12" :class="{ 'sb-spin': status === 'running' }"><component :is="icon" /></n-icon>
    </template>
    {{ t(statusI18nKey(status)) }}
  </AppBadge>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { Ban, CheckCircle2, HelpCircle, Loader2, MinusCircle, XCircle } from 'lucide-vue-next'

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
      return Loader2
    case 'succeeded':
      return CheckCircle2
    case 'failed':
      return XCircle
    case 'skipped':
      return MinusCircle
    case 'cancelled':
      return Ban
    default:
      return HelpCircle
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
