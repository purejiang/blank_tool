<template>
  <n-select
    :value="autoDeviceId"
    :options="deviceOptions"
    size="small"
    :placeholder="t('automation.selectDevice')"
    @update:value="emit('update:autoDeviceId', $event)"
  />
  <div class="run-actions">
    <n-checkbox
      :checked="captureTraffic"
      size="small"
      class="capture-toggle"
      @update:checked="emit('update:captureTraffic', $event)"
    >
      {{ t('automation.captureTraffic') }}
    </n-checkbox>
    <div class="timeout-row">
      <span class="timeout-label">{{ t('automation.elementTimeout') }}</span>
      <n-input-number
        :value="elementTimeoutMs"
        size="small"
        :min="500"
        :max="120000"
        :step="1000"
        class="timeout-ctl"
        @update:value="(v: number | null) => emit('update:elementTimeoutMs', v ?? 10000)"
      />
    </div>
    <n-tooltip v-if="!running" :disabled="canRun" placement="top">
      <template #trigger>
        <n-button type="primary" size="small" block :disabled="!canRun" @click="emit('run')">
          <template #icon><n-icon><Play /></n-icon></template>
          {{ t('automation.run') }}
        </n-button>
      </template>
      {{ !autoDeviceId ? t('automation.noDevice') : t('automation.noScriptSelected') }}
    </n-tooltip>
    <n-button v-else type="warning" size="small" block @click="emit('stop')">
      <template #icon><n-icon><Square /></n-icon></template>
      {{ t('automation.stop') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NCheckbox, NSelect, NIcon, NTooltip, NInputNumber } from 'naive-ui'
import { Play, Square } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'

defineProps<{
  autoDeviceId: string
  captureTraffic: boolean
  /** Default element-poll timeout (ms) — applied to new element targets. */
  elementTimeoutMs: number
  running: boolean
  canRun: boolean
}>()

const emit = defineEmits<{
  (e: 'update:autoDeviceId', v: string): void
  (e: 'update:captureTraffic', v: boolean): void
  (e: 'update:elementTimeoutMs', v: number): void
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
.capture-toggle { flex-shrink: 0; }
.run-actions { display: flex; flex-direction: column; gap: 8px; }
.timeout-row { display: flex; align-items: center; gap: 6px; }
.timeout-label { font-size: 12px; color: var(--app-text-muted); flex: none; }
.timeout-ctl { flex: 1; min-width: 0; }
</style>
