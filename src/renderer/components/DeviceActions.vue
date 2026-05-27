<template>
  <n-card :bordered="false" class="device-actions-card" size="small">
    <template #header>
      <span class="card-title">Device Actions</span>
    </template>

    <!-- Reboot Actions -->
    <div class="actions-row">
      <n-tag :bordered="false" type="info" size="small" class="section-label">Reboot</n-tag>
      <n-space :size="8">
        <n-button
          size="small"
          secondary
          :disabled="!selectedDevice"
          @click="rebootDevice('normal')"
        >
          <template #icon><n-icon><RotateCw /></n-icon></template>
          System
        </n-button>
        <n-button
          size="small"
          secondary
          type="warning"
          :disabled="!selectedDevice"
          @click="rebootDevice('recovery')"
        >
          <template #icon><n-icon><Wrench /></n-icon></template>
          Recovery
        </n-button>
        <n-button
          size="small"
          secondary
          type="error"
          :disabled="!selectedDevice"
          @click="rebootDevice('bootloader')"
        >
          <template #icon><n-icon><Zap /></n-icon></template>
          Bootloader
        </n-button>
      </n-space>
    </div>

    <n-divider style="margin: 14px 0" />

    <!-- Shell Command -->
    <div class="actions-row">
      <n-tag :bordered="false" type="info" size="small" class="section-label">Shell</n-tag>
      <n-space :size="8" style="flex: 1">
        <n-input
          v-model:value="shellCommand"
          placeholder="Enter ADB shell command..."
          :disabled="!selectedDevice"
          size="small"
          clearable
          @keyup.enter="executeShellCommand"
        />
        <n-button
          size="small"
          type="success"
          secondary
          :disabled="!selectedDevice || !shellCommand.trim()"
          @click="executeShellCommand"
        >
          <template #icon><n-icon><Play /></n-icon></template>
          Run
        </n-button>
      </n-space>
    </div>

    <!-- Shell Output -->
    <div v-if="shellOutput" class="shell-output">
      <div class="shell-output-header">
        <n-icon size="14"><Terminal /></n-icon>
        <span>Output</span>
      </div>
      <pre class="shell-output-text">{{ shellOutput }}</pre>
    </div>

    <!-- Empty State -->
    <div v-if="!selectedDevice" class="empty-state">
      <n-icon size="28" color="#475569"><Settings2 /></n-icon>
      <p class="empty-title">No Device Selected</p>
      <p class="empty-desc">Select a device to perform actions</p>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NIcon } from 'naive-ui'
import { RotateCw, Wrench, Zap, Terminal, Play, Settings2 } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { storeToRefs } from 'pinia'

const { showSuccess, showError, showLoading, completeLoading, failLoading } = useNotification()
const deviceStore = useDeviceStore()
const { selectedDevice, shellOutput } = storeToRefs(deviceStore)
const shellCommand = ref('')

const rebootDevice = async (mode: string) => {
  const loadingId = showLoading('Rebooting device', `Rebooting to ${mode} mode...`)

  try {
    const svc = await serviceManager.getService('device')
    await svc.rebootDevice(mode)

    completeLoading(loadingId, 'Reboot command sent', `Device is rebooting to ${mode} mode`)
  } catch (error: any) {
    failLoading(loadingId, 'Reboot failed', error.message || 'Unknown error')
  }
}

const executeShellCommand = async () => {
  if (!shellCommand.value.trim()) return

  const loadingId = showLoading('Executing command', `Running: ${shellCommand.value}`)

  try {
    const svc = await serviceManager.getService('device')
    await svc.executeShell(shellCommand.value)
    shellCommand.value = ''

    completeLoading(loadingId, 'Execution complete', 'Command executed successfully')
  } catch (error: any) {
    failLoading(loadingId, 'Execution failed', error.message || 'Unknown error')
  }
}
</script>

<style scoped>
.device-actions-card {
  background: #1E293B;
  border-radius: 10px;
}
.card-title {
  font-family: Inter, sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: #F8FAFC;
}
.actions-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.section-label {
  flex-shrink: 0;
  min-width: 56px;
  text-align: center;
}
.shell-output {
  margin-top: 12px;
  background: #0C1322;
  border-radius: 8px;
  overflow: hidden;
}
.shell-output-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 11px;
  color: #94A3B8;
  background: rgba(34, 197, 94, 0.06);
  border-bottom: 1px solid #1E293B;
}
.shell-output-text {
  margin: 0;
  padding: 10px 12px;
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  color: #CBD5E1;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 24px 16px;
  color: #64748B;
  font-size: 14px;
}
.empty-state p { margin: 0; }
.empty-title {
  font-size: 13px;
  font-weight: 600;
  color: #94A3B8;
}
.empty-desc {
  font-size: 12px;
  color: #64748B;
}
</style>
