<template>
  <n-select
    :value="autoDeviceId"
    :options="deviceOptions"
    size="small"
    :placeholder="t('automation.selectDevice')"
    @update:value="emit('update:autoDeviceId', $event)"
  />
  <template v-if="mode === 'run'">
    <n-checkbox
      :checked="captureTraffic"
      size="small"
      class="capture-toggle"
      @update:checked="emit('update:captureTraffic', $event)"
    >
      {{ t('automation.captureTraffic') }}
    </n-checkbox>
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
  </template>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NCheckbox, NSelect, NIcon, NTooltip } from 'naive-ui'
import { Play, Square } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'

defineProps<{
  mode: 'record' | 'run'
  autoDeviceId: string
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
.capture-toggle { flex-shrink: 0; }
</style>
