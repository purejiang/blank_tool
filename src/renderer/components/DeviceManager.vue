<template>
  <n-card :bordered="false" class="device-card" size="small">
    <div class="dm-header">
      <div class="dm-header-left">
        <n-icon size="18" color="#22C55E"><Smartphone /></n-icon>
        <span class="dm-title">{{ t('device.devices') }}</span>
      </div>
      <div class="dm-header-right">
        <span class="dm-count"><span class="dm-count-label">{{ t('device.connectedLabel') }}</span><span class="dm-count-num">{{ devices.length }}</span></span>
        <n-button @click="$emit('refreshDevices')" :loading="loading" quaternary circle size="tiny">
          <template #icon><n-icon size="16"><RefreshCw /></n-icon></template>
        </n-button>
      </div>
    </div>
    <n-spin :show="loading">
      <div v-if="devices.length === 0" class="empty-state">
        <n-icon size="36" color="#475569"><Smartphone /></n-icon>
        <p class="empty-title">{{ t('device.noDevices') }}</p>
        <p class="empty-desc">{{ t('device.noDevicesDesc') }}</p>
      </div>
      <n-list v-else hoverable clickable class="device-list">
        <n-list-item
          v-for="device in devices"
          :key="device.id"
          :class="{ selected: selectedDeviceId === device.id }"
          @click="handleDeviceSelection(device.id)"
        >
          <template #prefix>
            <div class="device-icon-wrap">
              <n-icon size="20" :color="device.status === 'device' ? '#22C55E' : '#F59E0B'">
                <Smartphone />
              </n-icon>
            </div>
          </template>
          <div class="device-info">
            <span class="device-model">{{ device.name || t('device.unknownDevice') }}</span>
            <span class="device-serial">{{ device.id }}</span>
          </div>
          <template #suffix>
            <div class="device-dot" :class="device.status === 'device' ? 'online' : 'warning'"></div>
          </template>
        </n-list-item>
      </n-list>
    </n-spin>
    <div class="dm-remote">
      <div class="dm-remote-title">{{ t('device.remoteConnect') }}</div>
      <div class="dm-remote-row">
        <n-input
          v-model:value="remoteAddress"
          :placeholder="t('device.remoteAddressPlaceholder')"
          size="tiny"
          clearable
          class="dm-remote-input"
          @keyup.enter="handleConnect"
        />
        <n-button size="tiny" type="primary" secondary @click="handleConnect" :loading="isConnecting">
          {{ t('device.connect') }}
        </n-button>
        <n-button size="tiny" secondary @click="handleDisconnect" :loading="isDisconnecting">
          {{ t('device.disconnect') }}
        </n-button>
      </div>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { Smartphone, RefreshCw } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { storeToRefs } from 'pinia'

const { t } = useI18n()

const deviceStore = useDeviceStore()
const { devices, selectedDeviceId } = storeToRefs(deviceStore)

const loading = ref(false)
const remoteAddress = ref('')
const isConnecting = ref(false)
const isDisconnecting = ref(false)

const emit = defineEmits<{ refreshDevices: [] }>()

const handleConnect = async () => {
  const addr = remoteAddress.value.trim()
  if (!addr) return
  isConnecting.value = true
  try {
    const api = window.electronAPI as any
    const result = await api.adbConnect(addr)
    if (result?.success) {
      remoteAddress.value = ''
      emit('refreshDevices')
    }
  } catch (e: any) {
    console.error('ADB connect failed:', e)
  } finally { isConnecting.value = false }
}

const handleDisconnect = async () => {
  isDisconnecting.value = true
  try {
    const api = window.electronAPI as any
    const addr = remoteAddress.value.trim()
    await api.adbDisconnect(addr || undefined)
    if (addr) remoteAddress.value = ''
    emit('refreshDevices')
  } catch (e: any) {
    console.error('ADB disconnect failed:', e)
  } finally { isDisconnecting.value = false }
}

const handleDeviceSelection = async (id: string) => {
  if (loading.value) return
  loading.value = true
  deviceStore.selectDevice(id)
  if (id) {
    try {
      const svc = await serviceManager.getService('device')
      await svc.getDeviceInfo(id)
    } catch {}
  }
  loading.value = false
}
</script>

<style scoped>
.device-card {
  background: var(--app-card-bg);
  border-radius: 10px;
}
.dm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.dm-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dm-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.dm-count {
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 2px;
}
.dm-count-label {
  color: var(--app-text-dim);
}
.dm-count-num {
  color: var(--app-green);
  font-weight: 600;
}
.dm-remote {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--app-card-border);
}
.dm-remote-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-muted);
  margin-bottom: 8px;
}
.dm-remote-row {
  display: flex;
  gap: 6px;
}
.dm-remote-input {
  flex: 1;
}
.dm-title {
  font-family: Inter, sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 16px;
  color: var(--app-text-dim);
  font-size: 14px;
}
.empty-state p { margin: 0; }
.empty-title { font-size: 14px; font-weight: 600; color: var(--app-text-muted); margin-top: 4px !important; }
.empty-desc { font-size: 12px; color: var(--app-text-dim); max-width: 220px; text-align: center; }

.device-list { margin: -4px 0; }
.device-icon-wrap { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.device-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.device-model { font-size: 14px; font-weight: 600; color: var(--app-text-primary); }
.device-serial { font-family: 'Fira Code', monospace; font-size: 11px; color: var(--app-text-dim); }
.device-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: var(--app-red); }
.device-dot.online { background: var(--app-green); }
.device-dot.warning { background: var(--app-yellow); }
:deep(.device-list .n-list-item) { background: transparent !important; }
:deep(.device-list .n-list-item:hover) { background: rgba(255,255,255,0.03) !important; }
:deep(.device-list .n-list-item.selected) { background: rgba(34,197,94,0.08) !important; }
</style>
