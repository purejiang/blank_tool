<template>
  <div class="device-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('device.title') }}</h1>
        <p class="page-subtitle">{{ t('device.subtitle') }}</p>
      </div>
      <n-space align="center">
        <n-tag :type="connectionStatus.connected ? 'success' : 'error'" round size="medium" :bordered="false">
          <template #icon><n-icon :component="connectionStatus.connected ? Link : Link2Off" /></template>
          {{ connectionStatus.text }}
        </n-tag>
        <n-button @click="refreshDevices" :loading="loading" secondary size="small">
          <template #icon><n-icon><RefreshCw /></n-icon></template>
          {{ t('device.refresh') }}
        </n-button>
      </n-space>
    </div>

    <n-grid cols="1 800:2" :x-gap="16" :y-gap="16">
      <!-- Device List -->
      <n-grid-item>
        <n-card :bordered="false" class="device-card" size="small">
          <template #header>
            <div class="card-header">
              <span class="card-title">{{ t('device.devices') }}</span>
              <n-tag size="small" :bordered="false" type="info">{{ t('device.connected', { count: devices.length }) }}</n-tag>
            </div>
          </template>
          <n-spin :show="loading">
            <div v-if="devices.length === 0" class="empty-state">
              <n-icon size="40" color="#475569"><Smartphone /></n-icon>
              <p class="empty-title">{{ t('device.noDevices') }}</p>
              <p class="empty-desc">{{ t('device.noDevicesDesc') }}</p>
              <n-button @click="refreshDevices" size="small" quaternary>{{ t('device.refresh') }}</n-button>
            </div>
            <n-list v-else hoverable clickable class="device-list">
              <n-list-item
                v-for="device in devices"
                :key="device.id"
                @click="handleDeviceSelection(device.id)"
                :class="{ selected: selectedDeviceId === device.id }"
              >
                <template #prefix>
                  <n-icon size="20" :color="device.status === 'device' ? '#22C55E' : '#F59E0B'">
                    <Smartphone />
                  </n-icon>
                </template>
                <div class="device-item-content">
                  <span class="device-model">{{ device.name || t('device.unknownDevice') }}</span>
                  <span class="device-serial">{{ device.id }}</span>
                </div>
                <template #suffix>
                  <span class="device-state-dot" :class="device.status === 'device' ? 'online' : 'warning'"></span>
                </template>
              </n-list-item>
            </n-list>
          </n-spin>
          <template v-if="selectedDeviceId" #action>
            <n-space>
              <n-button
                :type="isLogcatRunning ? 'error' : 'success'"
                size="small"
                @click="toggleLogcat"
                secondary
              >
                <template #icon>
                  <n-icon><Activity /></n-icon>
                </template>
                {{ isLogcatRunning ? t('device.stopLogcat') : t('device.startLogcat') }}
              </n-button>
            </n-space>
          </template>
        </n-card>
      </n-grid-item>

      <!-- Device Info -->
      <n-grid-item>
        <n-card :bordered="false" class="device-card" size="small">
          <template #header>
            <span class="card-title">{{ t('device.deviceInfo') }}</span>
          </template>
          <div v-if="!selectedDevice" class="empty-state">
            <n-icon size="40" color="#475569"><Info /></n-icon>
            <p class="empty-title">{{ t('device.noDeviceSelected') }}</p>
            <p class="empty-desc">{{ t('device.noDeviceSelectedDesc') }}</p>
          </div>
          <template v-else-if="selectedDevice">
            <n-descriptions label-placement="left" :column="1" size="small" class="device-descriptions">
              <n-descriptions-item :label="t('device.model')">
                <span class="info-value highlight">{{ selectedDevice.name || '-' }}</span>
              </n-descriptions-item>
              <n-descriptions-item :label="t('device.serial')">
                <span class="info-value mono">{{ selectedDevice.id }}</span>
              </n-descriptions-item>
              <n-descriptions-item :label="t('device.status')">
                <n-tag :type="selectedDevice.status === 'device' ? 'success' : 'warning'" size="small" :bordered="false">
                  {{ selectedDevice.status }}
                </n-tag>
              </n-descriptions-item>
              <n-descriptions-item :label="t('device.product')">{{ deviceInfo.product || '-' }}</n-descriptions-item>
              <template v-if="deviceInfo">
                <n-descriptions-item :label="t('device.android')">{{ deviceInfo.androidVersion || '-' }}</n-descriptions-item>
                <n-descriptions-item :label="t('device.sdk')">{{ deviceInfo.apiLevel || '-' }}</n-descriptions-item>
                <n-descriptions-item :label="t('device.cpu')">{{ deviceInfo.architecture || '-' }}</n-descriptions-item>
              </template>
            </n-descriptions>
          </template>
        </n-card>
      </n-grid-item>
    </n-grid>

    <!-- Logcat Output (collapsible) -->
    <n-card :bordered="false" class="logcat-card" size="small" style="margin-top: 16px">
      <template #header>
        <div class="card-header logcat-header" @click="logcatCollapsed = !logcatCollapsed" style="cursor: pointer;">
          <span class="card-title">{{ t('device.logcat') }}</span>
          <n-space align="center">
            <n-tag v-if="isLogcatRunning" type="success" size="small" :bordered="false">
              <template #icon><n-icon><Circle /></n-icon></template>
              {{ t('device.live') }}
            </n-tag>
            <n-icon :size="18" color="#94A3B8">
              <ChevronDown v-if="!logcatCollapsed" />
              <ChevronUp v-else />
            </n-icon>
          </n-space>
        </div>
      </template>
      <div v-show="!logcatCollapsed">
        <div v-if="!isLogcatRunning" class="empty-state logcat-empty">
          <n-icon size="32" color="#475569"><Terminal /></n-icon>
          <p class="empty-title">{{ t('device.logcatNotRunning') }}</p>
          <p class="empty-desc">{{ t('device.logcatNotRunningDesc') }}</p>
        </div>
        <div v-else class="logcat-output" ref="logcatContainer">
          <div v-if="logcatOutput.length === 0" class="empty-state">
            <p>{{ t('device.waitingForOutput') }}</p>
          </div>
          <div v-for="(line, i) in logcatOutput" :key="i" class="logcat-line" :class="getLogLevel(line)">
            <span class="log-line-num">{{ i + 1 }}</span>
            <span>{{ line }}</span>
          </div>
        </div>
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import {
  Smartphone, RefreshCw, Activity, Info, Link, Link2Off, Circle,
  ChevronDown, ChevronUp, Terminal
} from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { storeToRefs } from 'pinia'

const { t } = useI18n()

const deviceStore = useDeviceStore()
const {
  devices,
  selectedDeviceId,
  selectedDevice,
  deviceInfo,
  isLogcatRunning,
  connectionStatus,
  logcatOutput
} = storeToRefs(deviceStore)

const loading = ref(false)
const logcatContainer = ref<HTMLElement | null>(null)
const logcatCollapsed = ref(true)

// Auto-scroll logcat
watch(() => logcatOutput.value.length, () => {
  nextTick(() => {
    if (logcatContainer.value) {
      logcatContainer.value.scrollTop = logcatContainer.value.scrollHeight
    }
  })
})

// Auto-expand logcat card when logcat starts
watch(() => isLogcatRunning.value, (val) => {
  if (val) logcatCollapsed.value = false
})

onUnmounted(() => {
  if (isLogcatRunning.value) {
    serviceManager.getService('device').then(svc => svc.toggleLogcat())
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

const toggleLogcat = async () => {
  const svc = await serviceManager.getService('device')
  await svc.toggleLogcat()
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
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.card-title {
  font-family: Inter, sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: #F8FAFC;
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
  padding: 40px 16px;
  color: #64748B;
  font-size: 14px;
}
.empty-state p { margin: 0; }
.empty-title {
  font-size: 14px;
  font-weight: 600;
  color: #94A3B8;
  margin-top: 4px !important;
}
.empty-desc {
  font-size: 12px;
  color: #64748B;
  max-width: 220px;
  text-align: center;
}
/* Device list items */
.device-list {
  margin: -4px 0;
}
.device-item-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.device-model {
  font-size: 14px;
  font-weight: 600;
  color: #F8FAFC;
}
.device-serial {
  font-family: 'Fira Code', monospace;
  font-size: 11px;
  color: #64748B;
}
.device-state-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.device-state-dot.online { background: #22C55E; }
.device-state-dot.warning { background: #F59E0B; }
:deep(.n-list-item) {
  border-radius: 8px;
  margin: 2px 0;
  background: transparent !important;
}
:deep(.n-list-item .n-thing) {
  background: transparent !important;
}
:deep(.n-list-item .n-thing .n-thing-main .n-thing-header) {
  background: transparent !important;
}
:deep(.n-list-item.selected) {
  background: rgba(34,197,94,0.08) !important;
}
/* Device info */
.device-descriptions {
  margin: -8px 0;
}
.info-value {
  color: #E2E8F0;
}
.info-value.highlight {
  font-weight: 600;
  color: #F8FAFC;
}
.info-value.mono {
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  color: #3B82F6;
}
/* Logcat */
.logcat-card {
  background: #1E293B;
  border-radius: 10px;
}
.logcat-header {
  user-select: none;
}
.logcat-empty {
  padding: 32px 16px;
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
  display: flex;
  gap: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  color: #CBD5E1;
}
.log-line-num {
  color: #475569;
  min-width: 28px;
  text-align: right;
  user-select: none;
  flex-shrink: 0;
}
.level-error { color: #EF4444; }
.level-warn { color: #F59E0B; }
.level-info { color: #3B82F6; }
.level-debug { color: #64748B; }
</style>
