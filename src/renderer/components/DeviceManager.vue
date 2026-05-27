<template>
  <div class="section responsive-section">
    <div class="section-header">
      <h2><span class="section-icon">&#x1F4F1;</span>ADB Device Management</h2>
    </div>

    <DeviceActionBar
      :has-selection="!!selectedDevice"
      :is-monitoring="isMonitoring"
      :connection-text="connectionStatus.text"
      :connection-connected="connectionStatus.connected"
      @refresh="refreshDevices"
      @toggle-monitoring="toggleMonitoring"
    />

    <div class="form-group">
      <label>Select Device</label>
      <DeviceList
        :devices="devices"
        :selected-id="selectedDeviceId"
        @select="handleDeviceSelection"
      />
    </div>

    <div class="form-group">
      <label>Device Info</label>
      <DeviceDetail
        :device="selectedDevice"
        :device-info="deviceInfo"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { storeToRefs } from 'pinia'
import DeviceList from './device/DeviceList.vue'
import DeviceDetail from './device/DeviceDetail.vue'
import DeviceActionBar from './device/DeviceActionBar.vue'

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
const handleDeviceSelection = async (id: string) => {
  deviceStore.selectDevice(id)
  const svc = await serviceManager.getService('device')
  if (id) await svc.getDeviceInfo(id)
}
</script>

<style scoped>
.form-group {
  margin-bottom: var(--space-md);
}
.form-group label {
  display: block;
  font-weight: 600;
  margin-bottom: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}
</style>
