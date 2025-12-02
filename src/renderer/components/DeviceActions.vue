<template>
  <div class="section">
    <div class="section-header">
      <h2><span class="section-icon">⚙️</span>设备操作</h2>
      <div class="section-actions">
        <button 
          class="btn btn-sm btn-secondary" 
          :disabled="!selectedDevice"
          @click="rebootDevice('normal')"
          data-tooltip="重启设备"
        >
          <span>🔄</span>
        </button>
        <button 
          class="btn btn-sm btn-warning" 
          :disabled="!selectedDevice"
          @click="rebootDevice('recovery')"
          data-tooltip="重启到Recovery模式"
        >
          <span>🛠️</span>
        </button>
        <button 
          class="btn btn-sm btn-danger" 
          :disabled="!selectedDevice"
          @click="rebootDevice('bootloader')"
          data-tooltip="重启到Bootloader模式"
        >
          <span>⚡</span>
        </button>
      </div>
    </div>
    <div class="form-group">
      <label>Shell 命令</label>
      <div class="shell-input-group">
        <input 
          type="text" 
          class="form-control" 
          v-model="shellCommand"
          placeholder="输入 ADB shell 命令" 
          :disabled="!selectedDevice"
          @keyup.enter="executeShellCommand"
        >
        <button 
          class="btn btn-primary" 
          :disabled="!selectedDevice || !shellCommand.trim()"
          @click="executeShellCommand"
        >
          <span>▶️</span>执行
        </button>
      </div>
    </div>
    <div v-if="shellOutput" class="shell-output">
      <pre>{{ shellOutput }}</pre>
    </div>
  </div>
</template>

<script>
import { ref } from 'vue'
import { useDeviceStore } from '@stores/deviceStore.js'
import serviceManager from '../services/ServiceManager.js'
import { storeToRefs } from 'pinia'

export default {
  name: 'DeviceActions',
  setup() {
    const deviceStore = useDeviceStore()
    const { selectedDevice, shellOutput } = storeToRefs(deviceStore)
    const shellCommand = ref('')

    const rebootDevice = async (mode) => {
      const svc = await serviceManager.getService('device')
      await svc.rebootDevice(mode)
    }
    const executeShellCommand = async () => {
      const svc = await serviceManager.getService('device')
      await svc.executeShell(shellCommand.value)
      shellCommand.value = ''
    }

    return {
      selectedDevice,
      shellCommand,
      shellOutput,
      rebootDevice,
      executeShellCommand
    }
  }
}
</script>

<style scoped>
/* Component-specific styles */
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
</style>