<template>
  <!-- S6.2 环境页（docs/08 §3-S6.2）：检测到的 Java / Python / Node 等运行环境。
       告警带是 S6.1 依赖徽章的**反向视图**：工具页回答"我缺什么"，这里回答
       "缺了会怎样"。 -->
  <div class="screen envs-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('envs.title') }}</h1>
        <p class="page-subtitle">{{ t('envs.subtitle') }}</p>
      </div>
      <div class="page-header-right">
        <ToolsSectionNav active="env" />
      </div>
    </div>

    <!-- 告警带：存在未配置且被工具依赖的环境 -->
    <n-alert v-if="blockedEnvs.length > 0" type="warning" :show-icon="true" class="envs-banner">
      <div class="envs-banner-row">
        <span>{{ t('envs.alert', { env: blockedEnvs[0].label, count: blockedEnvs[0].count }) }}</span>
        <n-button size="tiny" @click="goTools">{{ t('envs.viewAffected') }}</n-button>
      </div>
    </n-alert>

    <div class="envs-toolbar">
      <n-button size="small" quaternary :loading="loading" @click="load(true)">
        <template #icon><n-icon size="15"><RefreshCw /></n-icon></template>
        {{ t('tools.refresh') }}
      </n-button>
      <n-button size="small" :loading="adding" @click="openAddDialog">
        <template #icon><n-icon size="15"><Plus /></n-icon></template>
        {{ t('envs.add') }}
      </n-button>
      <span class="envs-grow" />
      <span class="envs-hint">{{ t('envs.reprobeHint') }}</span>
    </div>

    <div v-if="loading && environments.length === 0" class="envs-status">{{ t('envs.loading') }}</div>
    <n-alert v-else-if="loadError" type="error" :show-icon="true">
      <div class="envs-status-row">
        <span>{{ t('envs.loadFailed', { error: loadError }) }}</span>
        <n-button size="tiny" @click="load(true)">{{ t('workflows.retry') }}</n-button>
      </div>
    </n-alert>
    <div v-else-if="environments.length === 0" class="envs-empty">
      <div class="envs-empty-title">{{ t('envs.empty') }}</div>
      <n-button size="small" type="primary" @click="openAddDialog">{{ t('envs.add') }}</n-button>
    </div>

    <div v-else class="envs-rows">
      <div v-for="env in environments" :key="env.name" class="env-row">
        <div class="env-main">
          <div class="env-head">
            <span class="env-name">{{ envLabel(env) }}</span>
            <n-tag size="tiny" :bordered="false" :type="env.is_valid ? 'success' : 'warning'">
              {{ env.is_valid ? t('envs.status.detected') : t('envs.status.missing') }}
            </n-tag>
            <n-tag v-if="env.source === 'overlay'" size="tiny" :bordered="false">
              {{ t('envs.source.overlay') }}
            </n-tag>
            <n-tag v-else-if="env.source === 'bundled'" size="tiny" :bordered="false">
              {{ t('envs.source.bundled') }}
            </n-tag>
            <!-- 反向依赖（渲染层按 env_deps 计数，无新后端方法） -->
            <span v-if="dependentCount(env) > 0" class="env-dependents">
              {{
                env.is_valid
                  ? t('envs.dependents', { count: dependentCount(env) })
                  : t('envs.dependentsBlocked', { count: dependentCount(env) })
              }}
            </span>
          </div>
          <div class="env-path" :title="env.binary_path || env.root_path || ''">
            {{ env.binary_path || env.root_path || t('envs.notDetected') }}
            <span v-if="env.version"> · {{ env.version }}</span>
          </div>
          <div v-if="env.path_override" class="env-override" :title="env.path_override">
            {{ t('envs.pathOverride') }}: {{ env.path_override }}
          </div>
        </div>

        <div class="env-actions">
          <n-button size="tiny" quaternary :loading="busy === `file-${env.name}`" @click="changePath(env, false)">
            {{ t('envs.changePath') }}
          </n-button>
          <n-button size="tiny" quaternary :loading="busy === `dir-${env.name}`" @click="changePath(env, true)">
            {{ t('envs.changePathDir') }}
          </n-button>
          <n-button
            v-if="env.path_override"
            size="tiny"
            quaternary
            :loading="busy === `reset-${env.name}`"
            @click="resetPath(env)"
          >
            {{ t('envs.resetPath') }}
          </n-button>
          <n-button
            size="tiny"
            quaternary
            type="error"
            :disabled="env.source === 'bundled'"
            :title="env.source === 'bundled' ? t('envs.deleteProtected') : ''"
            :loading="busy === `delete-${env.name}`"
            @click="confirmDelete(env)"
          >
            {{ t('tasks.actions.delete') }}
          </n-button>
        </div>
      </div>
    </div>

    <!-- 导入自定义环境：收整份描述符 JSON -->
    <n-modal
      v-model:show="addDialog.show"
      preset="card"
      :title="t('envs.add')"
      :style="{ width: '560px' }"
      :mask-closable="!adding"
    >
      <n-form label-placement="top" size="small">
        <n-form-item :label="t('envs.descriptor')" required :feedback="t('envs.descriptorHint')">
          <n-input
            v-model:value="addDialog.json"
            type="textarea"
            :autosize="{ minRows: 10, maxRows: 18 }"
            class="envs-json"
            placeholder='{ "name": "myenv", "display_name": "My Env", "type": "custom", ... }'
          />
        </n-form-item>
        <n-form-item>
          <n-button size="small" @click="pickDescriptorFile">{{ t('envs.loadFromFile') }}</n-button>
        </n-form-item>
      </n-form>
      <n-alert v-if="addDialog.error" type="error" :show-icon="false">{{ addDialog.error }}</n-alert>
      <template #footer>
        <div class="envs-dialog-footer">
          <n-button size="small" :disabled="adding" @click="addDialog.show = false">
            {{ t('workflow.editor.template.cancel') }}
          </n-button>
          <n-button size="small" type="primary" :loading="adding" @click="submitAdd">
            {{ t('envs.add') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NAlert, NButton, NForm, NFormItem, NIcon, NInput, NModal, NTag, useDialog } from 'naive-ui'
import { Plus, RefreshCw } from 'lucide-vue-next'

import ToolsSectionNav from '@components/tools/ToolsSectionNav.vue'
import { envDependents, envLabel } from '@components/tools/toolEnvDeps'
import type { EnvEntry, ToolEntry } from '../../shared/ipc/protocol'
import unifiedApi from '@/api/unifiedApi'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { log } from '@utils/logger'

/**
 * S6.2 — 运行环境。
 *
 * 环境与工具的依赖关系在渲染层 join：`workflow.list_tools[].env_deps` 按环境
 * `name` 计数即得「被 N 个工具依赖」与告警带，无需新后端方法。
 */
const { t } = useI18n()
const router = useRouter()
const dialog = useDialog()
const { showSuccess, showError } = useNotification()

const environments = ref<EnvEntry[]>([])
const tools = ref<ToolEntry[]>([])
const loading = ref(false)
const loadError = ref('')
const busy = ref<string | null>(null)
const adding = ref(false)

const addDialog = reactive({ show: false, json: '', error: null as string | null })

function errMsg(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

/** 环境名 → 依赖它的工具数。 */
const dependents = computed(() => envDependents(tools.value))

function dependentCount(env: EnvEntry): number {
  return dependents.value.get(env.name) ?? 0
}

/** 未配置且被依赖的环境（告警带，按依赖数倒序）。 */
const blockedEnvs = computed(() =>
  environments.value
    .filter((env) => !env.is_valid && dependentCount(env) > 0)
    .map((env) => ({ label: envLabel(env), count: dependentCount(env) }))
    .sort((a, b) => b.count - a.count),
)

async function load(refreshEnvs = false) {
  loading.value = true
  loadError.value = ''
  try {
    // 环境与工具必须一起刷新：set_path 会同时改变两侧（docs/08 §3-S6.2）
    const [envList, toolList] = await Promise.all([
      unifiedApi.call<{ environments?: EnvEntry[] }>(refreshEnvs ? 'workflow.list_envs' : 'env.list'),
      unifiedApi.call<{ tools?: ToolEntry[] }>('workflow.list_tools', {}),
    ])
    environments.value = Array.isArray(envList?.environments) ? envList.environments : []
    tools.value = Array.isArray(toolList?.tools) ? toolList.tools : []
  } catch (error) {
    log.error('[EnvsPage] loading environments failed:', error)
    loadError.value = errMsg(error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

function goTools() {
  void router.push('/tools')
}

// ---- 更改 / 重置路径 ---------------------------------------------------------

async function changePath(env: EnvEntry, asDirectory: boolean) {
  const svc = (await serviceManager.getService('system')) as any
  try {
    const picked = asDirectory
      ? await svc.selectDirectory({ title: t('envs.changePathDir') })
      : await svc.selectFile({ title: t('envs.changePath') })
    if (!picked || picked.canceled) return
    const path = (picked.filePath || (picked.filePaths && picked.filePaths[0]) || '').trim()
    if (!path) return
    busy.value = `${asDirectory ? 'dir' : 'file'}-${env.name}`
    await unifiedApi.call('env.set_path', { name: env.name, path })
    showSuccess(t('envs.pathSaved', { env: envLabel(env) }))
    await load(true)
  } catch (error) {
    showError(t('envs.pathFailed', { error: errMsg(error) }))
  } finally {
    busy.value = null
  }
}

async function resetPath(env: EnvEntry) {
  busy.value = `reset-${env.name}`
  try {
    await unifiedApi.call('env.reset_path', { name: env.name })
    showSuccess(t('envs.pathReset', { env: envLabel(env) }))
    await load(true)
  } catch (error) {
    showError(t('envs.pathFailed', { error: errMsg(error) }))
  } finally {
    busy.value = null
  }
}

// ---- 导入 / 删除 -------------------------------------------------------------

function openAddDialog() {
  addDialog.json = ''
  addDialog.error = null
  addDialog.show = true
}

async function pickDescriptorFile() {
  const svc = (await serviceManager.getService('system')) as any
  try {
    const picked = await svc.selectFile({
      title: t('envs.loadFromFile'),
      properties: ['openFile'],
      filters: [{ name: 'JSON', extensions: ['json'] }],
    })
    if (!picked || picked.canceled) return
    const file = (picked.filePath || (picked.filePaths && picked.filePaths[0]) || '').trim()
    if (!file) return
    const read = await svc.readTextFile(file)
    if (!read || read.success === false) throw new Error(read?.error || t('tools.readFailed'))
    addDialog.json = read.content
  } catch (error) {
    addDialog.error = errMsg(error)
  }
}

async function submitAdd() {
  addDialog.error = null
  let descriptor: Record<string, unknown>
  try {
    descriptor = JSON.parse(addDialog.json || '{}')
  } catch {
    addDialog.error = t('tools.invalidJson')
    return
  }
  if (!descriptor || typeof descriptor !== 'object' || Array.isArray(descriptor)) {
    addDialog.error = t('tools.invalidJson')
    return
  }
  adding.value = true
  try {
    await unifiedApi.call('env.add', { descriptor })
    showSuccess(t('envs.added', { name: String(descriptor.name ?? '') }))
    addDialog.show = false
    await load(true)
  } catch (error) {
    addDialog.error = errMsg(error)
  } finally {
    adding.value = false
  }
}

function confirmDelete(env: EnvEntry) {
  dialog.warning({
    title: t('envs.deleteTitle'),
    content: t('envs.deleteContent', { env: envLabel(env) }),
    positiveText: t('tasks.actions.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      busy.value = `delete-${env.name}`
      try {
        await unifiedApi.call('env.delete', { name: env.name })
        showSuccess(t('envs.deleted', { env: envLabel(env) }))
        await load(true)
      } catch (error) {
        showError(t('envs.deleteFailed', { error: errMsg(error) }))
      } finally {
        busy.value = null
      }
    },
  })
}
</script>

<style scoped>
.envs-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  overflow-y: auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.page-title {
  margin: 0;
  font-family: Inter, sans-serif;
  font-size: 22px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.page-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--app-text-muted);
}

.envs-banner-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.envs-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.envs-grow {
  flex: 1;
}

.envs-hint {
  font-size: 11px;
  color: var(--app-text-dim);
}

.envs-status {
  font-size: 12px;
  color: var(--app-text-muted);
}

.envs-status-row {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.envs-empty {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  padding: 40px 20px;
  border: 1px dashed var(--app-card-border);
  border-radius: 10px;
}

.envs-empty-title {
  font-size: 14px;
  color: var(--app-text-secondary);
}

.envs-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.env-row {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 10px 14px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 8px;
}

.env-main {
  flex: 1;
  min-width: 0;
}

.env-head {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.env-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.env-dependents {
  font-size: 11px;
  color: var(--app-text-dim);
}

.env-path {
  margin-top: 3px;
  overflow: hidden;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 11px;
  color: var(--app-text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.env-override {
  margin-top: 2px;
  overflow: hidden;
  font-size: 11px;
  color: var(--app-orange, var(--app-yellow));
  text-overflow: ellipsis;
  white-space: nowrap;
}

.env-actions {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-shrink: 0;
}

.envs-json :deep(.n-input__textarea-el) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
}

.envs-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
