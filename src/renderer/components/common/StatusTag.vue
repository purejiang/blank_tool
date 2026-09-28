<template>
  <!-- 全站统一状态徽章（docs/08 §5-3）：运行中/成功/失败/跳过/取消/未运行。
       颜色语义只在一处定义，运行列表与运行详情共用。 -->
  <n-tag :type="tagType" size="small" :bordered="false" class="status-tag">
    <template v-if="status === 'running'" #icon>
      <n-icon size="13" class="status-tag-spin"><Loader2 /></n-icon>
    </template>
    {{ t(statusI18nKey(status)) }}
  </n-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon, NTag } from 'naive-ui'
import { Loader2 } from 'lucide-vue-next'

import { statusI18nKey, statusTagType, type RunStatusKey } from '@components/tasks/runFormat'

const props = defineProps<{
  status: RunStatusKey
}>()

const { t } = useI18n()

const tagType = computed(() => statusTagType(props.status))
</script>

<style scoped>
.status-tag {
  font-weight: 500;
}

.status-tag-spin {
  animation: status-tag-rotate 1s linear infinite;
}

@keyframes status-tag-rotate {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .status-tag-spin {
    animation: none;
  }
}
</style>
