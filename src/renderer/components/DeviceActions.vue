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
      <div class="input-group">
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
    <div v-if="shellOutput" class="code-output">
      <pre>{{ shellOutput }}</pre>
    </div>
  </div>
</template>

<script>
import { ref } from 'vue'
import { useDeviceStore } from '@stores/deviceStore.js'
import  serviceManager  from '@services/serviceManager.js'
import { useNotification } from '@composables/useNotification.js'
import { storeToRefs } from 'pinia'

export default {
  name: 'DeviceActions',
  setup() {
    const { showSuccess, showError, showLoading, completeLoading, failLoading } = useNotification()
    const deviceStore = useDeviceStore()
    const { selectedDevice, shellOutput } = storeToRefs(deviceStore)
    const shellCommand = ref('')

    const rebootDevice = async (mode) => {

      const loadingId = showLoading('正在重启设备', `正在将设备重启到 ${mode} 模式...`)
      
      try {
        const svc = await serviceManager.getService('device')
        await svc.rebootDevice(mode)
        
        completeLoading(loadingId, '重启指令已发送', `设备正在重启到 ${mode} 模式`)
      } catch (error) {
        failLoading(loadingId, '重启失败', error.message || '未知错误')
      }
    }
    const executeShellCommand = async () => {
      if (!shellCommand.value.trim()) return
      // 对于耗时较短的 shell 命令，也许不需要 loading，或者给一个短的延迟显示？
      // 这里为了统一体验，加上 loading，因为 adb 命令有时候会卡住
      const loadingId = showLoading('执行命令', `正在执行: ${shellCommand.value}`)
      
      try {
        const svc = await serviceManager.getService('device')
        await svc.executeShell(shellCommand.value)
        shellCommand.value = ''
        
        completeLoading(loadingId, '执行完成', '命令执行成功')
      } catch (error) {
        failLoading(loadingId, '执行失败', error.message || '未知错误')
      }
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

</style>