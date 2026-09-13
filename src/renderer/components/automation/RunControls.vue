<template>
  <div class="run-controls">
    <div class="run-controls-row">
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
    <!-- non-blocking preflight hints (missing mitmproxy / ADBKeyBoard) -->
    <div v-if="hints.length" class="run-hints">
      <div v-for="(h, i) in hints" :key="i" class="run-hint">{{ h }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NCheckbox, NSelect, NIcon, NTooltip } from 'naive-ui'
import { Play, Square } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'

const props = defineProps<{
  autoDeviceId: string
  /** Run-time option: capture network traffic for this run. */
  captureTraffic: boolean
  running: boolean
  canRun: boolean
  /** Non-blocking preflight warnings rendered under the controls row. */
  hints?: string[]
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
const hints = computed(() => props.hints ?? [])
</script>

<style scoped>
/* single root so the parent column can lay it out; ONE row — the device
   select absorbs the slack, the run button is the primary action, and
   traffic capture is a short label (full explanation lives in its tooltip) */
.run-controls { display: flex; flex-direction: column; gap: 6px; flex: none; }
.run-controls-row { display: flex; align-items: center; gap: 8px; }
.run-controls-row :deep(.n-select) { flex: 1; min-width: 0; }
.capture-toggle { flex: none; }
.run-controls-row :deep(.capture-toggle .n-checkbox__label) { font-size: 12px; padding-left: 6px; }
.run-btn { flex: none; }
.run-hints { display: flex; flex-direction: column; gap: 2px; }
.run-hint { font-size: 12px; color: var(--app-text-muted); }
</style>
