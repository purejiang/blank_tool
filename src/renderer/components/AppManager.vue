<template>
  <div class="section">
    <div class="section-header">
      <h2><span class="section-icon">📦</span>应用管理</h2>
      <div class="section-actions">
        <button 
          class="btn btn-sm btn-secondary" 
          :disabled="!selectedDevice"
          @click="refreshAppList"
          data-tooltip="刷新应用列表"
        >
          <span>🔄</span>
        </button>
        <button 
          class="btn btn-sm btn-primary" 
          :disabled="!selectedDevice || apps.length === 0"
          @click="exportAppList"
          data-tooltip="导出应用列表"
        >
          <span>📄</span>
        </button>
      </div>
  </div>
  <div class="form-group">
    <label>应用类型</label>
      <select 
        class="form-control" 
        v-model="appType"
        :disabled="!selectedDevice"
        @change="refreshAppList"
      >
        <option value="all">所有应用</option>
        <option value="system">系统应用</option>
        <option value="user">用户应用</option>
        <option value="enabled">已启用应用</option>
        <option value="disabled">已禁用应用</option>
    </select>
  </div>
  <div class="form-group">
    <label>搜索应用</label>
    <input 
      class="form-control" 
      type="text" 
      v-model="searchQuery" 
      placeholder="输入包名关键字"
      :disabled="!selectedDevice"
    >
  </div>
  <div class="app-list" v-if="apps.length > 0">
    <div class="app-list-header">
      <span>包名</span>
      <span>操作</span>
    </div>
    <div class="app-list-content">
      <div v-for="app in filteredApps" :key="app.packageName" class="app-item">
        <span class="app-package-name">{{ app.packageName }}</span>
        <div class="app-actions">
          <button class="btn btn-sm btn-secondary" @click="copyPackageName(app.packageName)" data-tooltip="复制包名">📄</button>
          <button class="btn btn-sm btn-primary" @click="exportApp(app.packageName)" data-tooltip="导出应用">⏏</button>
          <button class="btn btn-sm btn-danger" @click="uninstallApp(app.packageName)" data-tooltip="卸载应用">🗑</button>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="placeholder">
      <p>没有要显示的应用</p>
    </div>
  </div>
</template>

<script>
import { useDeviceStore } from '@stores/deviceStore.js'
import serviceManager from '@services/ServiceManager.js'
import { storeToRefs } from 'pinia'
import { ref, computed } from 'vue'

export default {
  name: 'AppManager',
  setup() {
    const deviceStore = useDeviceStore()
    const { 
      selectedDevice, 
      apps, 
      appType 
    } = storeToRefs(deviceStore)

    const searchQuery = ref('')
    const filteredApps = computed(() => {
      const q = String(searchQuery.value || '').trim().toLowerCase()
      if (!q) return apps.value
      return apps.value.filter(a => String(a.packageName || '').toLowerCase().includes(q))
    })
    
    const refreshAppList = async () => {
      const svc = await serviceManager.getService('device')
      await svc.refreshAppList()
    }
    const exportAppList = async () => {
      const svc = await serviceManager.getService('device')
      await svc.exportAppList()
    }
    const copyPackageName = async (packageName) => {
      const svc = await serviceManager.getService('device')
      await svc.copyPackageName(packageName)
    }
    const exportApp = async (packageName) => {
      const svc = await serviceManager.getService('device')
      await svc.exportApp(packageName)
    }
    const uninstallApp = async (packageName) => {
      const svc = await serviceManager.getService('device')
      await svc.uninstallApp(packageName)
    }

    return {
      selectedDevice,
      apps,
      appType,
      searchQuery,
      filteredApps,
      refreshAppList,
      exportAppList,
      copyPackageName,
      exportApp,
      uninstallApp
    }
  }
}
</script>

<style scoped>
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  position: relative;
}

.section-actions {
  display: flex;
  gap: 8px;
  position: absolute;
  top: 0;
  right: 0;
}

.section-actions .btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 6px 12px;
}

.app-list {
  margin-top: 8px;
}
.app-list-header {
  display: grid;
  grid-template-columns: 1fr 120px;
  font-weight: 600;
  padding: 8px 12px;
  border: 1px solid var(--border-color, #ddd);
  border-bottom: none;
  border-radius: 8px 8px 0 0;
  background: var(--card-bg, #f8f8f8);
}
.app-list-content {
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid var(--border-color, #ddd);
  border-top: none;
  border-radius: 0 0 8px 8px;
}
.app-item {
  display: grid;
  grid-template-columns: 1fr 120px;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid #eee;
}
.app-item:last-child {
  border-bottom: none;
}
.app-package-name {
  font-family: monospace;
  font-size: 13px;
}
.app-actions .btn { margin-left: 4px; }
</style>