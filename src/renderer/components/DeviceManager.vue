<template>
  <div class="section responsive-section">
    <div class="section-header">
      <h2><span class="section-icon">📱</span>ADB 设备管理</h2>
      <div class="section-actions">
        <span class="toggle-desc">自动监听</span>
        <div class="toggle-switch-container" :data-tooltip="isMonitoring ? '关闭自动监听' : '开启自动监听'">
          <label class="toggle-switch">
            <input type="checkbox" :checked="isMonitoring" @change="toggleMonitoring">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <button class="btn btn-sm btn-secondary" @click="refreshDevices" data-tooltip="手动刷新设备列表">
          <span>🔄</span>
        </button>
      </div>
    </div>
    <div class="form-group">
      <label>连接状态</label>
      <div class="status-row">
        <span class="status-indicator"
          :class="connectionStatus.connected ? 'status-connected' : 'status-disconnected'"></span>
        <span>{{ connectionStatus.text }}</span>
      </div>
    </div>
    <div class="form-group">
      <label>选择设备</label>
      <select class="form-control" v-model="selectedDeviceId" :disabled="devices.length === 0"
        @change="handleDeviceSelection">
        <option value="">{{ devices.length === 0 ? '请先刷新设备列表' : '请选择设备' }}</option>
        <option v-for="device in devices" :key="device.id" :value="device.id">
          {{ device.name }} ({{ device.id }}) - {{ device.status }}
        </option>
      </select>
    </div>

    <!-- 设备信息 -->
    <div class="form-group">
      <label>设备信息</label>
      <div class="device-info compact">
        <div v-if="!selectedDevice">
          <p class="placeholder">请选择设备以查看详细信息</p>
        </div>
        <div v-else>
          <div class="device-info-grid">
            <div class="info-item">
              <span class="info-label">设备ID:</span>
              <span class="info-value">{{ selectedDevice.id }}</span>
            </div>
            <div class="info-item" v-if="selectedDevice.name">
              <span class="info-label">设备名称:</span>
              <span class="info-value">{{ selectedDevice.name }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">状态:</span>
              <span class="info-value">{{ selectedDevice.status }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.model">
              <span class="info-label">型号:</span>
              <span class="info-value">{{ deviceInfo.model }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.brand">
              <span class="info-label">品牌:</span>
              <span class="info-value">{{ deviceInfo.brand }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.manufacturer">
              <span class="info-label">制造商:</span>
              <span class="info-value">{{ deviceInfo.manufacturer }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.androidVersion">
              <span class="info-label">Android版本:</span>
              <span class="info-value">{{ deviceInfo.androidVersion }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.apiLevel">
              <span class="info-label">API级别:</span>
              <span class="info-value">{{ deviceInfo.apiLevel }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.architecture">
              <span class="info-label">架构:</span>
              <span class="info-value">{{ deviceInfo.architecture }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.systemActivationDate">
              <span class="info-label">激活日期:</span>
              <span class="info-value">{{ deviceInfo.systemActivationDate }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.pageSize">
              <span class="info-label">Page Size:</span>
              <span class="info-value">{{ deviceInfo.pageSize }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.batteryLevel !== undefined">
              <span class="info-label">电池电量:</span>
              <span class="info-value">{{ deviceInfo.batteryLevel }}%</span>
            </div>
            <div class="info-item" v-if="deviceInfo.screenResolution">
              <span class="info-label">屏幕分辨率:</span>
              <span class="info-value">{{ deviceInfo.screenResolution }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.density">
              <span class="info-label">屏幕密度:</span>
              <span class="info-value">{{ deviceInfo.density }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.totalMemory">
              <span class="info-label">总内存:</span>
              <span class="info-value">{{ deviceInfo.totalMemory }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.availableStorage">
              <span class="info-label">可用存储:</span>
              <span class="info-value">{{ deviceInfo.availableStorage }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.totalStorage">
              <span class="info-label">总存储:</span>
              <span class="info-value">{{ deviceInfo.totalStorage }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.buildId">
              <span class="info-label">构建ID:</span>
              <span class="info-value">{{ deviceInfo.buildId }}</span>
            </div>
            <div class="info-item" v-if="deviceInfo.buildNumber">
              <span class="info-label">构建号:</span>
              <span class="info-value">{{ deviceInfo.buildNumber }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { useDeviceStore } from '@stores/deviceStore.js'
import serviceManager from '@services/ServiceManager.js'
import { storeToRefs } from 'pinia'

export default {
  name: 'DeviceManager',
  setup() {
    const deviceStore = useDeviceStore()
    const {
      devices,
      selectedDeviceId,
      selectedDevice,
      deviceInfo,
      isMonitoring,
      connectionStatus
    } = storeToRefs(deviceStore)

    const refreshDevices = async () => {
      const svc = await serviceManager.getService('device')
      await svc.refreshDevices()
    }
    const toggleMonitoring = async () => {
      const svc = await serviceManager.getService('device')
      await svc.toggleMonitoring()
    }
    const handleDeviceSelection = async () => {
      deviceStore.selectDevice(selectedDeviceId.value)
      const svc = await serviceManager.getService('device')
      if (selectedDeviceId.value) await svc.getDeviceInfo(selectedDeviceId.value)
    }

    return {
      devices,
      selectedDeviceId,
      selectedDevice,
      deviceInfo,
      isMonitoring,
      connectionStatus,
      refreshDevices,
      toggleMonitoring,
      handleDeviceSelection
    }
  }
}
</script>

<style scoped>


.device-info {
  height: 260px;
  overflow-y: auto;
  padding: 12px;
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
}

.device-info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.info-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  background-color: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
}

.info-label {
  color: var(--text-muted);
}

.info-value {
  color: var(--text-primary);
  font-weight: 500;
}
</style>