<template>
  <!-- S1 工作流列表（docs/08 §3-S1，版式取自 docs/ui-prompts/ui-preview.html 第 4 节）：
       页面头 → 工具栏 → 3 列卡片网格 / 空态。本页不与 history.list join，
       卡片上没有运行状态徽章。 -->
  <div class="screen">
    <div class="page-hd">
      <h1>{{ t('workflows.title') }}</h1>
      <p>{{ t('workflows.subtitle') }}</p>
    </div>

    <div class="toolbar">
      <n-button type="primary" size="small" @click="openEditor()">
        <template #icon><AppIcon name="plus" size="sm" /></template>
        {{ t('workflows.new') }}
      </n-button>
      <n-button size="small" :loading="importing" @click="handleImport">
        <template #icon><AppIcon name="folder-in" size="sm" /></template>
        {{ t('workflows.importLabel') }}
      </n-button>
      <!-- 设计稿的工具栏导出是普通按钮、卡片上没有勾选框：这里用名称下拉选定目标，
           卡片 ⋯ 菜单里也有单卡导出。 -->
      <n-dropdown
        trigger="click"
        :options="exportOptions"
        :disabled="templates.length === 0"
        @select="(name: string) => exportTemplate(name)"
      >
        <n-button size="small" :disabled="templates.length === 0" :title="t('workflows.export.empty')">
          <template #icon><AppIcon name="download" size="sm" /></template>
          {{ t('workflows.exportLabel') }}
        </n-button>
      </n-dropdown>
      <div class="grow">
        <label class="search">
          <AppIcon name="search" size="sm" />
          <n-input v-model:value="query" size="small" :placeholder="t('workflows.search')" />
        </label>
      </div>
      <div class="btns">
        <button type="button" class="iconbtn boxed" :title="t('workflows.refresh')" @click="load()">
          <AppIcon name="refresh" />
        </button>
      </div>
    </div>

    <div v-if="backendDown" class="notice">
      <AppIcon name="alert" />
      <span class="grow">{{ t('workflows.backendUnavailable') }}</span>
    </div>
    <div v-if="loadError" class="notice err">
      <AppIcon name="alert" />
      <span class="grow">{{ t('workflows.loadFailed', { error: loadError }) }}</span>
      <button type="button" class="btn" @click="load()">{{ t('workflows.retry') }}</button>
    </div>

    <!-- 加载中：骨架卡片 -->
    <div v-if="loading && templates.length === 0" class="wf-grid">
      <div v-for="n in 6" :key="n" class="card wf-card">
        <n-skeleton text :repeat="3" />
      </div>
    </div>

    <!-- 空态：无工作流 -->
    <div v-else-if="templates.length === 0" class="empty">
      <div class="art"><AppIcon name="wf" :size="34" /></div>
      <h3>{{ t('workflows.empty.title') }}</h3>
      <p>{{ t('workflows.empty.hint') }}</p>
      <div class="acts">
        <n-button size="small" :loading="importing" @click="handleImport">
          <template #icon><AppIcon name="folder-in" size="sm" /></template>
          {{ t('workflows.empty.importSamples') }}
        </n-button>
        <n-button size="small" type="primary" @click="openEditor()">
          <template #icon><AppIcon name="plus" size="sm" /></template>
          {{ t('workflows.empty.create') }}
        </n-button>
      </div>
    </div>

    <!-- 空态：搜索无命中 -->
    <div v-else-if="filtered.length === 0" class="empty">
      <h3>{{ t('workflows.noMatch') }}</h3>
    </div>

    <div v-else class="wf-grid">
      <div
        v-for="template in filtered"
        :key="template.name"
        class="card wf-card"
        @click="openEditor(template.name)"
      >
        <h3 :title="template.name">{{ template.name }}</h3>
        <p class="desc">{{ template.description || t('workflows.card.noDescription') }}</p>
        <div class="meta">
          {{ t('workflows.card.nodes', { count: template.node_count }) }} ·
          {{ t('workflows.card.updated', { time: formatTime(template.updated_at) }) }}
        </div>
        <div class="foot">
          <div class="chips">
            <span v-for="tag in template.tags ?? []" :key="tag" class="tag">{{ tag }}</span>
          </div>
        </div>
        <span class="iconbtn wf-more" :title="t('workflows.card.menu')" @click.stop>
          <n-dropdown
            trigger="click"
            :options="cardMenu(template)"
            @select="(key: string) => onCardAction(key, template)"
          >
            <AppIcon name="more" />
          </n-dropdown>
        </span>
      </div>
    </div>

    <!-- 复制 / 重命名：一个名称输入对话框 -->
    <n-modal
      v-model:show="nameDialog.show"
      preset="card"
      :title="nameDialog.mode === 'duplicate' ? t('workflows.nameDialog.duplicateTitle') : t('workflows.nameDialog.renameTitle')"
      :style="{ width: '420px' }"
      :mask-closable="!nameDialog.busy"
    >
      <n-form label-placement="top" size="small">
        <n-form-item
          :label="t('workflows.nameDialog.name')"
          required
          :validation-status="nameDialog.error ? 'error' : undefined"
          :feedback="nameDialog.error ?? undefined"
        >
          <n-input v-model:value="nameDialog.value" :disabled="nameDialog.busy" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="wf-dialog-footer">
          <n-button size="small" :disabled="nameDialog.busy" @click="nameDialog.show = false">
            {{ t('workflow.editor.template.cancel') }}
          </n-button>
          <n-button size="small" type="primary" :loading="nameDialog.busy" @click="submitNameDialog">
            {{ t('workflows.nameDialog.confirm') }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <!-- M1 输入表单（试运行） -->
    <RunInputsDialog
      v-model:show="runDialog.show"
      :definition="runDialog.definition"
      :title="runDialog.title"
      :loading="runInFlight"
      @submit="startDryRun"
    />

    <!-- M2 导入结果报告 -->
    <ImportReportDialog
      v-model:show="reportDialog.show"
      :report="reportDialog.report"
      :title="t('workflows.import.title')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useDialog } from 'naive-ui'
import { NDropdown, NForm, NFormItem, NInput, NModal, NSkeleton, NButton } from 'naive-ui'
import AppIcon from '@components/ui/AppIcon.vue'

import RunInputsDialog from '@components/workflow/RunInputsDialog.vue'
import ImportReportDialog, {
  type ImportReport,
  type ImportReportEntry,
} from '@components/workflow/ImportReportDialog.vue'
import type { WorkflowDefinitionJSON } from '@components/workflow/serializer'
import { useWorkflowRun } from '@composables/useWorkflowRun'
import { useNotification } from '@composables/useNotification'
import { useBackendHealthStore } from '@stores/backendHealthStore'
import serviceManager from '@services/ServiceManager'
import unifiedApi from '@/api/unifiedApi'
import { log } from '@utils/logger'

/** One `template.list` entry. */
interface TemplateInfo {
  name: string
  description: string
  created_at: string
  updated_at: string
  tags: string[]
  node_count: number
}

const { t } = useI18n()
const router = useRouter()
const dialog = useDialog()
const { showSuccess, showError, showWarning } = useNotification()
const health = useBackendHealthStore()
const { isHealthy } = storeToRefs(health)
const { isRunning: runInFlight, start: startWorkflowRun } = useWorkflowRun()

const templates = ref<TemplateInfo[]>([])
const loading = ref(false)
const loadError = ref('')
const importing = ref(false)
const query = ref('')

const backendDown = computed(() => isHealthy.value === false)

function errMsg(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const result = await unifiedApi.call<{ templates?: TemplateInfo[] }>('template.list', {})
    templates.value = Array.isArray(result?.templates) ? result.templates : []
  } catch (error) {
    log.error('[WorkflowsListPage] template.list failed:', error)
    loadError.value = errMsg(error)
    templates.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  if (isHealthy.value === null) void health.check()
})

// ---- 搜索（前端过滤 name / description / tags） ---------------------------

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return templates.value
  return templates.value.filter(
    (template) =>
      template.name.toLowerCase().includes(needle) ||
      (template.description ?? '').toLowerCase().includes(needle) ||
      (template.tags ?? []).some((tag) => String(tag).toLowerCase().includes(needle)),
  )
})

function formatTime(iso: string): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

// ---- 卡片菜单 / 工具栏导出 --------------------------------------------------

function cardMenu(template: TemplateInfo) {
  return [
    { label: t('workflows.actions.edit'), key: 'edit' },
    { label: t('workflows.actions.run'), key: 'run' },
    { label: t('workflows.actions.duplicate'), key: 'duplicate' },
    { label: t('workflows.actions.rename'), key: 'rename' },
    { label: t('workflows.actions.export'), key: 'export' },
    { type: 'divider', key: 'd1' },
    { label: t('workflows.actions.delete'), key: 'delete' },
  ]
}

const exportOptions = computed(() =>
  templates.value.map((template) => ({ label: template.name, key: template.name })),
)

function onCardAction(key: string, template: TemplateInfo) {
  if (key === 'edit') return openEditor(template.name)
  if (key === 'run') return openRunDialog(template)
  if (key === 'duplicate') return openNameDialog('duplicate', template)
  if (key === 'rename') return openNameDialog('rename', template)
  if (key === 'export') return void exportTemplate(template.name)
  if (key === 'delete') return confirmDelete(template)
}

function openEditor(name?: string) {
  router.push(name ? `/workflows/editor/${encodeURIComponent(name)}` : '/workflows/editor')
}

// ---- 导入（M2 报告） --------------------------------------------------------

/** 文件多选或目录选择 → `template.import_path`（逐路径调用后合并报告）。 */
async function handleImport() {
  if (importing.value) return
  const svc = (await serviceManager.getService('system')) as any
  let paths: string[] = []
  try {
    const picked = await svc.selectFile({
      title: t('workflows.import.title'),
      properties: ['openFile', 'multiSelections'],
      filters: [{ name: 'JSON', extensions: ['json'] }],
    })
    if (picked && !picked.canceled) {
      paths = (picked.filePaths ?? []).filter((path: string) => !!path)
    }
    if (paths.length === 0) {
      // 没选文件 → 让用户选一个包含工作流 JSON 的目录
      const dir = await svc.selectDirectory({ title: t('workflows.import.title') })
      if (dir && !dir.canceled) {
        const single = (dir.filePath || (dir.filePaths && dir.filePaths[0]) || '').trim()
        if (single) paths = [single]
      }
    }
  } catch (error) {
    showError(t('workflows.import.failed', { error: errMsg(error) }))
    return
  }

  if (paths.length === 0) {
    showWarning(t('workflows.import.none'))
    return
  }

  importing.value = true
  const results: ImportReportEntry[] = []
  let imported = 0
  let failed = 0
  try {
    for (const path of paths) {
      try {
        const report = await unifiedApi.call<Partial<ImportReport>>('template.import_path', { path })
        const entries = Array.isArray(report?.results) ? (report.results as ImportReportEntry[]) : []
        results.push(...entries)
        imported += report?.imported ?? entries.filter((entry) => entry.status === 'imported').length
        failed += report?.failed ?? entries.filter((entry) => entry.status !== 'imported').length
      } catch (error) {
        failed += 1
        results.push({ status: 'failed', file: path, reason: errMsg(error) })
      }
    }
    reportDialog.report = { ok: failed === 0, imported, failed, results }
    reportDialog.show = true
    if (failed === 0) showSuccess(t('workflows.import.imported', { count: imported }))
    else showWarning(t('workflows.import.importedPartial', { ok: imported, failed }))
    await load()
  } finally {
    importing.value = false
  }
}

// ---- 导出（M3：showSave + writeTextFile） -----------------------------------

async function exportTemplate(name: string) {
  try {
    const loaded = await unifiedApi.call<{ definition?: WorkflowDefinitionJSON }>('template.load', { name })
    const definition = loaded?.definition
    if (!definition) throw new Error(`template “${name}” returned no definition`)
    const svc = (await serviceManager.getService('system')) as any
    const picked = await svc.showSave({
      title: t('workflows.export.saveTitle'),
      defaultPath: `${name}.json`,
      filters: [{ name: 'JSON', extensions: ['json'] }],
    })
    if (!picked || picked.canceled) return
    const target = (picked.filePath || (picked.filePaths && picked.filePaths[0]) || '').trim()
    if (!target) return
    const written = await svc.writeTextFile(target, `${JSON.stringify(definition, null, 2)}\n`)
    if (written && written.success === false) throw new Error(written.error || 'write failed')
    showSuccess(t('workflows.export.saved', { path: target }))
  } catch (error) {
    log.error('[WorkflowsListPage] export failed:', error)
    showError(t('workflows.export.failed', { error: errMsg(error) }))
  }
}

// ---- 复制 / 重命名 ----------------------------------------------------------

const nameDialog = reactive({
  show: false,
  mode: 'duplicate' as 'duplicate' | 'rename',
  target: null as TemplateInfo | null,
  value: '',
  error: null as string | null,
  busy: false,
})

function openNameDialog(mode: 'duplicate' | 'rename', template: TemplateInfo) {
  nameDialog.mode = mode
  nameDialog.target = template
  nameDialog.value = mode === 'duplicate' ? `${template.name}-copy` : template.name
  nameDialog.error = null
  nameDialog.busy = false
  nameDialog.show = true
}

function validateName(value: string): string | null {
  const name = value.trim()
  if (!name) return t('workflows.nameDialog.nameRequired')
  if (/[\\/:]/.test(name)) return t('workflows.nameDialog.invalid')
  return null
}

async function submitNameDialog() {
  const template = nameDialog.target
  if (!template || nameDialog.busy) return
  const error = validateName(nameDialog.value)
  if (error) {
    nameDialog.error = error
    return
  }
  const newName = nameDialog.value.trim()
  nameDialog.busy = true
  try {
    const loaded = await unifiedApi.call<{
      definition?: WorkflowDefinitionJSON
      description?: string
      tags?: string[]
    }>('template.load', { name: template.name })
    const definition = loaded?.definition
    if (!definition) throw new Error(`template “${template.name}” returned no definition`)

    await unifiedApi.call('template.save', {
      name: newName,
      definition: { ...definition, name: newName },
      description: loaded?.description ?? template.description ?? '',
      tags: Array.isArray(loaded?.tags) ? loaded.tags : (template.tags ?? []),
    })
    if (nameDialog.mode === 'rename' && newName !== template.name) {
      // 重命名 = 存新名 + 删旧名（docs/08 §3-S1 交互）
      await unifiedApi.call('template.delete', { name: template.name })
    }
    nameDialog.show = false
    await load()
  } catch (err) {
    log.error('[WorkflowsListPage] name dialog failed:', err)
    nameDialog.error = errMsg(err)
  } finally {
    nameDialog.busy = false
  }
}

// ---- 删除（M4 确认） --------------------------------------------------------

function confirmDelete(template: TemplateInfo) {
  dialog.warning({
    title: t('workflows.delete.title'),
    content: t('workflows.delete.content', { name: template.name }),
    positiveText: t('workflows.actions.delete'),
    negativeText: t('workflow.editor.template.cancel'),
    onPositiveClick: async () => {
      try {
        await unifiedApi.call('template.delete', { name: template.name })
        await load()
      } catch (error) {
        showError(t('workflows.delete.failed', { error: errMsg(error) }))
      }
    },
  })
}

// ---- 试运行（M1 + template.execute 一次性） ---------------------------------

const runDialog = reactive({
  show: false,
  title: '',
  name: '',
  definition: null as WorkflowDefinitionJSON | null,
})

async function openRunDialog(template: TemplateInfo) {
  try {
    const loaded = await unifiedApi.call<{ definition?: WorkflowDefinitionJSON }>('template.load', {
      name: template.name,
    })
    runDialog.definition = loaded?.definition ?? null
    runDialog.name = template.name
    runDialog.title = `${template.name} · ${t('workflows.actions.run')}`
    runDialog.show = true
  } catch (error) {
    showError(t('workflows.run.launchFailed', { error: errMsg(error) }))
  }
}

async function startDryRun(inputs: Record<string, unknown>) {
  const name = runDialog.name
  runDialog.show = false
  try {
    const outcome = await startWorkflowRun({
      method: 'template.execute',
      params: { name, inputs },
    })
    if (!outcome) {
      // 事件通道不可用时无法关联终态：不谎报结果，只提示已启动
      showWarning(t('workflows.run.launchFailed', { error: 'stream unavailable' }))
      return
    }
    if (outcome.status === 'success') showSuccess(t('workflows.run.success', { name }))
    else if (outcome.status === 'cancelled') showWarning(t('workflows.run.cancelled', { name }))
    else showError(t('workflows.run.failed', { name }), outcome.error ?? '')
  } catch (error) {
    showError(t('workflows.run.launchFailed', { error: errMsg(error) }))
  }
}

// ---- 弹层状态 ---------------------------------------------------------------

const reportDialog = reactive({ show: false, report: null as ImportReport | null })
</script>

<style scoped>
.wf-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
