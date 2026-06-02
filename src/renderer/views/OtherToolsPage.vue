<template>
  <div class="tools-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('tools.title') }}</h1>
        <p class="page-subtitle">{{ t('tools.subtitle') }}</p>
      </div>
      <n-button size="small" secondary @click="reloadPlugins" :loading="isLoading">
        <template #icon><n-icon><RefreshCw /></n-icon></template>
        {{ t('tools.reload') }}
      </n-button>
    </div>

    <!-- Plugin Grid -->
    <n-spin :show="isLoading">
      <div v-if="plugins.length === 0 && !isLoading" class="empty-state">
        <n-icon size="48" color="#475569"><Puzzle /></n-icon>
        <p class="empty-title">{{ t('tools.noPlugins') }}</p>
        <p class="empty-desc">{{ t('tools.noPluginsDesc') }}</p>
      </div>
      <n-grid v-else :cols="1" :x-gap="16" :y-gap="16" responsive="screen">
        <n-grid-item v-for="plugin in plugins" :key="plugin.name" span="1 600:2 1000:3">
          <n-card :bordered="false" size="small" class="plugin-card">
            
              <div class="plugin-header">
                <div class="plugin-icon">
                  <n-icon size="20" color="#22C55E"><Puzzle /></n-icon>
                </div>
                <div class="plugin-meta">
                  <span class="plugin-name">{{ plugin.name }}</span>
                  <span class="plugin-version">v{{ plugin.version }} by {{ plugin.author }}</span>
                </div>
              </div>
            <p class="plugin-desc">{{ plugin.description || t('tools.noDescription') }}</p>
            <pre v-if="plugin.lastResult" class="plugin-result">{{ plugin.lastResult }}</pre>
            <div class="plugin-actions">
              <n-button type="primary" size="small" @click="runPlugin(plugin)" :loading="plugin.running" block>
                <template #icon><n-icon><Play /></n-icon></template>
                {{ t('tools.run') }}
              </n-button>
            </div>
          </n-card>
        </n-grid-item>
      </n-grid>
    </n-spin>

    <!-- Help Section (collapsible) -->
    <n-card :bordered="false" size="small" class="help-card">
      
        <div class="help-header" @click="helpCollapsed = !helpCollapsed" style="cursor: pointer">
          <div style="display:flex;align-items:center;gap:8px">
            <n-icon size="18" color="#3B82F6"><BookOpen /></n-icon>
            <span class="card-title">{{ t('tools.howToAdd') }}</span>
          </div>
          <n-icon size="18" color="#94A3B8">
            <ChevronDown v-if="!helpCollapsed" />
            <ChevronUp v-else />
          </n-icon>
        </div>
      <div v-show="!helpCollapsed" class="help-content">
        <p class="help-intro">{{ t('tools.helpIntro') }}</p>
        <n-ol class="help-steps">
          <n-li>{{ t('tools.helpStep1') }}</n-li>
          <n-li>{{ t('tools.helpStep2') }}</n-li>
          <n-li>{{ t('tools.helpStep3') }}</n-li>
          <n-li>{{ t('tools.helpStep4') }}</n-li>
        </n-ol>
        <pre class="plugin-result" style="margin-top: 12px">DESCRIPTION = 'Plugin description'
VERSION = '1.0.0'
AUTHOR = 'Your Name'

def run(context, **kwargs):
    context.log('Starting...')
    return {'status': 'ok'}</pre>
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { RefreshCw, Puzzle, Play, BookOpen, ChevronDown, ChevronUp } from 'lucide-vue-next'
import { useNotification } from '@composables/useNotification'

const { t } = useI18n()

const plugins = ref<any[]>([])
const isLoading = ref(false)
const helpCollapsed = ref(false)
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
    showError(t('tools.loadFailed'), error.message)
  } finally { isLoading.value = false }
}

const reloadPlugins = async () => {
  isLoading.value = true
  try {
    plugins.value = (await callBackend('plugin.reload', {})) as any[] || []
    showSuccess(t('tools.pluginListUpdated'))
  } catch (error: any) {
    showError(t('tools.reloadFailed'), error.message)
  } finally { isLoading.value = false }
}

const runPlugin = async (plugin: any) => {
  plugin.running = true; plugin.lastResult = null
  try {
    const result = await callBackend('plugin.run', { name: plugin.name, params: {} })
    plugin.lastResult = JSON.stringify(result, null, 2)
    showSuccess(t('tools.pluginExecuted', { name: plugin.name }))
  } catch (error: any) {
    showError(t('tools.pluginFailed', { name: plugin.name }), error.message)
    plugin.lastResult = `Error: ${error.message}`
  } finally { plugin.running = false }
}

onMounted(() => loadPlugins())
</script>

<style scoped>
.tools-page { max-width: 1000px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title {
  font-family: Inter, sans-serif;
  font-size: 22px;
  font-weight: 700;
  color: var(--app-text-primary);
  margin: 0;
  letter-spacing: -0.02em;
}
.page-subtitle { font-size: 13px; color: var(--app-text-muted); margin: 4px 0 0; }
.card-title {
  font-family: Inter, sans-serif;
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary);
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 64px 16px;
  color: var(--app-text-dim);
  text-align: center;
}
.empty-title { font-size: 15px; font-weight: 600; color: var(--app-text-muted); margin: 0; }
.empty-desc { font-size: 13px; color: var(--app-text-dim); margin: 0; max-width: 360px; text-align: center; }

/* Plugin cards */
.plugin-card {
  background: var(--app-card-bg);
  border-radius: 10px;
  transition: border-color 0.2s;
  border: 1px solid var(--app-card-bg);
}
.plugin-card:hover {
  border-color: rgba(34,197,94,0.3);
}
.plugin-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.plugin-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: rgba(34,197,94,0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.plugin-meta {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.plugin-name { font-size: 14px; font-weight: 600; color: var(--app-text-primary); }
.plugin-version { font-size: 11px; color: var(--app-text-dim); }
.plugin-desc { color: var(--app-text-muted); font-size: 13px; margin: 0; line-height: 1.5; }
.plugin-actions { margin-top: 12px; }
.plugin-result {
  background: var(--app-code-bg);
  padding: 8px 12px;
  border-radius: 6px;
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  color: var(--app-text-secondary);
  margin-top: 10px;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
  max-height: 150px;
  overflow-y: auto;
}

/* Help card */
.help-card {
  background: var(--app-card-bg);
  border-radius: 10px;
  margin-top: 20px;
}
.help-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  user-select: none;
}
.help-content { margin-top: 4px; }
.help-intro { color: var(--app-text-secondary); font-size: 14px; line-height: 1.6; margin: 0 0 12px; }
.help-steps { color: var(--app-text-secondary); font-size: 14px; line-height: 1.8; }
.help-steps code {
  background: var(--app-code-bg);
  padding: 1px 6px;
  border-radius: 4px;
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  color: var(--app-green);
}
</style>
