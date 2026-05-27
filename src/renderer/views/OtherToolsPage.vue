<template>
  <div class="tools-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">Plugins & Tools</h1>
        <p class="page-subtitle">Manage and run extension plugins</p>
      </div>
    </div>

    <n-grid :cols="1" responsive="screen">
      <n-grid-item span="1 800:2">
        <n-card title="Plugins" :bordered="false" size="small" class="tools-card">
          <template #header-extra>
            <n-button size="tiny" quaternary @click="reloadPlugins" :loading="isLoading">
              <template #icon><n-icon><RefreshCw /></n-icon></template>
            </n-button>
          </template>
          <div v-if="plugins.length === 0 && !isLoading" class="empty-state">
            <n-icon size="36" color="#475569"><Puzzle /></n-icon>
            <p>No plugins loaded</p>
          </div>
          <n-spin :show="isLoading">
            <n-list v-if="plugins.length > 0" hoverable>
              <n-list-item v-for="plugin in plugins" :key="plugin.name">
                <n-thing :title="plugin.name" :description="'v' + plugin.version + ' by ' + plugin.author">
                  <p class="plugin-desc">{{ plugin.description }}</p>
                  <template #action>
                    <n-button size="tiny" type="primary" @click="runPlugin(plugin)" :loading="plugin.running">
                      Run
                    </n-button>
                  </template>
                  <pre v-if="plugin.lastResult" class="plugin-result">{{ plugin.lastResult }}</pre>
                </n-thing>
              </n-list-item>
            </n-list>
          </n-spin>
        </n-card>
      </n-grid-item>

      <n-grid-item span="1 800:1">
        <n-card title="How to Add Plugins" :bordered="false" size="small" class="tools-card">
          <p style="color: #CBD5E1; font-size: 14px; line-height: 1.6;">Extend Blank Tool by writing Python scripts.</p>
          <n-ol>
            <n-li>Write a Python script (e.g. <code>my_tool.py</code>)</n-li>
            <n-li>Implement the <code>run(context, **kwargs)</code> function</n-li>
            <n-li>Place the script in the <code>backend/plugins</code> directory</n-li>
            <n-li>Click the reload button above</n-li>
          </n-ol>
          <n-code code="
DESCRIPTION = 'Plugin description'
VERSION = '1.0.0'
AUTHOR = 'Your Name'

def run(context, **kwargs):
    context.log('Starting...')
    return {'status': 'ok'}" language="python" style="margin-top: 12px" />
        </n-card>
      </n-grid-item>
    </n-grid>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NIcon } from 'naive-ui'
import { RefreshCw, Puzzle } from 'lucide-vue-next'
import { useNotification } from '@/composables/useNotification'

const plugins = ref<any[]>([])
const isLoading = ref(false)
const { showSuccess, showError } = useNotification()

const callBackend = async (method: string, payload: Record<string, unknown> = {}) => {
  const api = window.electronAPI
  if (api && typeof api.callBackendAPI === 'function') {
    return await (api.callBackendAPI as Function)(method, payload)
  }
  return []
}

const loadPlugins = async () => {
  isLoading.value = true
  try {
    plugins.value = (await callBackend('plugin.list', {})) as any[] || []
  } catch (error: any) {
    showError('Failed to load plugins', error.message)
  } finally { isLoading.value = false }
}

const reloadPlugins = async () => {
  isLoading.value = true
  try {
    plugins.value = (await callBackend('plugin.reload', {})) as any[] || []
    showSuccess('Plugin list updated')
  } catch (error: any) {
    showError('Failed to reload plugins', error.message)
  } finally { isLoading.value = false }
}

const runPlugin = async (plugin: any) => {
  plugin.running = true; plugin.lastResult = null
  try {
    const result = await callBackend('plugin.run', { name: plugin.name, params: {} })
    plugin.lastResult = JSON.stringify(result, null, 2)
    showSuccess(`Plugin ${plugin.name} executed`)
  } catch (error: any) {
    showError(`Plugin ${plugin.name} failed`, error.message)
    plugin.lastResult = `Error: ${error.message}`
  } finally { plugin.running = false }
}

onMounted(() => loadPlugins())
</script>

<style scoped>
.tools-page { max-width: 1000px; margin: 0 auto; }
.page-header { margin-bottom: 20px; }
.page-title { font-family: Inter, sans-serif; font-size: 22px; font-weight: 700; color: #F8FAFC; margin: 0; letter-spacing: -0.02em; }
.page-subtitle { font-size: 13px; color: #94A3B8; margin: 4px 0 0; }
.tools-card { background: #1E293B; border-radius: 10px; margin-bottom: 16px; }
.empty-state { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 32px; color: #64748B; font-size: 14px; }
.plugin-desc { color: #94A3B8; font-size: 13px; margin: 4px 0; }
.plugin-result { background: #0C1322; padding: 8px 12px; border-radius: 6px; font-family: 'Fira Code', monospace; font-size: 12px; color: #CBD5E1; margin-top: 8px; white-space: pre-wrap; word-break: break-all; overflow-x: auto; }
</style>
