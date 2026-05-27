<template>
  <n-card :bordered="false" class="logcat-viewer-card" size="small">
    <template #header>
      <div class="card-header">
        <span class="card-title">Logcat</span>
        <n-space :size="8" align="center">
          <n-tag v-if="isLogcatRunning" type="success" size="small" :bordered="false">
            <template #icon><n-icon><Circle /></n-icon></template>
            Live
          </n-tag>
          <n-button
            size="tiny"
            secondary
            :type="isLogcatRunning ? 'error' : 'success'"
            :disabled="!selectedDevice || toggling"
            :loading="toggling"
            @click="toggleLogcat"
          >
            <template #icon>
              <n-icon><Square v-if="isLogcatRunning" /><Play v-else /></n-icon>
            </template>
            {{ isLogcatRunning ? 'Stop' : 'Start' }}
          </n-button>
          <n-button
            size="tiny"
            secondary
            :disabled="!selectedDevice || logcatOutput.length === 0"
            @click="clearLogcat"
          >
            <template #icon><n-icon><Trash2 /></n-icon></template>
          </n-button>
          <n-button
            size="tiny"
            secondary
            :disabled="!selectedDevice || logcatOutput.length === 0"
            @click="exportLogcat"
          >
            <template #icon><n-icon><FileDown /></n-icon></template>
          </n-button>
        </n-space>
      </div>
    </template>

    <!-- Empty / Stopped State -->
    <div v-if="!selectedDevice" class="empty-state">
      <n-icon size="28" color="#475569"><Terminal /></n-icon>
      <p class="empty-title">No Device Selected</p>
      <p class="empty-desc">Select a device to use logcat</p>
    </div>
    <div v-else-if="!isLogcatRunning && logcatOutput.length === 0" class="empty-state">
      <n-icon size="28" color="#475569"><Terminal /></n-icon>
      <p class="empty-title">Logcat Not Running</p>
      <p class="empty-desc">Click "Start" to begin monitoring</p>
    </div>
    <div v-else-if="!isLogcatRunning && logcatOutput.length > 0" class="empty-state">
      <n-icon size="28" color="#475569"><PauseCircle /></n-icon>
      <p class="empty-title">Logcat Stopped</p>
      <p class="empty-desc">{{ logcatOutput.length }} lines captured</p>
    </div>

    <!-- Logcat Output -->
    <div v-else class="logcat-output" ref="logcatContainer">
      <div v-for="(line, index) in logcatOutput" :key="index" class="logcat-line" :class="getLogLevel(line)">
        <span class="log-line-num">{{ index + 1 }}</span>
        <span>{{ line }}</span>
      </div>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { NIcon } from 'naive-ui'
import {
  Play, Square, Trash2, FileDown, Terminal, Circle, PauseCircle
} from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { storeToRefs } from 'pinia'

const deviceStore = useDeviceStore()
const {
  selectedDevice,
  isLogcatRunning,
  logcatOutput
} = storeToRefs(deviceStore)

const logcatContainer = ref<HTMLElement | null>(null)
const toggling = ref(false)

const toggleLogcat = async () => {
  if (toggling.value) return
  toggling.value = true
  try {
    const svc = await serviceManager.getService('device')
    await svc.toggleLogcat()
  } finally {
    toggling.value = false
  }
}

const clearLogcat = async () => {
  const svc = await serviceManager.getService('device')
  await svc.clearLogcat()
}

const exportLogcat = async () => {
  const svc = await serviceManager.getService('device')
  await svc.exportLogcat()
}

function getLogLevel(line: string): string {
  if (line.includes(' E/') || line.includes('ERROR')) return 'level-error'
  if (line.includes(' W/') || line.includes('WARN')) return 'level-warn'
  if (line.includes(' I/') || line.includes('INFO')) return 'level-info'
  if (line.includes(' D/') || line.includes('DEBUG')) return 'level-debug'
  return ''
}

// Auto-scroll logic — only when user is near the bottom
watch(() => logcatOutput.value.length, () => {
  nextTick(() => {
    const container = logcatContainer.value
    if (container) {
      const threshold = 100
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold

      if (isNearBottom || logcatOutput.value.length < 100) {
        container.scrollTop = container.scrollHeight
      }
    }
  })
})
</script>

<style scoped>
.logcat-viewer-card {
  background: #1E293B;
  border-radius: 10px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.card-title {
  font-family: Inter, sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: #F8FAFC;
}
.logcat-output {
  background: #0C1322;
  border-radius: 8px;
  padding: 12px;
  max-height: 320px;
  overflow-y: auto;
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.7;
}
.logcat-line {
  display: flex;
  gap: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  color: #CBD5E1;
}
.log-line-num {
  color: #475569;
  min-width: 28px;
  text-align: right;
  user-select: none;
  flex-shrink: 0;
}
.level-error { color: #EF4444; }
.level-warn { color: #F59E0B; }
.level-info { color: #3B82F6; }
.level-debug { color: #64748B; }
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 32px 16px;
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
