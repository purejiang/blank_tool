<template>
  <div class="status-bar">
    <!-- 左侧：设备信息 -->
    <div class="status-left">
      <div class="device-status" v-if="connectedDevice">
        <span class="device-icon">📱</span>
        <span class="device-info">{{ connectedDevice.name || connectedDevice.id }}</span>
        <span class="device-status-indicator" :class="deviceStatusClass"></span>
      </div>
      <div class="device-status no-device" v-else>
        <span class="device-icon">📱</span>
        <span class="device-info">未连接设备</span>
        <span class="device-status-indicator offline"></span>
      </div>
    </div>

    <!-- 中间：可扩展区域 -->
    <div class="status-center">
      <slot name="center"></slot>
    </div>

    <!-- 右侧：版本信息 -->
    <div class="status-right">
      <span class="version-info">v{{ appVersion }}</span>
    </div>
  </div>
</template>

<script>
import { computed, onMounted } from 'vue'
import { useDeviceStore } from '../../stores'

export default {
  name: 'StatusBar',
  setup() {
    // 注入服务

    const deviceStore = useDeviceStore()

    // 使用全局设备状态
    const connectedDevice = computed(() => {
      if (!deviceStore.currentDevice) {
        return {}
      }
      return deviceStore.currentDevice.value
  })
    const appVersion = computed(() => '1.0.0') // 可以后续从设置中获取

    // 计算设备状态
    const deviceStatus = computed(() => {
      if (!connectedDevice.value) {
        return 'offline'
      }
      
      // 根据设备状态判断
      if (connectedDevice.value.status === 'device') {
        return 'online'
      } else if (connectedDevice.value.status === 'unauthorized') {
        return 'connecting'
      } else {
        return 'offline'
      }
    })

    // 计算属性
    const deviceStatusClass = computed(() => {
      return {
        'online': deviceStatus.value === 'online',
        'offline': deviceStatus.value === 'offline',
        'connecting': deviceStatus.value === 'connecting'
      }
    })

    // 获取应用版本信息
    const getAppVersion = async () => {
      try {
        const buildInfo = await settingsService.getBuildInfo()
        if (buildInfo && buildInfo.build_info) {
          appVersion.value = buildInfo.build_info.app_version || '1.0.0'
        }
      } catch (error) {
        console.error('获取版本信息失败:', error)
      }
    }

    // 获取当前设备信息
    const getConnectedDevice = async () => {
      try {
        const device = await settingsService.getConnectedDevice()
        if (device) {
          connectedDevice.value = device
        }
      } catch (error) {
        console.error('获取设备信息失败:', error)
      }
    }

    // 生命周期
    onMounted(async () => {
      await getAppVersion()
    })

    return {
      connectedDevice,
      appVersion,
      deviceStatus,
      deviceStatusClass
    }
  }
}
</script>

<style scoped>
.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 28px;
  padding: 0 16px;
  background: var(--bg-secondary, #f8f9fa);
  border-top: 1px solid var(--border-color, #e9ecef);
  font-size: 12px;
  color: var(--text-secondary, #6c757d);
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 1000;
}

.status-left {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
}

.status-center {
  display: flex;
  align-items: center;
  flex: 1;
  justify-content: center;
}

.status-right {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
}

.device-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.device-icon {
  font-size: 14px;
}

.device-info {
  font-weight: 500;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #dc3545;
  transition: background-color 0.3s ease;
}

.device-status-indicator.online {
  background: #28a745;
}

.device-status-indicator.connecting {
  background: #ffc107;
  animation: pulse 1.5s infinite;
}

.device-status-indicator.offline {
  background: #dc3545;
}

.no-device .device-info {
  color: var(--text-muted, #adb5bd);
}

.version-info {
  font-family: 'Consolas', 'Monaco', monospace;
  font-weight: 500;
  color: var(--text-secondary, #6c757d);
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

/* 深色主题适配 */
@media (prefers-color-scheme: dark) {
  .status-bar {
    background: var(--bg-secondary-dark, #2d3748);
    border-top-color: var(--border-color-dark, #4a5568);
    color: var(--text-secondary-dark, #a0aec0);
  }

  .version-info {
    color: var(--text-secondary-dark, #a0aec0);
  }

  .no-device .device-info {
    color: var(--text-muted-dark, #718096);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .status-bar {
    padding: 0 12px;
  }

  .device-info {
    max-width: 120px;
  }
}
</style>