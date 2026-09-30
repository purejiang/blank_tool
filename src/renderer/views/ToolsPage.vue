<template>
  <!-- S6.1 工具页（docs/08 §3-S6.1）：工具描述符列表 + 环境依赖徽章 + 自定义路径。
       数据是 `tool.list`（含内置/插件/描述符）与 `tool.get_tools`
       （探测状态、实际路径）的合并。 -->
  <div class="screen tools-page">
    <PageHeader :title="t('tools.title')" :description="t('tools.subtitle')">
      <template #nav><ToolsSectionNav active="tools" /></template>
    </PageHeader>

    <div class="tools-toolbar">
      <!-- 导入只有一个入口、一种格式：压缩包（描述符放在压缩包根目录）。
           目录/单描述符不走界面——那是 CLI `import-pack` 的用法。 -->
      <n-button size="small" :loading="importing" @click="importPack">
        <template #icon><AppIcon name="folder-in" /></template>
        {{ t('tools.import') }}
      </n-button>
      <n-dropdown trigger="click" :options="searchModeOptions" @select="setSearchMode">
        <n-button size="small" quaternary>
          <template #icon><AppIcon name="search" /></template>
          {{ t('tools.systemSearch') }}
        </n-button>
      </n-dropdown>
    </div>

    <div class="tools-hint">{{ t('tools.searchModeHint') }}</div>

    <div v-if="loading && rows.length === 0" class="tools-status">{{ t('tools.loading') }}</div>
    <AppNotice v-else-if="loadError" tone="danger">
      {{ t('tools.loadFailed', { error: loadError }) }}
      <template #action>
        <AppButton variant="outline" size="tiny" @click="load(true)">{{ t('workflows.retry') }}</AppButton>
      </template>
    </AppNotice>
    <div v-else-if="rows.length === 0" class="tools-empty">
      <div class="tools-empty-title">{{ t('tools.empty.title') }}</div>
      <div class="tools-empty-hint">{{ t('tools.empty.hint') }}</div>
      <div class="tools-empty-actions">
        <n-button size="small" type="primary" :loading="importing" @click="importPack">
          {{ t('tools.import') }}
        </n-button>
      </div>
    </div>

    <div v-else-if="filtered.length === 0" class="tools-empty">
      <div class="tools-empty-title">{{ t('tools.noMatch') }}</div>
    </div>

    <div v-else class="tools-grid">
      <div v-for="row in filtered" :key="row.name" class="tool-card">
        <div class="tc-head">
          <span class="tc-icon" :class="`tc-icon--${row.sourceKey}`"><AppIcon :name="iconFor(row)" /></span>
          <span class="tc-name" :title="row.name">{{ row.name }}</span>
          <n-tag size="tiny" :bordered="false" :type="row.sourceKey === 'descriptor' ? 'warning' : 'default'">
            {{ t(`tools.source.${row.sourceKey}`) }}
          </n-tag>
          <n-tag v-if="!row.is_valid" size="tiny" :bordered="false" type="error">
            {{ t('tools.status.unavailable') }}
          </n-tag>
          <n-tag v-else size="tiny" :bordered="false" type="success">
            {{ t('tools.status.available') }}
          </n-tag>
        </div>

        <div v-if="row.description" class="tc-desc" :title="row.description">{{ row.description }}</div>

        <div class="tc-meta">
          <span v-if="row.version">v{{ row.version }}</span>
          <span v-if="row.operations > 0">{{ t('tools.operationCount', { count: row.operations }) }}</span>
          <span>{{ t('tools.portCount', { inputs: row.inputs, outputs: row.outputs }) }}</span>
        </div>

        <div v-if="row.path" class="tc-path" :title="row.path">{{ row.path }}</div>

        <!-- 环境依赖徽章行：只在该工具**确实声明过** env_deps 时出现（缺口 #18） -->
        <div v-if="row.envDeps.length > 0" class="tc-deps">
          <span
            v-for="dep in row.envDeps"
            :key="dep.name"
            class="tc-dep"
            :class="dep.ready ? 'tc-dep--ok' : 'tc-dep--missing'"
          >
            {{ dep.ready ? t('tools.dep.ready', { env: dep.label }) : t('tools.dep.missing', { env: dep.label }) }}
          </span>
        </div>

        <div class="app-actions">
          <AppButton variant="ghost" size="tiny" @click="toggleDetail(row.name)">
            {{ expanded.has(row.name) ? t('tools.hideDetail') : t('tools.showDetail') }}
          </AppButton>
          <AppButton
            variant="danger-ghost"
            size="tiny"
            :disabled="!canDeleteTool(row.kind)"
            :title="canDeleteTool(row.kind) ? '' : t('tools.deleteProtected')"
            :loading="busy === `delete-${row.name}`"
            @click="confirmDelete(row)"
          >
            {{ t('tasks.actions.delete') }}
          </AppButton>
        </div>

        <!-- 详情：端口与操作 -->
        <div v-if="expanded.has(row.name)" class="tc-detail">
          <div class="tc-detail-block">
            <div class="tc-detail-title">{{ t('tools.detail.inputs') }}</div>
            <div v-if="row.portList.inputs.length === 0" class="tc-detail-empty">—</div>
            <div v-for="port in row.portList.inputs" :key="`in-${port.name}`" class="tc-port">
              <code>{{ port.name }}</code>
              <span class="tc-port-type">{{ portTypeLabel(port) }}</span>
              <span v-if="port.direction === 'output'" class="tc-port-dir">{{ t('tools.detail.artifact') }}</span>
              <span v-if="port.required" class="tc-port-req">*</span>
              <span v-if="port.description" class="tc-port-desc">{{ port.description }}</span>
            </div>
          </div>
          <div class="tc-detail-block">
            <div class="tc-detail-title">{{ t('tools.detail.outputs') }}</div>
            <div v-if="row.portList.outputs.length === 0" class="tc-detail-empty">—</div>
            <div v-for="port in row.portList.outputs" :key="`out-${port.name}`" class="tc-port">
              <code>{{ port.name }}</code>
              <span class="tc-port-type">{{ portTypeLabel(port) }}</span>
            </div>
          </div>
          <div v-if="row.operationList.length > 0" class="tc-detail-block">
            <div class="tc-detail-title">{{ t('tools.detail.operations') }}</div>
            <div v-for="op in row.operationList" :key="op.name" class="tc-op">
              <code>{{ op.name }}</code>
              <span class="tc-port-desc">{{ op.description }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- M2 导入结果报告（与工作流导入共用） -->
    <ImportReportDialog
      v-model:show="reportDialog.show"
      :report="reportDialog.report"
      :title="reportDialog.title"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAlert, NButton, NDropdown, NTag, useDialog } from 'naive-ui'
import AppIcon from '@components/ui/AppIcon.vue'
import AppButton from '@components/ui/AppButton.vue'
import AppNotice from '@components/ui/AppNotice.vue'
import PageHeader from '@components/ui/PageHeader.vue'

import ToolsSectionNav from '@components/tools/ToolsSectionNav.vue'
import ImportReportDialog, {
  type ImportReport,
  type ImportReportEntry,
} from '@components/workflow/ImportReportDialog.vue'
import {
  canDeleteTool,
  toolEnvDeps,
  toolSourceOf,
  type ToolEnvDep,
  type ToolSourceKey,
} from '@components/tools/toolEnvDeps'
import { CATEGORY_ICONS, categoryOfToolName } from '@components/workflow/toolMeta'
import type {
  EnvEntry,
  PortJson,
  ToolEntry,
  ToolImportReport,
  ToolStatusEntry,
} from '../../shared/ipc/protocol'
import unifiedApi from '@/api/unifiedApi'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { log } from '@utils/logger'

/**
 * S6.1 — 工具描述符列表。
 *
 * 合并两个接口：`tool.list`（含内置与插件的全量 + 描述符的 `env_deps`
 * 与 ports/operations）与 `tool.get_tools`（探测出的实际路径与可用性），再用
 * `env.list` 本地 join 出依赖就绪状态。内置/插件工具没有 `env_deps`，因此它们
 * **不显示依赖行**（缺口 #18，不猜、不占位）。
 */

interface ToolRow {
  name: string
  kind: string
  sourceKey: ToolSourceKey
  is_valid: boolean
  version: string
  description: string
  path: string
  inputs: number
  outputs: number
  operations: number
  portList: { inputs: PortJson[]; outputs: PortJson[] }
  operationList: Array<{ name: string; description: string }>
  envDeps: ToolEnvDep[]
}

const { t } = useI18n()
const dialog = useDialog()
const { showSuccess, showError } = useNotification()

const tools = ref<ToolEntry[]>([])
const statuses = ref<Record<string, ToolStatusEntry>>({})
const envs = ref<EnvEntry[]>([])
const loading = ref(false)
const loadError = ref('')
const importing = ref(false)
const busy = ref<string | null>(null)
const expanded = ref(new Set<string>())

const reportDialog = reactive({ show: false, report: null as ImportReport | null, title: '' })

function errMsg(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function portTypeLabel(port: PortJson): string {
  const base = String(port.type?.base ?? '')
  const subtype = port.type?.subtype
  return subtype ? `${base}/${subtype}` : base
}

function iconFor(row: ToolRow): string {
  return CATEGORY_ICONS[categoryOfToolName(row.name)]
}

async function load(refresh = false) {
  loading.value = true
  loadError.value = ''
  try {
    const [toolList, statusList, envList] = await Promise.all([
      unifiedApi.call<{ tools?: ToolEntry[] }>('tool.list', {}),
      unifiedApi.call<Record<string, ToolStatusEntry>>('tool.get_tools', refresh ? { refresh: true } : {}),
      unifiedApi.call<{ environments?: EnvEntry[] }>('env.list'),
    ])
    tools.value = Array.isArray(toolList?.tools) ? toolList.tools : []
    statuses.value = statusList && typeof statusList === 'object' ? statusList : {}
    envs.value = Array.isArray(envList?.environments) ? envList.environments : []
  } catch (error) {
    log.error('[ToolsPage] loading tools failed:', error)
    loadError.value = errMsg(error)
    tools.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

const rows = computed<ToolRow[]>(() =>
  tools.value.map((tool) => {
    const status = statuses.value[tool.name]
    const operations = Array.isArray(tool.operations) ? tool.operations : []
    const inputs = Array.isArray(tool.ports?.inputs) ? tool.ports!.inputs : []
    const outputs = Array.isArray(tool.ports?.outputs) ? tool.ports!.outputs : []
    return {
      name: tool.name,
      kind: String(tool.kind ?? ''),
      sourceKey: toolSourceOf(tool.kind),
      is_valid: status ? status.is_valid !== false : tool.is_valid !== false,
      version: tool.version || status?.version || '',
      description: tool.description ?? '',
      path: status?.path || tool.tool_path || '',
      inputs: inputs.length,
      outputs: outputs.length,
      operations: operations.length,
      portList: { inputs, outputs },
      operationList: operations.map((op) => ({ name: op.name, description: op.description ?? '' })),
      envDeps: toolEnvDeps(tool, envs.value),
    }
  }),
)

const filtered = computed(() => rows.value)

function toggleDetail(name: string) {
  const next = new Set(expanded.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  expanded.value = next
}

// ---- 导入（只吃压缩包） -----------------------------------------------------

function toReport(report: Partial<ToolImportReport> & { updated?: number }): ImportReport {
  const results = Array.isArray(report?.results) ? (report.results as ImportReportEntry[]) : []
  return {
    ok: report?.ok !== false,
    imported: report?.imported ?? 0,
    failed: report?.failed ?? results.filter((entry) => entry.status === 'failed').length,
    updated: report?.updated ?? 0,
    results,
  }
}

/**
 * 只支持压缩包。后端 `tool.import_pack` 另外还认目录与单个 `*.json`
 * （CLI `import-pack` 在用），界面不暴露那两条路。
 */
async function importPack() {
  if (importing.value) return
  const svc = (await serviceManager.getService('system')) as any
  try {
    const picked = await svc.selectFile({
      title: t('tools.import'),
      properties: ['openFile'],
      filters: [{ name: 'ZIP', extensions: ['zip'] }],
    })
    if (!picked || picked.canceled) return
    const path = (picked.filePath || (picked.filePaths && picked.filePaths[0]) || '').trim()
    if (!path) return
    importing.value = true
    const report = await unifiedApi.call<ToolImportReport>('tool.import_pack', { path })
    reportDialog.report = toReport(report)
    reportDialog.title = t('tools.import')
    reportDialog.show = true
    await load()
  } catch (error) {
    showError(t('tools.importFailed', { error: errMsg(error) }))
  } finally {
    importing.value = false
  }
}

// ---- 系统 PATH 探测 ----------------------------------------------------------

/**
 * 后端只提供**写入**（`tool.set_search_mode {system_search}`），且该标志只存在于
 * 后端进程的环境变量里（重启回到默认关闭）——因此这里做成两个显式动作而不是
 * 一个"状态开关"，避免画出一个我们读不到的状态。
 */
const searchModeOptions = computed(() => [
  { label: t('tools.searchModeOn'), key: 'on' },
  { label: t('tools.searchModeOff'), key: 'off' },
])

async function setSearchMode(key: string) {
  try {
    await unifiedApi.call('tool.set_search_mode', { system_search: key === 'on' })
    showSuccess(key === 'on' ? t('tools.searchModeEnabled') : t('tools.searchModeDisabled'))
    await load(true)
  } catch (error) {
    showError(t('tools.searchModeFailed', { error: errMsg(error) }))
  }
}

// ---- 删除 --------------------------------------------------------------------

function confirmDelete(row: ToolRow) {
  dialog.warning({
    title: t('tools.deleteTitle'),
    content: t('tools.deleteContent', { name: row.name }),
    positiveText: t('tasks.actions.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      busy.value = `delete-${row.name}`
      try {
        await unifiedApi.call('tool.delete', { name: row.name })
        showSuccess(t('tools.deleted', { name: row.name }))
        await load()
      } catch (error) {
        showError(t('tools.deleteFailed', { error: errMsg(error) }))
      } finally {
        busy.value = null
      }
    },
  })
}
</script>

<style scoped>
/* 页面根不滚动（唯一滚动容器是外壳 .app-shell-content）——见 preview-layout.css */
.tools-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}




.tools-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.tools-hint {
  font-size: 11px;
  color: var(--app-text-dim);
}

.tools-status {
  font-size: 12px;
  color: var(--app-text-muted);
}

.tools-status-row {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.tools-empty {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  padding: 40px 20px;
  text-align: center;
  border: 1px dashed var(--app-card-border);
  border-radius: var(--radius-control);
}

.tools-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.tools-empty-hint {
  max-width: 560px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--app-text-muted);
}

.tools-empty-actions {
  display: flex;
  gap: 8px;
}

.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.tool-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-control);
}

.tc-head {
  display: flex;
  gap: 8px;
  align-items: center;
}

.tc-icon {
  display: inline-flex;
  flex-shrink: 0;
  color: var(--app-text-dim);
}

.tc-icon :deep(svg) {
  width: 14px;
  height: 14px;
}

.tc-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-family: var(--font-family-monospace);
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tc-desc {
  font-size: 12px;
  line-height: 1.5;
  color: var(--app-text-secondary);
}

.tc-meta {
  display: flex;
  gap: 10px;
  font-size: 11px;
  color: var(--app-text-dim);
}

.tc-path {
  overflow: hidden;
  font-size: 11px;
  color: var(--app-text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tc-deps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tc-dep {
  padding: 1px 7px;
  font-size: 11px;
  border-radius: var(--radius-chip);
}

.tc-dep--ok {
  color: var(--app-green);
  background: var(--app-green-bg, var(--app-storage-bg));
}

.tc-dep--missing {
  color: var(--app-orange, var(--app-yellow));
  background: var(--app-orange-bg, var(--app-storage-bg));
}

.tc-actions {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 2px;
}

.tc-detail {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--app-card-border);
}

.tc-detail-title {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--app-text-dim);
}

.tc-detail-empty {
  font-size: 11px;
  color: var(--app-text-muted);
}

.tc-port,
.tc-op {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 11px;
  color: var(--app-text-secondary);
}

.tc-port code,
.tc-op code {
  font-family: var(--font-family-monospace);
  color: var(--app-text-primary);
}

.tc-port-type {
  color: var(--app-text-dim);
}

.tc-port-dir {
  color: var(--app-purple, var(--app-text-dim));
}

.tc-port-req {
  color: var(--app-yellow);
}

.tc-port-desc {
  min-width: 0;
  overflow: hidden;
  color: var(--app-text-dim);
  text-overflow: ellipsis;
}
</style>
