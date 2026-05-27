<script setup lang="ts">
interface Device {
  id: string
  name?: string
  status?: string
}

defineProps<{
  device: Device | null
  deviceInfo: Record<string, string>
}>()
</script>

<template>
  <div class="device-detail" v-if="device">
    <div class="device-info-grid">
      <div class="info-item">
        <span class="info-label">Device ID:</span>
        <span class="info-value">{{ device.id }}</span>
      </div>
      <div class="info-item" v-if="device.name">
        <span class="info-label">Name:</span>
        <span class="info-value">{{ device.name }}</span>
      </div>
      <div class="info-item" v-if="device.status">
        <span class="info-label">Status:</span>
        <span class="info-value">{{ device.status }}</span>
      </div>
      <div class="info-item" v-if="deviceInfo.model">
        <span class="info-label">Model:</span>
        <span class="info-value">{{ deviceInfo.model }}</span>
      </div>
      <div class="info-item" v-if="deviceInfo.brand">
        <span class="info-label">Brand:</span>
        <span class="info-value">{{ deviceInfo.brand }}</span>
      </div>
      <div class="info-item" v-if="deviceInfo.manufacturer">
        <span class="info-label">Manufacturer:</span>
        <span class="info-value">{{ deviceInfo.manufacturer }}</span>
      </div>
      <div class="info-item" v-if="deviceInfo.androidVersion">
        <span class="info-label">Android:</span>
        <span class="info-value">{{ deviceInfo.androidVersion }}</span>
      </div>
      <div class="info-item" v-if="deviceInfo.apiLevel">
        <span class="info-label">API Level:</span>
        <span class="info-value">{{ deviceInfo.apiLevel }}</span>
      </div>
      <div class="info-item" v-if="deviceInfo.architecture">
        <span class="info-label">Architecture:</span>
        <span class="info-value">{{ deviceInfo.architecture }}</span>
      </div>
      <div class="info-item" v-if="deviceInfo.batteryLevel !== undefined && deviceInfo.batteryLevel !== ''">
        <span class="info-label">Battery:</span>
        <span class="info-value">{{ deviceInfo.batteryLevel }}%</span>
      </div>
      <div class="info-item" v-if="deviceInfo.screenResolution">
        <span class="info-label">Resolution:</span>
        <span class="info-value">{{ deviceInfo.screenResolution }}</span>
      </div>
      <div class="info-item" v-if="deviceInfo.density">
        <span class="info-label">Density:</span>
        <span class="info-value">{{ deviceInfo.density }}</span>
      </div>
      <div class="info-item" v-if="deviceInfo.totalMemory">
        <span class="info-label">RAM:</span>
        <span class="info-value">{{ deviceInfo.totalMemory }}</span>
      </div>
      <div class="info-item" v-if="deviceInfo.availableStorage">
        <span class="info-label">Storage Avail:</span>
        <span class="info-value">{{ deviceInfo.availableStorage }}</span>
      </div>
      <div class="info-item" v-if="deviceInfo.systemActivationDate">
        <span class="info-label">Activated:</span>
        <span class="info-value">{{ deviceInfo.systemActivationDate }}</span>
      </div>
    </div>
  </div>
  <div class="device-detail empty" v-else>
    Select a device to view details
  </div>
</template>

<style scoped>
.device-detail {
  padding: var(--space-md);
  height: 260px;
  overflow-y: auto;
  background-color: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
.device-detail.empty {
  color: var(--color-text-secondary);
  text-align: center;
  padding: var(--space-xl);
  display: flex;
  align-items: center;
  justify-content: center;
}
.device-info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-sm);
}
.info-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  background-color: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
.info-label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}
.info-value {
  color: var(--color-text);
  font-weight: 500;
}
</style>
