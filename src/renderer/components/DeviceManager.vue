<template>
  <n-card :bordered="false" class="device-card" size="small">
    <div class="card-header">
      <n-icon size="18" color="#22C55E"><Smartphone /></n-icon>
      <span class="card-title">{{ t('device.devices') }}</span>
      <n-tag size="small" :bordered="false" type="info">
        {{ t('device.connected', { count: devices.length }) }}
      </n-tag>
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
    <div class="card-footer">
      <n-button @click="$emit('refreshDevices')" :loading="loading" secondary size="small" block>
        <template #icon><n-icon><RefreshCw /></n-icon></template>
        {{ t('device.refresh') }}
      </n-button>
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

defineEmits<{ refreshDevices: [] }>()

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
  background: #1E293B;
  border-radius: 10px;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.card-title {
  font-family: Inter, sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: #F8FAFC;
  flex: 1;
}
.card-footer {
  margin-top: 12px;
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
.empty-title { font-size: 14px; font-weight: 600; color: #94A3B8; margin-top: 4px !important; }
.empty-desc { font-size: 12px; color: #64748B; max-width: 220px; text-align: center; }

.device-list { margin: -4px 0; }
.device-icon-wrap { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.device-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.device-model { font-size: 14px; font-weight: 600; color: #F8FAFC; }
.device-serial { font-family: 'Fira Code', monospace; font-size: 11px; color: #64748B; }
.device-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: #EF4444; }
.device-dot.online { background: #22C55E; }
.device-dot.warning { background: #F59E0B; }
:deep(.device-list .n-list-item) { background: transparent !important; }
:deep(.device-list .n-list-item:hover) { background: rgba(255,255,255,0.03) !important; }
:deep(.device-list .n-list-item.selected) { background: rgba(34,197,94,0.08) !important; }
</style>
