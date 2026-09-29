<template>
  <!-- S3.2 任务编辑（docs/08 §3-S3.2）：主体是**入参的持久化表单**；工作流只是
       "入参 schema 来源 + 运行目标"，只占顶部一行紧凑选择器，不占侧栏。 -->
  <div class="screen task-editor">
    <div class="page-header">
      <n-button size="small" quaternary :title="t('workflow.editor.back')" @click="goBack">
        <template #icon><AppIcon name="back" /></template>
      </n-button>
      <h1 class="page-title">{{ isNew ? t('tasks.editor.createTitle') : t('tasks.editor.editTitle') }}</h1>
      <span class="page-grow" />
      <n-button v-if="!isNew" size="small" type="error" quaternary @click="removeTask">
        {{ t('tasks.actions.delete') }}
      </n-button>
    </div>

    <!-- 基本信息一行 -->
    <div class="te-row">
      <div class="te-field">
        <label class="te-label">{{ t('tasks.editor.name') }} <span class="te-req">*</span></label>
        <n-input
          v-model:value="form.name"
          size="small"
          :disabled="saving"
          :placeholder="t('tasks.editor.namePlaceholder')"
          @update:value="nameError = null"
        />
        <div v-if="nameError" class="te-error">{{ nameError }}</div>
      </div>
      <div class="te-field te-field--wide">
        <label class="te-label">{{ t('tasks.editor.description') }}</label>
        <n-input
          v-model:value="form.description"
          size="small"
          :disabled="saving"
          :placeholder="t('tasks.editor.descriptionPlaceholder')"
        />
      </div>
    </div>

    <!-- 工作流一行（紧凑：可搜索选择 + 描述 + 打开工作流） -->
    <div class="te-workflow">
      <label class="te-label">{{ t('tasks.editor.workflow') }} <span class="te-req">*</span></label>
      <n-select
        v-model:value="form.workflow"
        size="small"
        filterable
        class="te-workflow-select"
        :disabled="saving"
        :options="workflowOptions"
        :placeholder="t('tasks.editor.workflowPlaceholder')"
        @update:value="onWorkflowChange"
      />
      <span v-if="workflowDescription" class="te-workflow-desc" :title="workflowDescription">
        {{ workflowDescription }}
      </span>
      <n-button size="small" quaternary :disabled="!form.workflow" @click="openWorkflow">
        {{ t('tasks.editor.openWorkflow') }}
      </n-button>
    </div>

    <n-alert v-if="workflowMissing" type="warning" :show-icon="true">
      {{ t('tasks.editor.workflowMissingHint', { workflow: form.workflow }) }}
    </n-alert>

    <!-- 入参表单：两列网格，路径 / JSON 整行 -->
    <div v-if="!form.workflow" class="te-placeholder">{{ t('tasks.editor.pickWorkflowFirst') }}</div>
    <div v-else-if="loadingDefinition" class="te-placeholder">{{ t('tasks.editor.loadingDefinition') }}</div>
    <div v-else-if="ports.length === 0" class="te-placeholder">{{ t('tasks.editor.noInputs') }}</div>
    <div v-else class="te-fields">
      <div
        v-for="port in ports"
        :key="port.name"
        class="te-field te-port-field"
        :class="{ 'te-port-field--full': isWidePort(port) }"
      >
        <label class="te-label">
          {{ port.name }}
          <span v-if="port.required !== false" class="te-req">*</span>
        </label>
        <!-- 任务页入参是持久化字面量：不提供表达式绑定（与 S1 试运行一致） -->
        <PortInput
          :value="inputs[port.name]"
          :port="port"
          :allow-bindings="false"
          :disabled="saving"
          @update:value="(value: any) => (inputs[port.name] = value)"
        />
        <div v-if="port.description" class="te-help">{{ port.description }}</div>
        <div v-if="fieldErrors[port.name]" class="te-error">{{ fieldErrors[port.name] }}</div>
      </div>
    </div>

    <!-- 底部固定操作条 -->
    <div class="te-footer">
      <div class="te-field te-workdir">
        <label class="te-label">{{ t('tasks.editor.workDir') }}</label>
        <div class="te-workdir-row">
          <n-input
            v-model:value="form.work_dir"
            size="small"
            class="te-workdir-input"
            :disabled="saving"
            :placeholder="t('tasks.editor.workDirPlaceholder')"
          />
          <n-button size="small" :disabled="saving" @click="browseWorkDir">
            {{ t('workflow.editor.dialog.browse') }}
          </n-button>
        </div>
      </div>
      <div class="te-footer-actions">
        <n-button size="small" :disabled="saving" @click="goBack">
          {{ t('workflow.editor.template.cancel') }}
        </n-button>
        <n-button size="small" :disabled="saving || workflowMissing" :loading="saving" @click="save(false)">
          {{ t('tasks.editor.save') }}
        </n-button>
        <n-button
          size="small"
          type="primary"
          :disabled="saving || workflowMissing"
          :loading="savingAndRunning"
          @click="save(true)"
        >
          {{ t('tasks.editor.saveAndRun') }}
        </n-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NAlert, NButton, NInput, NSelect, useDialog } from 'naive-ui'
import AppIcon from '@components/ui/AppIcon.vue'

import PortInput from '@components/workflow/PortInput.vue'
import type { PortJSON, WorkflowDefinitionJSON } from '@components/workflow/serializer'
import type { TaskGetResult } from '../../shared/ipc/protocol'
import unifiedApi from '@/api/unifiedApi'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { log } from '@utils/logger'

/**
 * S3.2 — the ONLY place a task is edited: pick a workflow, fill its inputs and
 * save them (docs/08 §3-S3 模型口径).
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const dialog = useDialog()
const { showSuccess, showError } = useNotification()

const nameFromRoute = computed(() =>
  typeof route.params.name === 'string' && route.params.name ? decodeURIComponent(route.params.name) : '',
)
const isNew = computed(() => !nameFromRoute.value)

const form = reactive({ name: '', description: '', workflow: '', work_dir: '' })
const inputs = reactive<Record<string, any>>({})
const ports = ref<PortJSON[]>([])
const workflowOptions = ref<Array<{ label: string; value: string }>>([])
const workflowDescriptions = ref<Record<string, string>>({})
const workflowMissing = ref(false)
/** 上一次成功装载过定义的工作流，用于「取消改绑」时回退选择器。 */
const appliedWorkflow = ref('')

const loadingDefinition = ref(false)
const saving = ref(false)
const savingAndRunning = ref(false)
const nameError = ref<string | null>(null)
const fieldErrors = reactive<Record<string, string>>({})

const workflowDescription = computed(() => workflowDescriptions.value[form.workflow] ?? '')

function errMsg(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

// ---- 工作流选择器 -----------------------------------------------------------

async function loadWorkflows() {
  try {
    const result = await unifiedApi.call<{
      templates?: Array<{ name: string; description: string; node_count: number }>
    }>('template.list', {})
    const templates = Array.isArray(result?.templates) ? result.templates : []
    workflowOptions.value = templates.map((template) => ({
      label: `${template.name} · ${t('workflows.card.nodes', { count: template.node_count })}`,
      value: template.name,
    }))
    workflowDescriptions.value = Object.fromEntries(
      templates.map((template) => [template.name, template.description ?? '']),
    )
  } catch (error) {
    log.error('[TaskEditorPage] template.list failed:', error)
    workflowOptions.value = []
  }
}

/** 按工作流定义重建入参表单；按端口名保留已有值（docs/08 §3-S3.2 改绑口径）。 */
async function loadDefinition(workflow: string) {
  if (!workflow) {
    ports.value = []
    return
  }
  loadingDefinition.value = true
  try {
    const result = await unifiedApi.call<{ definition?: WorkflowDefinitionJSON }>('template.load', {
      name: workflow,
    })
    const declared = Array.isArray(result?.definition?.inputs) ? result.definition!.inputs! : []
    ports.value = declared.filter(
      (port): port is PortJSON => !!port && typeof port === 'object' && typeof port.name === 'string',
    )
    // 同名端口保留已填值；新端口给空值；不再声明的键保留在 inputs 里（不自动清空）
    for (const port of ports.value) {
      if (inputs[port.name] === undefined) {
        inputs[port.name] = port.multi === true ? [] : portBase(port) === 'boolean' ? false : ''
      }
    }
  } catch (error) {
    log.error(`[TaskEditorPage] template.load “${workflow}” failed:`, error)
    ports.value = []
    showError(t('workflows.loadFailed', { error: errMsg(error) }))
  } finally {
    loadingDefinition.value = false
  }
}

/**
 * 改绑工作流：按端口名对齐。只存在于旧工作流的**已填值**会在保存前二次确认
 * （docs/08 §3-S3.2）；没有任何值会丢就不打扰。
 */
function onWorkflowChange(next: string) {
  const staleFilled = Object.keys(inputs).filter(
    (key) => !ports.value.some((port) => port.name === key) && hasValue(inputs[key]),
  )
  const apply = async () => {
    workflowMissing.value = false
    await loadDefinition(next)
    appliedWorkflow.value = next
  }
  if (staleFilled.length === 0) {
    void apply()
    return
  }
  dialog.warning({
    title: t('tasks.editor.rebindTitle'),
    content: t('tasks.editor.rebindContent', { count: staleFilled.length, keys: staleFilled.join(', ') }),
    positiveText: t('tasks.editor.rebindConfirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => {
      for (const key of staleFilled) delete inputs[key]
      void apply()
    },
    onNegativeClick: () => {
      // 取消改绑：把选择器退回上一个已生效的工作流
      form.workflow = appliedWorkflow.value
    },
  })
}

function openWorkflow() {
  if (form.workflow) void router.push(`/workflows/editor/${encodeURIComponent(form.workflow)}`)
}

// ---- 端口辅助 ---------------------------------------------------------------

const KNOWN_BASES = ['file', 'directory', 'text', 'number', 'boolean', 'json']

function portBase(port: PortJSON): string {
  const base = String(port.type?.base ?? '').toLowerCase()
  return KNOWN_BASES.includes(base) ? base : 'text'
}

/** 路径与 JSON（以及多行文本）在表单里整行显示。 */
function isWidePort(port: PortJSON): boolean {
  const base = portBase(port)
  return base === 'file' || base === 'directory' || base === 'json' || port.multi === true
}

function hasValue(value: unknown): boolean {
  if (value === undefined || value === null || value === '') return false
  return !(Array.isArray(value) && value.length === 0)
}

async function browseWorkDir() {
  try {
    const svc = (await serviceManager.getService('system')) as any
    const picked = await svc.selectDirectory({ title: t('tasks.editor.workDir') })
    if (picked && !picked.canceled) {
      const path = (picked.filePath || (picked.filePaths && picked.filePaths[0]) || '').trim()
      if (path) form.work_dir = path
    }
  } catch (error) {
    log.error('[TaskEditorPage] work dir picker failed:', error)
  }
}

// ---- 装载 / 保存 -------------------------------------------------------------

async function loadTask(name: string) {
  try {
    const result = await unifiedApi.call<TaskGetResult>('task.get', { name })
    const task = result?.task
    if (!task) throw new Error(t('tasks.detail.notFound'))
    form.name = task.name
    form.description = task.description ?? ''
    form.workflow = task.workflow ?? ''
    form.work_dir = task.work_dir ?? ''
    workflowMissing.value = result.workflow_exists === false
    for (const key of Object.keys(inputs)) delete inputs[key]
    Object.assign(inputs, task.inputs ?? {})
    await loadDefinition(form.workflow)
    appliedWorkflow.value = form.workflow
  } catch (error) {
    log.error(`[TaskEditorPage] task.get “${name}” failed:`, error)
    showError(t('tasks.loadFailed', { error: errMsg(error) }))
  }
}

onMounted(async () => {
  await loadWorkflows()

  if (nameFromRoute.value) {
    await loadTask(nameFromRoute.value)
    return
  }

  // 新建：可从 S5「存为任务」带 query 预填工作流与入参快照
  const queryWorkflow = typeof route.query.workflow === 'string' ? route.query.workflow : ''
  const queryInputs = typeof route.query.inputs === 'string' ? route.query.inputs : ''
  if (queryWorkflow) {
    form.workflow = queryWorkflow
    if (queryInputs) {
      try {
        const parsed = JSON.parse(queryInputs)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) Object.assign(inputs, parsed)
      } catch {
        log.warn('[TaskEditorPage] could not parse prefilled inputs')
      }
    }
    await loadDefinition(form.workflow)
    appliedWorkflow.value = form.workflow
  }
})

function validateName(): string | null {
  const name = form.name.trim()
  if (!name) return t('tasks.editor.nameRequired')
  // 路径安全：无分隔符、无 ..
  if (/[\\/]/.test(name) || name.includes('..')) return t('tasks.editor.nameInvalid')
  return null
}

/** 必填校验在表单层（后端不做端口级校验，docs/08 §3-S3.2）。 */
function validateInputs(): boolean {
  for (const key of Object.keys(fieldErrors)) delete fieldErrors[key]
  let ok = true
  for (const port of ports.value) {
    if (port.required === false) continue
    if (portBase(port) === 'boolean') continue
    if (!hasValue(inputs[port.name])) {
      fieldErrors[port.name] = t('tasks.editor.fieldRequired')
      ok = false
    }
  }
  return ok
}

async function save(thenRun: boolean) {
  nameError.value = validateName()
  if (nameError.value) return
  if (!validateInputs()) return

  // 可选空值不提交该键（docs/08 §3-S3.2）
  const payload: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(inputs)) {
    if (hasValue(value)) payload[key] = value
  }

  saving.value = true
  savingAndRunning.value = thenRun
  try {
    await unifiedApi.call('task.save', {
      name: form.name.trim(),
      workflow: form.workflow,
      inputs: payload,
      work_dir: form.work_dir.trim() || undefined,
      description: form.description.trim() || undefined,
    })
    if (thenRun) {
      await unifiedApi.call('task.execute', {
        name: form.name.trim(),
        task_id: `task-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      })
      showSuccess(t('tasks.editor.savedAndRun', { name: form.name.trim() }))
      await router.push({ path: '/tasks', query: { tab: 'runs', task: form.name.trim() } })
    } else {
      showSuccess(t('tasks.editor.saved', { name: form.name.trim() }))
      await router.push('/tasks')
    }
  } catch (error) {
    showError(t('tasks.editor.saveFailed', { error: errMsg(error) }))
  } finally {
    saving.value = false
    savingAndRunning.value = false
  }
}

function removeTask() {
  const name = form.name.trim()
  if (!name) return
  dialog.warning({
    title: t('tasks.deleteTitle'),
    content: t('tasks.deleteContent', { name }),
    positiveText: t('tasks.actions.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await unifiedApi.call('task.delete', { name })
        await router.push('/tasks')
      } catch (error) {
        showError(t('tasks.deleteFailed', { error: errMsg(error) }))
      }
    },
  })
}

function goBack() {
  void router.push('/tasks')
}

// 直接改 URL 的 name 时重新装载（二级页复用同一组件实例）
watch(nameFromRoute, (name) => {
  if (name) void loadTask(name)
})
</script>

<style scoped>
.task-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  overflow-y: auto;
  padding-bottom: 76px;
}

.page-header {
  display: flex;
  gap: 10px;
  align-items: center;
}

.page-title {
  margin: 0;
  font-family: var(--font-family-base);
  font-size: 20px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.page-grow {
  flex: 1;
}

.te-row {
  display: flex;
  gap: 12px;
}

.te-workflow {
  display: flex;
  gap: 10px;
  align-items: center;
}

.te-workflow-select {
  width: 300px;
}

.te-workflow-desc {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: 11.5px;
  color: var(--app-text-dim);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.te-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.te-field--wide {
  flex: 2;
}

.te-label {
  font-size: 12px;
  color: var(--app-text-secondary);
}

.te-req {
  color: var(--app-yellow);
}

.te-error {
  font-size: 11px;
  color: var(--app-red);
}

.te-help {
  font-size: 11px;
  color: var(--app-text-dim);
}

.te-placeholder {
  padding: 32px 16px;
  font-size: 13px;
  text-align: center;
  color: var(--app-text-muted);
  border: 1px dashed var(--app-card-border);
  border-radius: var(--radius-control);
}

.te-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 16px;
}

.te-port-field--full {
  grid-column: 1 / -1;
}

.te-footer {
  position: sticky;
  bottom: 0;
  display: flex;
  gap: 16px;
  align-items: flex-end;
  margin-top: auto;
  padding: 10px 14px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-control);
  /* 这里原有 `0 -2px 10px rgba(0,0,0,.12)`（向上投影）纯属冗余：粘底条本身已带
   * 1px 完整描边 + 不透明卡片底，滚动内容贴上来时边界已经清楚；三档阴影 token
   * 全是向下打的，硬套会打在视口外。按极简口径去掉，顺带消掉一处硬编码色。 */
}

.te-workdir {
  flex: 1;
}

.te-workdir-row {
  display: flex;
  gap: 6px;
}

.te-workdir-input {
  flex: 1;
  min-width: 0;
}

.te-footer-actions {
  display: flex;
  gap: 8px;
}
</style>
