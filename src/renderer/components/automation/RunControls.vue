<template>
  <div class="run-controls">
    <n-select
      :value="autoDeviceId"
      :options="deviceOptions"
      size="small"
      :placeholder="t('automation.selectDevice')"
      @update:value="emit('update:autoDeviceId', $event)"
    />
    <n-tooltip placement="top">
      <template #trigger>
        <n-checkbox
          :checked="captureTraffic"
          size="small"
          class="capture-toggle"
          @update:checked="emit('update:captureTraffic', $event)"
        >
          {{ t('automation.captureTrafficShort') }}
        </n-checkbox>
      </template>
      {{ t('automation.captureTrafficHint') }}
    </n-tooltip>
    <n-tooltip v-if="!running" :disabled="canRun" placement="top">
      <template #trigger>
        <n-button type="primary" size="small" :disabled="!canRun" class="run-btn" @click="emit('run')">
          <template #icon><n-icon><Play /></n-icon></template>
          {{ t('automation.run') }}
        </n-button>
      </template>
      {{ !autoDeviceId ? t('automation.noDevice') : t('automation.noScriptSelected') }}
    </n-tooltip>
    <n-button v-else type="warning" size="small" class="run-btn" @click="emit('stop')">
      <template #icon><n-icon><Square /></n-icon></template>
      {{ t('automation.stop') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NCheckbox, NSelect, NIcon, NTooltip } from 'naive-ui'
import { Play, Square } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'

defineProps<{
  autoDeviceId: string
  /** Run-time option: capture network traffic for this run. */
  captureTraffic: boolean
  running: boolean
  canRun: boolean
}>()

const emit = defineEmits<{
  (e: 'update:autoDeviceId', v: string): void
  (e: 'update:captureTraffic', v: boolean): void
  (e: 'run'): void
  (e: 'stop'): void
}>()

const { t } = useI18n()
const deviceStore = useDeviceStore()
const deviceOptions = computed(() =>
  deviceStore.devices.map((d: any) => ({
    label: `${d.name || d.id}${d.status ? ' (' + d.status + ')' : ''}`,
    value: d.id,
  })),
)
</script>

<style scoped>
/* single root so the parent column can lay it out; ONE row — the device
   select absorbs the slack, the run button is the primary action, and
   traffic capture is a short label (full explanation lives in its tooltip) */
.run-controls { display: flex; align-items: center; gap: 8px; flex: none; }
.run-controls :deep(.n-select) { flex: 1; min-width: 0; }
.capture-toggle { flex: none; }
.run-controls :deep(.capture-toggle .n-checkbox__label) { font-size: 12px; padding-left: 6px; }
.run-btn { flex: none; }
</style>
