<template>
  <n-card :bordered="false" class="app-manager-card" size="small">
    <template #header>
      <div class="card-header">
        <span class="card-title">{{ t('appManager.title') }}</span>
        <n-space :size="8">
          <n-tag v-if="selectedDevice && apps.length > 0" :bordered="false" type="info" size="small">
            {{ filteredApps.length }} / {{ apps.length }}
          </n-tag>
          <n-button
            size="tiny"
            secondary
            :disabled="!selectedDevice"
            @click="refreshAppList"
          >
            <template #icon><n-icon><RefreshCw /></n-icon></template>
          </n-button>
          <n-button
            size="tiny"
            secondary
            :disabled="!selectedDevice || apps.length === 0"
            @click="exportAppList"
          >
            <template #icon><n-icon><FileDown /></n-icon></template>
          </n-button>
        </n-space>
      </div>
    </template>

    <!-- Filters -->
    <div class="filter-row">
      <n-select
        v-model:value="appType"
        :options="appTypeOptions"
        :disabled="!selectedDevice"
        size="small"
        :placeholder="t('appManager.appType')"
        @update:value="refreshAppList"
        style="width: 140px"
      />
      <n-input
        v-model:value="searchQuery"
        :placeholder="t('appManager.searchPlaceholder')"
        :disabled="!selectedDevice"
        size="small"
        clearable
      >
        <template #prefix>
          <n-icon size="14"><Search /></n-icon>
        </template>
      </n-input>
    </div>

    <!-- App List -->
    <n-spin :show="loading">
      <div v-if="!selectedDevice" class="empty-state">
        <n-icon size="28" color="#475569"><Package /></n-icon>
        <p class="empty-title">{{ t('appManager.noDeviceSelected') }}</p>
        <p class="empty-desc">{{ t('appManager.noDeviceSelectedDesc') }}</p>
      </div>
      <div v-else-if="apps.length === 0" class="empty-state">
        <n-icon size="28" color="#475569"><Inbox /></n-icon>
        <p class="empty-title">{{ t('appManager.noApps') }}</p>
        <p class="empty-desc">{{ t('appManager.noAppsDesc') }}</p>
      </div>
      <div v-else-if="filteredApps.length === 0" class="empty-state">
        <n-icon size="28" color="#475569"><Search /></n-icon>
        <p class="empty-title">{{ t('appManager.noMatches') }}</p>
        <p class="empty-desc">{{ t('appManager.noMatchesDesc') }}</p>
      </div>
      <n-scrollbar v-else style="max-height: 320px">
        <n-list hoverable clickable class="app-list">
          <n-list-item v-for="app in filteredApps" :key="app.packageName">
            <template #prefix>
              <n-icon size="16" color="#64748B"><Box /></n-icon>
            </template>
            <span class="app-package-name" :title="app.packageName">
              {{ app.packageName }}
            </span>
            <template #suffix>
              <n-space :size="4">
                <n-button
                  size="tiny"
                  secondary
                  type="success"
                  :loading="isExporting && isExporting(app.packageName)"
                  @click="exportApp(app.packageName)"
                >
                  <template #icon><n-icon><Download /></n-icon></template>
                </n-button>
                <n-button
                  size="tiny"
                  secondary
                  type="error"
                  @click="uninstallApp(app.packageName)"
                >
                  <template #icon><n-icon><Trash2 /></n-icon></template>
                </n-button>
              </n-space>
            </template>
          </n-list-item>
        </n-list>
      </n-scrollbar>
    </n-spin>
  </n-card>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import {
  RefreshCw, FileDown, Download, Trash2, Search, Package,
  Inbox, Box
} from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { storeToRefs } from 'pinia'

const { t } = useI18n()

const deviceStore = useDeviceStore()
const {
  selectedDevice,
  apps,
  appType
} = storeToRefs(deviceStore)

const searchQuery = ref('')
const loading = ref(false)
const deviceSvcRef = ref<any>(null)
const exportingPackages = ref(new Set<string>())

const appTypeOptions = computed(() => [
  { label: t('appManager.allApps'), value: 'all' },
  { label: t('appManager.systemApps'), value: 'system' },
  { label: t('appManager.userApps'), value: 'user' },
  { label: t('appManager.enabled'), value: 'enabled' },
  { label: t('appManager.disabled'), value: 'disabled' },
])

const filteredApps = computed(() => {
  const q = String(searchQuery.value || '').trim().toLowerCase()
  if (!q) return apps.value
  return apps.value.filter(a => String(a.packageName || '').toLowerCase().includes(q))
})

const isExporting = (packageName: string) => {
  return exportingPackages.value.has(packageName)
}

const refreshAppList = async () => {
  loading.value = true
  try {
    const svc = deviceSvcRef.value || await serviceManager.getService('device')
    deviceSvcRef.value = svc
    await svc.refreshAppList()
  } finally {
    loading.value = false
  }
}

const exportAppList = async () => {
  const svc = deviceSvcRef.value || await serviceManager.getService('device')
  deviceSvcRef.value = svc
  await svc.exportAppList()
}

const exportApp = async (packageName: string) => {
  if (exportingPackages.value.has(packageName)) return

  exportingPackages.value.add(packageName)
  try {
    const svc = deviceSvcRef.value || await serviceManager.getService('device')
    deviceSvcRef.value = svc
    await svc.exportApp(packageName)
  } finally {
    exportingPackages.value.delete(packageName)
  }
}

const uninstallApp = async (packageName: string) => {
  const svc = deviceSvcRef.value || await serviceManager.getService('device')
  deviceSvcRef.value = svc
  await svc.uninstallApp(packageName)
}
</script>

<style scoped>
.app-manager-card {
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
.filter-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.app-list {
  margin: -4px 0;
}
.app-package-name {
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  color: #CBD5E1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.n-list-item) {
  border-radius: 8px;
  margin: 2px 0;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 32px 16px;
  color: #64748B;
  font-size: 14px;
}
.empty-state p { margin: 0; }
.empty-title {
  font-size: 13px;
  font-weight: 600;
  color: #94A3B8;
}
.empty-desc {
  font-size: 12px;
  color: #64748B;
}
</style>
