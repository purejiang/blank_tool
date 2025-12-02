<template>
  <div class="section">
    <div class="section-header">
      <h2><span class="section-icon">📜</span>Logcat</h2>
      <div class="section-actions">
        <button 
          class="btn btn-sm" 
          :class="isLogcatRunning ? 'btn-danger' : 'btn-primary'"
          :disabled="!selectedDevice || toggling"
          @click="toggleLogcat"
          :data-tooltip="isLogcatRunning ? '停止 Logcat' : '启动 Logcat'"
        >
          <span>{{ isLogcatRunning ? '⏹️' : '▶️' }}</span>
        </button>
        <button 
          class="btn btn-sm btn-secondary" 
          :disabled="!selectedDevice || logcatOutput.length === 0"
          @click="clearLogcat"
          data-tooltip="清空日志"
        >
          <span>🗑️</span>
        </button>
        <button 
          class="btn btn-sm btn-secondary" 
          :disabled="!selectedDevice || logcatOutput.length === 0"
          @click="exportLogcat"
          data-tooltip="导出日志"
        >
          <span>📄</span>
        </button>
      </div>
    </div>
    <div class="logcat-output">
      <pre ref="logcatContainer">{{ formattedLogcatOutput }}</pre>
    </div>
  </div>
</template>

<script>
import { computed, ref, watch } from 'vue'
import { useDeviceStore } from '@stores/deviceStore.js'
import serviceManager from '../services/ServiceManager.js'
import { storeToRefs } from 'pinia'

export default {
  name: 'LogcatViewer',
  setup() {
    const deviceStore = useDeviceStore()
    const { 
      selectedDevice, 
      isLogcatRunning, 
      logcatOutput 
    } = storeToRefs(deviceStore)

    const logcatContainer = ref(null)

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

    const formattedLogcatOutput = computed(() => logcatOutput.value.join('\n'))

    watch(logcatOutput, () => {
      const container = logcatContainer.value
      if (container) {
        container.scrollTop = container.scrollHeight
      }
    })

    return {
      selectedDevice,
      isLogcatRunning,
      logcatOutput,
      logcatContainer,
      toggling,
      toggleLogcat,
      clearLogcat,
      exportLogcat,
      formattedLogcatOutput
    }
  }
}
</script>

<style scoped>
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  position: relative;
}

.section-actions {
  display: flex;
  gap: 8px;
  position: absolute;
  top: 0;
  right: 0;
}

.section-actions .btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 6px 12px;
}

.logcat-output pre {
  height: 320px;
  overflow: auto;
  font-size: 11px;
}
</style>
