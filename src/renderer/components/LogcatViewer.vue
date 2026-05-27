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
    <div class="logcat-output" ref="logcatContainer">
      <div v-for="(line, index) in logcatOutput" :key="index" class="log-line">{{ line }}</div>
    </div>
  </div>
</template>

<script>
import { computed, ref, watch, nextTick } from 'vue'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
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

    // Auto-scroll logic
    watch(() => logcatOutput.value.length, () => {
      nextTick(() => {
        const container = logcatContainer.value
        if (container) {
          // Only auto-scroll if user is already near the bottom (allow manual review of history)
          const threshold = 100 // pixels
          const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold
          
          if (isNearBottom || logcatOutput.value.length < 100) {
             container.scrollTop = container.scrollHeight
          }
        }
      })
    })

    return {
      selectedDevice,
      isLogcatRunning,
      logcatOutput,
      logcatContainer,
      toggling,
      toggleLogcat,
      clearLogcat,
      exportLogcat
    }
  }
}
</script>

<style scoped>




.log-line:hover {
  background-color: #e0e0e0;
}
</style>
