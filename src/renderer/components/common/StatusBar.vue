<template>
  <div class="status-bar">
    <div class="status-left">
      <div class="device-badge" v-if="connectedDevice">
        <n-icon size="14"><Smartphone /></n-icon>
        <span>{{ connectedDevice.name || connectedDevice.id }}</span>
        <span class="status-dot" :class="deviceStatusClass"></span>
      </div>
      <div class="device-badge off" v-else>
        <n-icon size="14" color="#64748B"><Smartphone /></n-icon>
        <span class="dim">No device</span>
        <span class="status-dot offline"></span>
      </div>
    </div>
    <div class="status-right">
      <span class="version-text">v{{ frontendVersion }} | backend {{ backendVersion || 'N/A' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NIcon } from 'naive-ui'
import { Smartphone } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import { storeToRefs } from 'pinia'
import serviceManager from '@services/ServiceManager'

const deviceStore = useDeviceStore()
const { selectedDevice } = storeToRefs(deviceStore)
const connectedDevice = computed(() => selectedDevice.value || null)
const frontendVersion = ref('1.0.0')
const backendVersion = ref('')

const deviceStatus = computed(() => {
  if (!connectedDevice.value) return 'offline'
  const s = connectedDevice.value.state || connectedDevice.value.status
  if (s === 'device') return 'online'
  if (s === 'unauthorized') return 'connecting'
  return 'offline'
})

const deviceStatusClass = computed(() => deviceStatus.value)

const getVersions = async () => {
  try {
    const systemSvc = await serviceManager.getService('system')
    const info = await systemSvc.getAppInfo()
    frontendVersion.value = info?.version || '1.0.0'
    const be = await systemSvc.getBackendInfo()
    backendVersion.value = be?.version || ''
  } catch { /* silent */ }
}

onMounted(() => getVersions())
</script>

<style scoped>
.status-bar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 18px;
  background: #0C1322;
  border-top: 1px solid #1E293B;
  font-size: 11px;
  font-family: Inter, sans-serif;
}
.status-left, .status-right {
  display: flex;
  align-items: center;
}
.device-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #CBD5E1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.device-badge.off { color: #64748B; }
.dim { color: #64748B; }
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #EF4444;
  flex-shrink: 0;
}
.status-dot.online { background: #22C55E; }
.status-dot.connecting { background: #F59E0B; animation: pulse 1.5s infinite; }
.status-dot.offline { background: #EF4444; }
.version-text {
  font-family: 'Fira Code', monospace;
  color: #64748B;
  font-size: 10px;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
