<template>
  <!-- S1 工作流列表（docs/08 §3-S1，版式取自 docs/ui-prompts/ui-preview.html 第 4 节）：
       页面头 → 工具栏 → 3 列卡片网格 / 空态。本页不与 history.list join，
       卡片上没有运行状态徽章。 -->
  <div class="screen">
    <PageHeader :title="t('workflows.title')" :description="t('workflows.subtitle')" />

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
           卡片 ⋯ 菜单里也有单卡导出。下拉的 value 是工作流 id（显示名可重复）。 -->
      <n-dropdown
        trigger="click"
        :options="exportOptions"
        :disabled="workflows.length === 0"
        @select="(id: string) => exportById(id)"
      >
        <n-button size="small" :disabled="workflows.length === 0" :title="t('workflows.export.empty')">
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
    <div v-if="loading && workflows.length === 0" class="wf-grid">
      <div v-for="n in 6" :key="n" class="card wf-card">
        <n-skeleton text :repeat="3" />
      </div>
    </div>

    <!-- 空态：无工作流 -->
    <div v-else-if="workflows.length === 0" class="empty">
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
        v-for="workflow in filtered"
        :key="workflow.id"
        class="card wf-card"
        @click="openEditor(workflow.id)"
      >
        <h3 :title="workflow.name">{{ workflow.name }}</h3>
        <p class="desc">{{ workflow.description || t('workflows.card.noDescription') }}</p>
        <div class="meta">
          {{ t('workflows.card.nodes', { count: workflow.node_count }) }} ·
          {{ t('workflows.card.updated', { time: formatTime(workflow.updated_at) }) }}
        </div>
        <div class="foot">
          <div class="chips">
            <span v-for="tag in workflow.tags ?? []" :key="tag" class="tag">{{ tag }}</span>
          </div>
        </div>
        <span class="iconbtn wf-more" :title="t('workflows.card.menu')" @click.stop>
          <n-dropdown
            trigger="click"
            :options="cardMenu(workflow)"
            @select="(key: string) => onCardAction(key, workflow)"
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
            {{ t('workflow.editor.actions.cancel') }}
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
import PageHeader from '@components/ui/PageHeader.vue'

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

/**
 * One `workflow.list` entry.
 *
 * `id` is the storage identity (also the `<id>.json` file name) and the key
 * every action uses; `name` is the free-form display name, which may repeat.
 */
interface WorkflowInfo {
  id: string
  name: string
  description: string
  created_at: string | null
  updated_at: string | null
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

const workflows = ref<WorkflowInfo[]>([])
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
    const result = await unifiedApi.call<{ workflows?: WorkflowInfo[] }>('workflow.list', {})
    workflows.value = Array.isArray(result?.workflows) ? result.workflows : []
  } catch (error) {
    log.error('[WorkflowsListPage] workflow.list failed:', error)
    loadError.value = errMsg(error)
    workflows.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  if (isHealthy.value === null) void health.check()
})

// ---- 搜索（前端过滤 id / name / description / tags） ----------------------

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return workflows.value
  return workflows.value.filter(
    (workflow) =>
      workflow.id.toLowerCase().includes(needle) ||
      workflow.name.toLowerCase().includes(needle) ||
      (workflow.description ?? '').toLowerCase().includes(needle) ||
      (workflow.tags ?? []).some((tag) => String(tag).toLowerCase().includes(needle)),
  )
})

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

// ---- 卡片菜单 / 工具栏导出 --------------------------------------------------

function cardMenu(workflow: WorkflowInfo) {
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

// 下拉的 key 必须是 id：显示名可以重复，用名字当下拉键会选错目标。
const exportOptions = computed(() =>
  workflows.value.map((workflow) => ({ label: workflow.name, key: workflow.id })),
)

function onCardAction(key: string, workflow: WorkflowInfo) {
  if (key === 'edit') return openEditor(workflow.id)
  if (key === 'run') return openRunDialog(workflow)
  if (key === 'duplicate') return openNameDialog('duplicate', workflow)
  if (key === 'rename') return openNameDialog('rename', workflow)
  if (key === 'export') return void exportWorkflow(workflow.id, workflow.name)
  if (key === 'delete') return confirmDelete(workflow)
}

function openEditor(id?: string) {
  router.push(id ? `/workflows/editor/${encodeURIComponent(id)}` : '/workflows/editor')
}

// ---- 导入（M2 报告） --------------------------------------------------------

/**
 * 只按 JSON 文件导入（可多选）→ `workflow.import_path`（逐路径调用后合并报告）。
 *
 * 后端 `workflow.import_path` 另外还认目录（CLI `import-workflows` 在用），
 * 界面不暴露那条路；取消文件对话框就是取消，不再接着弹一个目录选择器。
 */
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
    if (!picked || picked.canceled) return
    paths = (picked.filePaths ?? []).filter((path: string) => !!path)
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
        const report = await unifiedApi.call<Partial<ImportReport>>('workflow.import_path', { path })
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

/**
 * 导出的是**可移植的纯定义**（不含存储 id）：导入时按显示名匹配、重新分配 id，
 * 所以中文名只会出现在用户自己选的文件名里。
 */
async function exportWorkflow(id: string, displayName: string) {
  try {
    const loaded = await unifiedApi.call<{ definition?: WorkflowDefinitionJSON }>('workflow.load', { id })
    const definition = loaded?.definition
    if (!definition) throw new Error(`workflow “${id}” returned no definition`)
    const svc = (await serviceManager.getService('system')) as any
    const picked = await svc.showSave({
      title: t('workflows.export.saveTitle'),
      // 显示名现在可以是任意字符（含 \ / :），导出文件名单独清洗一次。
      defaultPath: `${safeFileName(displayName) || id}.json`,
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

/** 把显示名压成一个可作文件名的字符串（仅用于导出对话框的默认名）。 */
function safeFileName(name: string): string {
  return String(name ?? '')
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80)
}

/** 工具栏下拉只回传 id；显示名从当前列表取，仅用于导出默认文件名。 */
function exportById(id: string) {
  const workflow = workflows.value.find((item) => item.id === id)
  return exportWorkflow(id, workflow?.name ?? id)
}

// ---- 复制 / 重命名 ----------------------------------------------------------

const nameDialog = reactive({
  show: false,
  mode: 'duplicate' as 'duplicate' | 'rename',
  target: null as WorkflowInfo | null,
  value: '',
  error: null as string | null,
  busy: false,
})

function openNameDialog(mode: 'duplicate' | 'rename', workflow: WorkflowInfo) {
  nameDialog.mode = mode
  nameDialog.target = workflow
  nameDialog.value = mode === 'duplicate' ? `${workflow.name}-copy` : workflow.name
  nameDialog.error = null
  nameDialog.busy = false
  nameDialog.show = true
}

/**
 * 名字不再是身份、也不再是文件名，所以这里只要求"非空"——`/`、`:`、emoji、
 * Windows 保留字都能用（写进的是定义内部，不落盘成文件名）。
 */
function validateName(value: string): string | null {
  const name = value.trim()
  if (!name) return t('workflows.nameDialog.nameRequired')
  return null
}

async function submitNameDialog() {
  const workflow = nameDialog.target
  if (!workflow || nameDialog.busy) return
  const error = validateName(nameDialog.value)
  if (error) {
    nameDialog.error = error
    return
  }
  const newName = nameDialog.value.trim()
  // id 才是身份，所以撞名不再是"整份覆盖"：两个工作流可以同名，只提示一下。
  const clash = workflows.value.find(
    (item) => item.id !== workflow.id && item.name.toLowerCase() === newName.toLowerCase(),
  )
  if (clash) {
    dialog.warning({
      title: t('workflows.nameDialog.duplicateNameTitle'),
      content: t('workflows.nameDialog.duplicateNameContent', { name: clash.name }),
      positiveText: t('workflows.nameDialog.duplicateNameConfirm'),
      negativeText: t('common.cancel'),
      onPositiveClick: () => void applyNameDialog(newName, workflow),
    })
    return
  }
  await applyNameDialog(newName, workflow)
}

/**
 * 真正落盘。
 *
 * - 复制：不带 id 保存 → 后端分配一个新 id（新工作流），原名那份原封不动。
 * - 重命名：带**同一个 id** 保存 → 只改文件里的显示名，文件名（id）不变，
 *   因此绑定的任务与子工作流引用都不会断。
 */
async function applyNameDialog(newName: string, workflow: WorkflowInfo) {
  nameDialog.busy = true
  try {
    const loaded = await unifiedApi.call<{
      definition?: WorkflowDefinitionJSON
      description?: string
      tags?: string[]
    }>('workflow.load', { id: workflow.id })
    const definition = loaded?.definition
    if (!definition) throw new Error(`workflow “${workflow.id}” returned no definition`)

    await unifiedApi.call('workflow.save', {
      id: nameDialog.mode === 'rename' ? workflow.id : undefined,
      name: newName,
      definition: { ...definition, name: newName },
      description: loaded?.description ?? workflow.description ?? '',
      tags: Array.isArray(loaded?.tags) ? loaded.tags : (workflow.tags ?? []),
    })
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

function confirmDelete(workflow: WorkflowInfo) {
  dialog.warning({
    title: t('workflows.delete.title'),
    content: t('workflows.delete.content', { name: workflow.name }),
    positiveText: t('workflows.actions.delete'),
    negativeText: t('workflow.editor.actions.cancel'),
    onPositiveClick: async () => {
      try {
        await unifiedApi.call('workflow.delete', { id: workflow.id })
        await load()
      } catch (error) {
        showError(t('workflows.delete.failed', { error: errMsg(error) }))
      }
    },
  })
}

// ---- 试运行（一次性 workflow.execute） --------------------------------------

const runDialog = reactive({
  show: false,
  title: '',
  id: '',
  name: '',
  definition: null as WorkflowDefinitionJSON | null,
})

async function openRunDialog(workflow: WorkflowInfo) {
  try {
    const loaded = await unifiedApi.call<{ definition?: WorkflowDefinitionJSON }>('workflow.load', {
      id: workflow.id,
    })
    runDialog.definition = loaded?.definition ?? null
    runDialog.id = workflow.id
    runDialog.name = workflow.name
    runDialog.title = `${workflow.name} · ${t('workflows.actions.run')}`
    runDialog.show = true
  } catch (error) {
    showError(t('workflows.run.launchFailed', { error: errMsg(error) }))
  }
}

async function startDryRun(inputs: Record<string, unknown>) {
  const id = runDialog.id
  const name = runDialog.name
  runDialog.show = false
  try {
    const outcome = await startWorkflowRun({
      method: 'workflow.execute',
      // 按 id 跑：显示名可以重复，按名字跑可能命中另一个工作流。
      params: { id, inputs },
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
