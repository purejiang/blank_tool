<template>
  <n-card :bordered="false" class="device-card" size="small">
    <template #header>
      <div class="card-header">
        <span class="card-title">{{ t('device.devices') }}</span>
        <n-tag size="small" :bordered="false" type="info">
          {{ t('device.connected', { count: devices.length }) }}
        </n-tag>
      </div>
    </template>
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
        >
          <template #prefix>
            <n-icon size="20" :color="device.status === 'device' ? '#22C55E' : '#F59E0B'">
              <Smartphone />
            </n-icon>
          </template>
          <div class="device-item-content" @click="handleDeviceSelection(device.id)">
            <span class="device-model">{{ device.name || t('device.unknownDevice') }}</span>
            <span class="device-serial">{{ device.id }}</span>
          </div>
          <template #suffix>
            <n-button
              size="tiny"
              secondary
              @click="handleDeviceSelection(device.id)"
              class="details-btn"
            >
              <template #icon><n-icon size="14"><Eye /></n-icon></template>
              {{ t('device.details') }}
            </n-button>
          </template>
        </n-list-item>
      </n-list>
    </n-spin>
    <template v-if="selectedDeviceId" #action>
      <n-button
        :type="isLogcatRunning ? 'error' : 'success'"
        size="small"
        @click="$emit('toggleLogcat')"
        secondary
      >
        <template #icon>
          <n-icon><Activity /></n-icon>
        </template>
        {{ isLogcatRunning ? t('device.stopLogcat') : t('device.startLogcat') }}
      </n-button>
    </template>
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
import { Smartphone, RefreshCw, Activity, Eye } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { storeToRefs } from 'pinia'

const { t } = useI18n()

const deviceStore = useDeviceStore()
const {
  devices,
  selectedDeviceId,
  isLogcatRunning,
  deviceInfo
} = storeToRefs(deviceStore)

const loading = ref(false)

defineEmits<{
  refreshDevices: []
  toggleLogcat: []
}>()

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
  justify-content: space-between;
  width: 100%;
}
.card-title {
  font-family: Inter, sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: #F8FAFC;
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
.device-list {
  margin: -4px 0;
}
.device-item-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  cursor: pointer;
  flex: 1;
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
.details-btn {
  margin-left: 4px;
}
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
</style>
