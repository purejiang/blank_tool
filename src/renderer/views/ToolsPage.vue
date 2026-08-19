<template>
  <div class="tools-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('tools.title') }}</h1>
        <p class="page-subtitle">{{ t('tools.subtitle') }}</p>
      </div>
      <n-button size="small" quaternary @click="handleRefresh" :loading="loading">
        <template #icon><n-icon><RefreshCw /></n-icon></template>
        {{ t('tools.refresh') }}
      </n-button>
    </div>

    <div class="tools-content">

      <!-- Add plugin -->
      <n-card :bordered="false" class="tools-card">
        <div class="section-header">
          <n-icon size="18" color="#22C55E"><PackagePlus /></n-icon>
          <span class="section-title">{{ t('tools.addPlugin') }}</span>
        </div>
        <n-form label-placement="left" label-width="100" size="small" style="margin-top:12px;max-width:520px">
          <n-form-item :label="t('tools.module')" required>
            <n-input v-model:value="addForm.module" :placeholder="t('tools.modulePlaceholder')" style="width: 320px" />
          </n-form-item>
          <n-form-item :label="t('tools.path')">
            <n-input v-model:value="addForm.path" :placeholder="t('tools.pathPlaceholder')" style="width: 320px" />
          </n-form-item>
          <n-form-item :label="t('tools.config')">
            <n-input
              v-model:value="addForm.config"
              type="textarea"
              :rows="3"
              :placeholder="t('tools.configPlaceholder')"
              style="width: 320px"
            />
          </n-form-item>
          <n-form-item label=" ">
            <n-button
              size="small"
              type="primary"
              :disabled="!addForm.module.trim()"
              :loading="submitting"
              @click="handleAdd"
            >
              <template #icon><n-icon><PackagePlus /></n-icon></template>
              {{ t('tools.submit') }}
            </n-button>
          </n-form-item>
        </n-form>
      </n-card>

      <!-- Plugin list -->
      <n-card :bordered="false" class="tools-card">
        <div class="section-header">
          <n-icon size="18" color="#3B82F6"><Puzzle /></n-icon>
          <span class="section-title">{{ t('tools.listTitle') }}</span>
        </div>

        <div v-if="loading && plugins.length === 0" class="plugin-loading">
          <n-spin size="small" />
        </div>

        <div v-else-if="plugins.length === 0" class="plugin-empty">
          {{ t('tools.empty') }}
        </div>

        <div v-else class="plugin-list">
          <div v-for="plugin in plugins" :key="plugin.module" class="plugin-row">
            <div class="plugin-info">
              <div class="plugin-name-row">
                <span class="plugin-name">{{ plugin.module }}</span>
                <n-tag size="tiny" :bordered="false" :type="kindTagType(plugin.kind)">{{ kindLabel(plugin.kind) }}</n-tag>
                <span class="plugin-version">{{ t('common.version') }}{{ plugin.version || t('common.unknown') }}</span>
              </div>
              <div class="plugin-status-row">
                <template v-if="plugin.loaded">
                  <n-icon size="14" color="#22C55E"><CheckCircle /></n-icon>
                  <span class="plugin-status-ok">{{ t('tools.loaded') }}</span>
                </template>
                <template v-else>
                  <n-icon size="14" color="#EF4444"><AlertCircle /></n-icon>
                  <span class="plugin-status-err">{{ t('tools.loadError') }}{{ plugin.error ? `：${plugin.error}` : '' }}</span>
                </template>
              </div>
            </div>
            <n-button
              size="tiny"
              quaternary
              type="error"
              :disabled="plugin.kind === 'shipped-native'"
              :loading="deletingModule === plugin.module"
              @click="confirmDelete(plugin)"
            >
              <template #icon><n-icon size="13"><Trash2 /></n-icon></template>
            </n-button>
          </div>
        </div>
      </n-card>

    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { NIcon, NButton, NTag, NSpin, useDialog } from 'naive-ui'
import { PackagePlus, Puzzle, RefreshCw, Trash2, CheckCircle, AlertCircle } from 'lucide-vue-next'
import { usePluginStore } from '@stores/pluginStore'
import { useNotification } from '@composables/useNotification'
import type { PluginEntry } from '../../shared/ipc/protocol'

const { t } = useI18n()
const { showSuccess, showError } = useNotification()
const dialog = useDialog()

const pluginStore = usePluginStore()
const { plugins, loading } = storeToRefs(pluginStore)

const addForm = reactive({ module: '', path: '', config: '' })
const submitting = ref(false)
const deletingModule = ref<string | null>(null)

const kindTagType = (kind: string) => {
  if (kind === 'shipped-native') return 'info'
  if (kind === 'native') return 'success'
  return 'warning'
}

const kindLabel = (kind: string) => {
  if (kind === 'shipped-native') return t('tools.kindShippedNative')
  if (kind === 'native') return t('tools.kindNative')
  if (kind === 'descriptor') return t('tools.kindDescriptor')
  return kind
}

const handleAdd = async () => {
  const module = addForm.module.trim()
  if (!module) return

  const path = addForm.path.trim() || undefined

  let config: Record<string, unknown> | undefined
  const configText = addForm.config.trim()
  if (configText) {
    try {
      config = JSON.parse(configText)
    } catch {
      showError(t('tools.invalidJson'))
      return
    }
  }

  submitting.value = true
  try {
    await pluginStore.addPlugin(module, path, config)
    if (pluginStore.error) {
      showError(t('tools.addFailed'), pluginStore.error)
    } else {
      showSuccess(t('tools.addSuccess'))
      addForm.module = ''
      addForm.path = ''
      addForm.config = ''
    }
  } finally {
    submitting.value = false
  }
}

const confirmDelete = (plugin: PluginEntry) => {
  dialog.warning({
    title: t('tools.deleteConfirmTitle'),
    content: t('tools.deleteConfirmContent', { module: plugin.module }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      deletingModule.value = plugin.module
      try {
        await pluginStore.deletePlugin(plugin.module)
        if (pluginStore.error) {
          showError(t('tools.deleteFailed'), pluginStore.error)
        } else {
          showSuccess(t('tools.deleteSuccess'))
        }
      } finally {
        deletingModule.value = null
      }
    }
  })
}

const handleRefresh = async () => {
  await pluginStore.reloadPlugins()
  if (pluginStore.error) {
    showError(t('tools.refreshFailed'), pluginStore.error)
  }
}

onMounted(() => {
  pluginStore.fetchPlugins()
})
</script>

<style scoped>
.tools-page { max-width: 740px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title { font-family: Inter, sans-serif; font-size: 22px; font-weight: 700; color: var(--app-text-primary); margin: 0; letter-spacing: -0.02em; }
.page-subtitle { font-size: 13px; color: var(--app-text-muted); margin: 4px 0 0; }
.tools-content { display: flex; flex-direction: column; gap: 16px; }
.tools-card { background: var(--app-card-bg); border-radius: 10px; }
.section-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; justify-content: flex-start; }
.section-title { font-family: Inter, sans-serif; font-size: 15px; font-weight: 600; color: var(--app-text-primary); }
.plugin-loading { display: flex; justify-content: center; padding: 16px 0; }
.plugin-empty { font-size: 13px; color: var(--app-text-dim); padding: 8px 0; }
.plugin-list { display: flex; flex-direction: column; gap: 6px; }
.plugin-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 10px; background: var(--app-storage-bg); border-radius: 8px; }
.plugin-info { display: flex; flex-direction: column; gap: 4px; min-width: 0; flex: 1; }
.plugin-name-row { display: flex; align-items: center; gap: 8px; min-width: 0; }
.plugin-name { font-size: 13px; font-weight: 600; color: var(--app-text-primary); font-family: 'Fira Code', monospace; white-space: nowrap; }
.plugin-version { font-size: 11px; color: var(--app-text-dim); white-space: nowrap; }
.plugin-status-row { display: flex; align-items: center; gap: 6px; }
.plugin-status-ok { font-size: 12px; color: var(--app-text-muted); }
.plugin-status-err { font-size: 12px; color: #EF4444; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
