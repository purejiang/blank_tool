<template>
  <div class="status-bar" :class="{ collapsed }">
    <!-- Minimal mode: version only when sidebar collapsed -->
    <template v-if="collapsed">
      <span class="health-dot" :class="healthClass" :title="healthTitle"></span>
    </template>
    <!-- Full mode -->
    <template v-else>
      <div class="status-version">
        <span class="version-text">v{{ frontendVersion }} | backend {{ backendVersion || 'N/A' }}</span>
        <span class="health-dot" :class="healthClass" :title="healthTitle"></span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NIcon } from 'naive-ui'
import { useBackendHealthStore } from '@stores/backendHealthStore'
import serviceManager from '@services/ServiceManager'

defineProps<{ collapsed?: boolean }>()

const frontendVersion = ref('1.0.0')
const backendVersion = ref('')

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

// Backend health dot
const healthStore = useBackendHealthStore()
healthStore.startPolling()

const healthClass = computed(() =>
  healthStore.isHealthy === null ? 'dot-unknown' :
  healthStore.isHealthy ? 'dot-healthy' : 'dot-unhealthy'
)
const healthTitle = computed(() =>
  healthStore.isHealthy === null ? 'Backend status unknown' :
  healthStore.isHealthy ? 'Backend healthy' : 'Backend down'
)
</script>

<style scoped>
.status-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 18px;
  height: auto;
  background: var(--app-sidebar-bg);
  border-top: 1px solid var(--app-sidebar-border);
  font-size: 11px;
  font-family: Inter, sans-serif;
  flex-shrink: 0;
}
.status-bar.collapsed {
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 4px;
}
.status-version {
  display: flex;
  align-items: center;
}
.version-text {
  font-family: 'Fira Code', monospace;
  color: var(--app-text-dim);
  font-size: 10px;
}
.health-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-left: 6px;
  vertical-align: middle;
}
.health-dot.dot-healthy { background: var(--app-green); }
.health-dot.dot-unhealthy { background: var(--app-red); }
.health-dot.dot-unknown { background: var(--app-text-dim); }
</style>
