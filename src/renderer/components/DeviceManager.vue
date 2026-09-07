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
          v-for="device in deviceStore.sortedDevices"
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
            <span class="device-model">
              {{ device.name || t('device.unknownDevice') }}
              <n-icon v-if="deviceStore.isPinned(device.id)" size="12" class="device-pin-flag"><Pin /></n-icon>
            </span>
            <span class="device-serial">{{ device.id }}</span>
          </div>
          <template #suffix>
            <div class="device-actions">
              <n-button
                quaternary circle size="tiny"
                :title="deviceStore.isPinned(device.id) ? t('device.unpin') : t('device.pin')"
                @click.stop="handleTogglePin(device.id)"
              >
                <template #icon>
                  <n-icon size="14" :color="deviceStore.isPinned(device.id) ? '#22C55E' : undefined">
                    <component :is="deviceStore.isPinned(device.id) ? PinOff : Pin" />
                  </n-icon>
                </template>
              </n-button>
              <n-button
                v-if="isNetworkDevice(device.id)"
                quaternary circle size="tiny"
                :title="t('device.reconnect')"
                :loading="reconnectingId === device.id"
                @click.stop="handleReconnectDevice(device.id)"
              >
                <template #icon><n-icon size="14"><RefreshCw /></n-icon></template>
              </n-button>
              <n-button
                v-if="isNetworkDevice(device.id)"
                quaternary circle size="tiny"
                :title="t('device.disconnect')"
                :loading="disconnectingId === device.id"
                @click.stop="handleDisconnectDevice(device.id)"
              >
                <template #icon><n-icon size="14"><Unplug /></n-icon></template>
              </n-button>
              <div class="device-dot" :class="device.status === 'device' ? 'online' : 'warning'"></div>
            </div>
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
        <n-button
          size="tiny"
          secondary
          :title="t('device.saveAddress')"
          :disabled="!remoteAddress.trim()"
          @click="handleSaveAddress"
        >
          <template #icon><n-icon size="14"><Plus /></n-icon></template>
        </n-button>
      </div>
      <div v-if="deviceStore.savedAddresses.length" class="dm-saved">
        <span class="dm-saved-label">{{ t('device.savedAddresses') }}</span>
        <div class="dm-saved-chips">
          <div
            v-for="addr in deviceStore.savedAddresses"
            :key="addr"
            class="dm-chip"
            :class="{ connected: isConnected(addr) }"
          >
            <button
              class="dm-chip-connect"
              :title="t('device.connect')"
              @click="handleQuickConnect(addr)"
            >{{ addr }}</button>
            <button
              class="dm-chip-remove"
              :title="t('device.removeAddress')"
              @click.stop="handleRemoveSaved(addr)"
            >
              <n-icon size="11"><X /></n-icon>
            </button>
          </div>
        </div>
      </div>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { Smartphone, RefreshCw, Plus, X, Pin, PinOff, Unplug } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { log } from '@utils/logger'
import { storeToRefs } from 'pinia'

const { t } = useI18n()

const deviceStore = useDeviceStore()
const { devices, selectedDeviceId } = storeToRefs(deviceStore)

const loading = ref(false)
const remoteAddress = ref('')
const isConnecting = ref(false)
const disconnectingId = ref('')
const reconnectingId = ref('')

const emit = defineEmits<{ refreshDevices: [] }>()

// 该地址当前已处于 adb 连接中（设备列表里存在同 id 且在线）——芯片高亮用
const isConnected = (addr: string) =>
  devices.value.some(d => d.id === addr && d.status === 'device')

const connectAddress = async (addr: string): Promise<boolean> => {
  isConnecting.value = true
  try {
    const api = window.electronAPI as any
    const result = await api.adbConnect(addr)
    if (result?.success) {
      if (remoteAddress.value === addr) remoteAddress.value = ''
      emit('refreshDevices')
      return true
    }
    return false
  } catch (e: any) {
    log.error('ADB connect failed:', e)
    return false
  } finally { isConnecting.value = false }
}

const handleConnect = () => {
  const addr = remoteAddress.value.trim()
  if (addr) void connectAddress(addr)
}

// 一键连接常用地址（重复 add 是无害的 —— store 内部去重）
const handleQuickConnect = (addr: string) => {
  if (isConnecting.value) return
  deviceStore.addSavedAddress(addr)
  void connectAddress(addr)
}

const handleSaveAddress = () => {
  const addr = remoteAddress.value.trim()
  if (!addr) return
  deviceStore.addSavedAddress(addr)
  remoteAddress.value = ''
}

const handleRemoveSaved = (addr: string) => {
  deviceStore.removeSavedAddress(addr)
}

// 网络设备才显示重连/断开按钮（USB 序列号设备无 adb connect/disconnect 语义）：
// 1) 传统 TCP 连接 id：host:port（如 127.0.0.1:5555、192.168.1.5:5555）
// 2) 无线调试 mDNS id：adb-<serial>-<token>._adb-tls-connect._tcp.（Android 11+ 无线调试，
//    小米/安卓 11+ 机型开启「无线调试」后 adb devices -l 即此形态），同样支持 adb connect/disconnect
const isNetworkDevice = (id: string) => /^[^:]+:\d+$/.test(id) || id.includes('_adb-tls-connect')

const handleTogglePin = (id: string) => {
  deviceStore.togglePinDevice(id)
}

const handleDisconnectDevice = async (id: string) => {
  if (disconnectingId.value) return
  disconnectingId.value = id
  try {
    const api = window.electronAPI as any
    await api.adbDisconnect(id)
    emit('refreshDevices')
  } catch (e: any) {
    log.error('ADB disconnect failed:', e)
  } finally { disconnectingId.value = '' }
}

// 重连网络设备（host:port）：再次 adb connect 该地址
const handleReconnectDevice = async (id: string) => {
  if (reconnectingId.value) return
  reconnectingId.value = id
  try {
    await (window.electronAPI as any).adbConnect(id)
    emit('refreshDevices')
  } catch (e: any) {
    log.error('ADB reconnect failed:', e)
  } finally { reconnectingId.value = '' }
}

// 点击列表项：仅选中设备并刷新右侧详情面板（置顶/重连/断开等操作全走按钮）
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
.dm-saved {
  margin-top: 10px;
}
.dm-saved-label {
  font-size: 12px;
  color: var(--app-text-dim);
  margin-bottom: 6px;
}
.dm-saved-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.dm-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--app-card-border);
  border-radius: 14px;
  overflow: hidden;
  background: transparent;
  transition: border-color 0.15s;
}
.dm-chip:hover {
  border-color: var(--app-green);
}
.dm-chip.connected {
  border-color: var(--app-green);
  background: color-mix(in srgb, var(--app-green) 12%, transparent);
}
.dm-chip-connect {
  border: none;
  background: transparent;
  color: var(--app-text-muted);
  font-family: 'Fira Code', monospace;
  font-size: 11px;
  padding: 4px 6px 4px 10px;
  cursor: pointer;
}
.dm-chip.connected .dm-chip-connect {
  color: var(--app-green);
  font-weight: 600;
}
.dm-chip-remove {
  border: none;
  background: transparent;
  color: var(--app-text-dim);
  display: flex;
  align-items: center;
  padding: 4px 8px 4px 4px;
  cursor: pointer;
}
.dm-chip-remove:hover {
  color: var(--app-red);
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
.device-model { font-size: 14px; font-weight: 600; color: var(--app-text-primary); display: inline-flex; align-items: center; gap: 4px; }
.device-pin-flag { color: var(--app-green); flex-shrink: 0; }
.device-actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
.device-serial { font-family: 'Fira Code', monospace; font-size: 11px; color: var(--app-text-dim); }
.device-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: var(--app-red); }
.device-dot.online { background: var(--app-green); }
.device-dot.warning { background: var(--app-yellow); }
:deep(.device-list .n-list-item) { background: transparent !important; }
:deep(.device-list .n-list-item:hover) { background: rgba(255,255,255,0.03) !important; }
:deep(.device-list .n-list-item.selected) { background: rgba(34,197,94,0.08) !important; }
</style>
