<template>
  <div class="status-bar" :class="{ collapsed }">
    <!-- Minimal mode: icon + dot only when sidebar collapsed -->
    <template v-if="collapsed">
      <n-icon size="18" :color="deviceStatus === 'online' ? '#22C55E' : '#64748B'"><Smartphone /></n-icon>
      <span class="status-dot" :class="deviceStatus"></span>
    </template>
    <!-- Full mode -->
    <template v-else>
      <div class="status-device" @click="goToDevice">
        <div class="device-badge" v-if="connectedDevice">
          <n-icon size="14"><Smartphone /></n-icon>
          <span>{{ connectedDevice.name || connectedDevice.id }}</span>
          <span class="status-dot" :class="deviceStatusClass"></span>
        </div>
        <div class="device-badge off" v-else>
          <n-icon size="14" color="#64748B"><Smartphone /></n-icon>
          <span class="dim">{{ t('statusBar.noDevice') }}</span>
          <span class="status-dot offline"></span>
        </div>
      </div>
      <div class="status-version">
        <span class="version-text">v{{ frontendVersion }} | backend {{ backendVersion || 'N/A' }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { Smartphone } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import { storeToRefs } from 'pinia'
import serviceManager from '@services/ServiceManager'

const { t } = useI18n()
const router = useRouter()

defineProps<{ collapsed?: boolean }>()

const goToDevice = () => {
  router.push('/device')
}

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
  cursor: pointer;
}
.status-bar.collapsed:hover {
  background: var(--app-hover-strong);
}
.status-device {
  cursor: pointer;
  padding: 2px 0;
}
.status-device:hover {
  opacity: 0.8;
}
.status-version {
  display: flex;
  align-items: center;
}
.device-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--app-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.device-badge.off { color: var(--app-text-dim); }
.dim { color: var(--app-text-dim); }
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--app-red);
  flex-shrink: 0;
}
.status-dot.online { background: var(--app-green); }
.status-dot.connecting { background: var(--app-yellow); animation: pulse 1.5s infinite; }
.status-dot.offline { background: var(--app-red); }
.version-text {
  font-family: 'Fira Code', monospace;
  color: var(--app-text-dim);
  font-size: 10px;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
