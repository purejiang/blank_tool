<template>
  <div class="device-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">Device Management</h1>
        <p class="page-subtitle">Manage connected Android devices via ADB</p>
      </div>
      <n-space>
        <n-tag :type="connectionStatus.connected ? 'success' : 'error'" round size="small">
          <template #icon><n-icon :component="connectionStatus.connected ? Link : Link2Off" /></template>
          {{ connectionStatus.text }}
        </n-tag>
        <n-button @click="refreshDevices" :loading="loading" secondary size="small">
          <template #icon><n-icon><RefreshCw /></n-icon></template>
          Refresh
        </n-button>
      </n-space>
    </div>

    <n-grid cols="1 800:2" :x-gap="16" :y-gap="16">
      <!-- Device List -->
      <n-grid-item>
        <n-card title="Devices" :bordered="false" class="device-card" size="small">
          <template #header-extra>
            <n-tag size="small" :bordered="false">{{ devices.length }} connected</n-tag>
          </template>
          <n-spin :show="loading">
            <div v-if="devices.length === 0" class="empty-state">
              <n-icon size="48" color="#475569"><Smartphone /></n-icon>
              <p>No devices connected</p>
              <n-button @click="refreshDevices" size="small" quaternary>Try refreshing</n-button>
            </div>
            <n-list v-else hoverable clickable>
              <n-list-item
                v-for="device in devices"
                :key="device.id"
                @click="handleDeviceSelection(device.id)"
                :class="{ selected: selectedDeviceId === device.id }"
              >
                <template #prefix>
                  <n-icon size="20" :color="device.state === 'device' ? '#22C55E' : '#F59E0B'">
                    <Smartphone />
                  </n-icon>
                </template>
                <n-thing :title="device.model || device.id" title-extra="">
                  <template #description>
                    <n-space size="small">
                      <n-tag :type="device.state === 'device' ? 'success' : 'warning'" size="tiny" :bordered="false">
                        {{ device.state }}
                      </n-tag>
                      <span class="serial-text">{{ device.id }}</span>
                    </n-space>
                  </template>
                </n-thing>
              </n-list-item>
            </n-list>
          </n-spin>
          <template v-if="selectedDeviceId" #action>
            <n-space>
              <n-button
                :type="isMonitoring ? 'error' : 'success'"
                size="small"
                @click="toggleMonitoring"
                secondary
              >
                <template #icon>
                  <n-icon><Activity /></n-icon>
                </template>
                {{ isMonitoring ? 'Stop Logcat' : 'Start Logcat' }}
              </n-button>
            </n-space>
          </template>
        </n-card>
      </n-grid-item>

      <!-- Device Info -->
      <n-grid-item>
        <n-card title="Device Info" :bordered="false" class="device-card" size="small">
          <template v-if="!selectedDevice" #default>
            <div class="empty-state">
              <n-icon size="48" color="#475569"><Info /></n-icon>
              <p>Select a device to view details</p>
            </div>
          </template>
          <template v-else>
            <n-descriptions label-placement="left" :column="1" size="small">
              <n-descriptions-item label="Model">{{ selectedDevice.model || '-' }}</n-descriptions-item>
              <n-descriptions-item label="Serial">{{ selectedDevice.id }}</n-descriptions-item>
              <n-descriptions-item label="Status">
                <n-tag :type="selectedDevice.state === 'device' ? 'success' : 'warning'" size="small" :bordered="false">
                  {{ selectedDevice.state }}
                </n-tag>
              </n-descriptions-item>
              <n-descriptions-item label="Product">{{ selectedDevice.product || '-' }}</n-descriptions-item>
              <template v-if="deviceInfo">
                <n-descriptions-item label="Android Version">{{ deviceInfo.androidVersion || '-' }}</n-descriptions-item>
                <n-descriptions-item label="SDK Level">{{ deviceInfo.sdkLevel || '-' }}</n-descriptions-item>
                <n-descriptions-item label="CPU">{{ deviceInfo.cpu || '-' }}</n-descriptions-item>
              </template>
            </n-descriptions>
          </template>
        </n-card>
      </n-grid-item>
    </n-grid>

    <!-- Logcat Output -->
    <n-card v-if="isMonitoring" title="Logcat" :bordered="false" class="logcat-card" size="small" style="margin-top: 16px">
      <template #header-extra>
        <n-tag type="success" size="small" :bordered="false">
          <template #icon><n-icon><Circle /></n-icon></template>
          Live
        </n-tag>
      </template>
      <div class="logcat-output" ref="logcatContainer">
        <div v-if="logcatOutput.length === 0" class="empty-state">
          <p>Waiting for log output...</p>
        </div>
        <div v-for="(line, i) in logcatOutput" :key="i" class="logcat-line" :class="getLogLevel(line)">
          {{ line }}
        </div>
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onUnmounted } from 'vue'
import { NIcon } from 'naive-ui'
import {
  Smartphone, RefreshCw, Activity, Info, Link, Link2Off, Circle
} from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { storeToRefs } from 'pinia'

const deviceStore = useDeviceStore()
const {
  devices,
  selectedDeviceId,
  selectedDevice,
  deviceInfo,
  isMonitoring,
  connectionStatus,
  logcatOutput
} = storeToRefs(deviceStore)

const loading = ref(false)
const logcatContainer = ref<HTMLElement | null>(null)

// Auto-scroll logcat
watch(() => logcatOutput.value.length, () => {
  nextTick(() => {
    if (logcatContainer.value) {
      logcatContainer.value.scrollTop = logcatContainer.value.scrollHeight
    }
  })
})

onUnmounted(() => {
  if (isMonitoring.value) {
    serviceManager.getService('device').then(svc => svc.toggleMonitoring())
  }
})

function getLogLevel(line: string): string {
  if (line.includes(' E/') || line.includes('ERROR')) return 'level-error'
  if (line.includes(' W/') || line.includes('WARN')) return 'level-warn'
  if (line.includes(' I/') || line.includes('INFO')) return 'level-info'
  if (line.includes(' D/') || line.includes('DEBUG')) return 'level-debug'
  return ''
}

const refreshDevices = async () => {
  loading.value = true
  try {
    const svc = await serviceManager.getService('device')
    await svc.refreshDevices()
  } finally {
    loading.value = false
  }
}

const toggleMonitoring = async () => {
  const svc = await serviceManager.getService('device')
  await svc.toggleMonitoring()
}

const handleDeviceSelection = async (id: string) => {
  deviceStore.selectDevice(id)
  if (id) {
    const svc = await serviceManager.getService('device')
    await svc.getDeviceInfo(id)
  }
}
</script>

<style scoped>
.device-page {
  max-width: 1200px;
  margin: 0 auto;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.page-title {
  font-family: Inter, sans-serif;
  font-size: 22px;
  font-weight: 700;
  color: #F8FAFC;
  margin: 0;
  letter-spacing: -0.02em;
}
.page-subtitle {
  font-size: 13px;
  color: #94A3B8;
  margin: 4px 0 0;
}
.device-card {
  background: #1E293B;
  border-radius: 10px;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 16px;
  color: #64748B;
  font-size: 14px;
}
.empty-state p { margin: 0; }
.serial-text {
  font-family: 'Fira Code', monospace;
  font-size: 11px;
  color: #64748B;
}
:deep(.n-list-item) {
  border-radius: 8px;
  margin: 2px 0;
}
:deep(.n-list-item.selected) {
  background: rgba(34,197,94,0.08) !important;
}
.logcat-card {
  background: #1E293B;
  border-radius: 10px;
}
.logcat-output {
  background: #0C1322;
  border-radius: 8px;
  padding: 12px;
  max-height: 300px;
  overflow-y: auto;
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.7;
}
.logcat-line {
  white-space: pre-wrap;
  word-break: break-all;
  color: #CBD5E1;
}
.level-error { color: #EF4444; }
.level-warn { color: #F59E0B; }
.level-info { color: #3B82F6; }
.level-debug { color: #64748B; }
</style>
