<template>
  <!-- S6.3 插件页（docs/08 §3-S6.3）：清单加载器里的插件与加载状态。
       ⚠️ 本页**不显示环境依赖徽章、也不显示"该插件注册了哪些工具"**——后端没有
       这两个字段（缺口 #18），画上去就是编数据。 -->
  <div class="screen plugins-page">
    <PageHeader :title="t('plugins.title')" :description="t('plugins.subtitle')">
      <template #nav><ToolsSectionNav active="plugins" /></template>
    </PageHeader>

    <div class="plugins-toolbar">
      <n-button size="small" type="primary" @click="openAddDialog">
        <template #icon><AppIcon name="pkg" /></template>
        {{ t('plugins.add') }}
      </n-button>
      <!-- 「重新加载插件」是动作：重跑清单加载器，与「重取列表」不是一回事。 -->
      <n-button size="small" :loading="reloading" @click="reload">
        <template #icon><AppIcon name="loop" /></template>
        {{ t('plugins.reload') }}
      </n-button>
    </div>

    <div class="plugins-hint">{{ t('plugins.reloadHint') }}</div>

    <div v-if="loading && plugins.length === 0" class="plugins-status">{{ t('plugins.loading') }}</div>
    <AppNotice v-else-if="loadError" tone="danger">
      {{ t('plugins.loadFailed', { error: loadError }) }}
      <template #action>
        <AppButton variant="outline" size="tiny" @click="fetchPlugins">{{ t('workflows.retry') }}</AppButton>
      </template>
    </AppNotice>
    <div v-else-if="plugins.length === 0" class="plugins-empty">
      <div class="plugins-empty-title">{{ t('plugins.empty') }}</div>
      <n-button size="small" type="primary" @click="openAddDialog">{{ t('plugins.add') }}</n-button>
    </div>

    <div v-else class="plugins-rows">
      <div v-for="plugin in plugins" :key="plugin.module" class="plugin-row">
        <div class="plugin-main">
          <div class="plugin-head">
            <span class="plugin-name" :title="plugin.module">{{ plugin.module }}</span>
            <n-tag size="tiny" :bordered="false" :color="kindTagColor(plugin.kind)">
              {{ kindLabel(plugin.kind) }}
            </n-tag>
            <n-tag v-if="plugin.source === 'user'" size="tiny" :bordered="false">
              {{ t('plugins.source.user') }}
            </n-tag>
            <span v-if="plugin.version" class="plugin-version">v{{ plugin.version }}</span>
          </div>
          <div class="plugin-status">
            <template v-if="plugin.loaded">
              <AppIcon name="check" style="color: var(--success-text)" />
              <span class="plugin-status-ok">{{ t('plugins.status.loaded') }}</span>
            </template>
            <template v-else>
              <AppIcon name="alert-circle" style="color: var(--danger-text)" />
              <span class="plugin-status-err">
                {{ plugin.error === 'not loaded' ? t('plugins.status.notLoaded') : t('plugins.status.failed') }}
                <template v-if="plugin.error && plugin.error !== 'not loaded'">：{{ plugin.error }}</template>
              </span>
            </template>
          </div>
        </div>
        <AppButton
          variant="danger-ghost"
          size="tiny"
          :disabled="plugin.kind === 'shipped-native'"
          :title="plugin.kind === 'shipped-native' ? t('plugins.deleteProtected') : ''"
          :loading="deletingModule === plugin.module"
          @click="confirmDelete(plugin)"
        >
          {{ t('tasks.actions.delete') }}
        </AppButton>
      </div>
    </div>

    <!-- 添加插件：module / path / config -->
    <n-modal v-model:show="addDialog.show" preset="card" :title="t('plugins.add')" :style="{ width: '520px' }" :mask-closable="!adding">
      <n-form label-placement="top" size="small">
        <n-form-item :label="t('plugins.module')" required>
          <n-input v-model:value="addDialog.module" :placeholder="t('plugins.modulePlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('plugins.path')">
          <n-input v-model:value="addDialog.path" :placeholder="t('plugins.pathPlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('plugins.config')" :feedback="t('plugins.configHint')">
          <n-input
            v-model:value="addDialog.config"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 10 }"
            class="plugins-json"
            placeholder='{ "key": "value" }'
          />
        </n-form-item>
      </n-form>
      <AppNotice v-if="addDialog.error" tone="danger">{{ addDialog.error }}</AppNotice>
      <template #footer>
        <AppDialogFooter>
          <AppButton variant="outline" :disabled="adding" @click="addDialog.show = false">
            {{ t('workflow.editor.template.cancel') }}
          </AppButton>
          <AppButton
            variant="primary"
            :disabled="!addDialog.module.trim()"
            :loading="adding"
            @click="submitAdd"
          >
            {{ t('plugins.add') }}
          </AppButton>
        </AppDialogFooter>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAlert, NButton, NForm, NFormItem, NInput, NModal, NTag, useDialog } from 'naive-ui'
import AppIcon from '@components/ui/AppIcon.vue'
import AppButton from '@components/ui/AppButton.vue'
import AppDialogFooter from '@components/ui/AppDialogFooter.vue'
import AppNotice from '@components/ui/AppNotice.vue'
import PageHeader from '@components/ui/PageHeader.vue'
import { storeToRefs } from 'pinia'

import ToolsSectionNav from '@components/tools/ToolsSectionNav.vue'
import { usePluginStore } from '@stores/pluginStore'
import { useNotification } from '@composables/useNotification'
import type { PluginEntry } from '../../shared/ipc/protocol'
import unifiedApi from '@/api/unifiedApi'
import { log } from '@utils/logger'

/**
 * S6.3 — 插件清单与加载状态（原 `ToolsPage` 的插件部分迁移到这里）。
 */
const { t } = useI18n()
const dialog = useDialog()
const { showSuccess, showError } = useNotification()

const pluginStore = usePluginStore()
const { plugins } = storeToRefs(pluginStore)

const loading = ref(false)
const loadError = ref('')
const reloading = ref(false)
const adding = ref(false)
const deletingModule = ref<string | null>(null)
const addDialog = reactive({ show: false, module: '', path: '', config: '', error: null as string | null })

function errMsg(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

/**
 * 插件种类徽章：设计契约里 `.badge kind` 是紫点缀（本地此前用主色，已回正）。
 * 内置用紫、第三方插件保持中性 —— 两个徽章别抢同一档视觉权重。
 */
function kindTagColor(kind: string) {
  if (kind === 'shipped-native') {
    return { color: 'var(--purple-soft)', textColor: 'var(--purple)', borderColor: 'transparent' }
  }
  return undefined
}

/** 清单加载器只允许 `shipped-native` / `native`（描述符工具走 tool.*）。 */
function kindLabel(kind: string) {
  if (kind === 'shipped-native') return t('plugins.kind.shippedNative')
  return t('plugins.kind.native')
}

async function fetchPlugins() {
  loading.value = true
  loadError.value = ''
  try {
    await pluginStore.fetchPlugins()
    if (pluginStore.error) throw new Error(pluginStore.error)
  } catch (error) {
    log.error('[PluginsPage] plugin.list failed:', error)
    loadError.value = errMsg(error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void fetchPlugins()
})

/**
 * 重载：插件注册的工具会随之增减，所以重载后**必须重拉工具列表**——
 * 否则工具页会与插件页互相矛盾（docs/08 §3-S6.3）。
 */
async function reload() {
  reloading.value = true
  try {
    await pluginStore.reloadPlugins()
    if (pluginStore.error) throw new Error(pluginStore.error)
    await unifiedApi.call('workflow.list_tools', {})
    showSuccess(t('plugins.reloaded'))
    await fetchPlugins()
  } catch (error) {
    showError(t('plugins.reloadFailed', { error: errMsg(error) }))
  } finally {
    reloading.value = false
  }
}

function openAddDialog() {
  addDialog.module = ''
  addDialog.path = ''
  addDialog.config = ''
  addDialog.error = null
  addDialog.show = true
}

async function submitAdd() {
  addDialog.error = null
  const module = addDialog.module.trim()
  if (!module) return
  let config: Record<string, unknown> | undefined
  const text = addDialog.config.trim()
  if (text) {
    try {
      config = JSON.parse(text)
    } catch {
      addDialog.error = t('tools.invalidJson')
      return
    }
  }
  adding.value = true
  try {
    await pluginStore.addPlugin(module, addDialog.path.trim() || undefined, config)
    if (pluginStore.error) throw new Error(pluginStore.error)
    showSuccess(t('plugins.added', { module }))
    addDialog.show = false
    await fetchPlugins()
  } catch (error) {
    addDialog.error = errMsg(error)
  } finally {
    adding.value = false
  }
}

function confirmDelete(plugin: PluginEntry) {
  dialog.warning({
    title: t('plugins.deleteTitle'),
    content: t('plugins.deleteContent', { module: plugin.module }),
    positiveText: t('tasks.actions.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      deletingModule.value = plugin.module
      try {
        await pluginStore.deletePlugin(plugin.module)
        if (pluginStore.error) throw new Error(pluginStore.error)
        showSuccess(t('plugins.deleted', { module: plugin.module }))
        await fetchPlugins()
      } catch (error) {
        showError(t('plugins.deleteFailed', { error: errMsg(error) }))
      } finally {
        deletingModule.value = null
      }
    },
  })
}
</script>

<style scoped>
.plugins-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}




.plugins-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.plugins-hint {
  font-size: 11px;
  color: var(--app-text-dim);
}

.plugins-status {
  font-size: 12px;
  color: var(--app-text-muted);
}

.plugins-status-row {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.plugins-empty {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  padding: 40px 20px;
  border: 1px dashed var(--app-card-border);
  border-radius: var(--radius-control);
}

.plugins-empty-title {
  font-size: 14px;
  color: var(--app-text-secondary);
}

.plugins-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.plugin-row {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 10px 14px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-control);
}

.plugin-main {
  flex: 1;
  min-width: 0;
}

.plugin-head {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.plugin-name {
  overflow: hidden;
  font-family: var(--font-family-monospace);
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plugin-version {
  font-size: 11px;
  color: var(--app-text-dim);
}

.plugin-status {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 3px;
}

.plugin-status-ok {
  font-size: 12px;
  color: var(--app-text-muted);
}

.plugin-status-err {
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  color: var(--app-red);
  text-overflow: ellipsis;
}

.plugins-json :deep(.n-input__textarea-el) {
  font-family: var(--font-family-monospace);
  font-size: 12px;
}

.plugins-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
