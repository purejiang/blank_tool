<template>
  <!-- S3.1 任务列表（docs/08 §3-S3.1）：任务 = 可持久化的执行配置（绑定的工作流 +
       保存的入参）。列表展示**任务定义**，不是运行日志；因此没有运行状态徽章。 -->
  <div class="task-list">
    <div class="tl-toolbar">
      <n-button size="small" type="primary" @click="emit('new-task')">
        <template #icon><AppIcon name="plus" /></template>
        {{ t('tasks.new') }}
      </n-button>
      <n-input
        v-model:value="query"
        size="small"
        clearable
        class="tl-search"
        :placeholder="t('tasks.search')"
      />
      <span class="tl-grow" />
      <n-button size="small" quaternary :loading="loading" @click="load">
        <template #icon><AppIcon name="refresh" /></template>
        {{ t('workflows.refresh') }}
      </n-button>
    </div>

    <div v-if="loading && tasks.length === 0" class="tl-status">{{ t('tasks.loading') }}</div>
    <n-alert v-else-if="loadError" type="error" :show-icon="true">
      <div class="tl-status-row">
        <span>{{ t('tasks.loadFailed', { error: loadError }) }}</span>
        <n-button size="tiny" @click="load">{{ t('workflows.retry') }}</n-button>
      </div>
    </n-alert>

    <div v-else-if="tasks.length === 0" class="tl-empty">
      <div class="tl-empty-title">{{ t('tasks.empty.title') }}</div>
      <!-- 两种空态：有工作流 → 直接建任务；没有工作流 → 先去创建工作流 -->
      <div v-if="workflowCount === 0" class="tl-empty-hint">
        {{ t('tasks.empty.noWorkflows') }}
      </div>
      <div class="tl-empty-actions">
        <n-button size="small" type="primary" @click="emit('new-task')">{{ t('tasks.new') }}</n-button>
        <n-button v-if="workflowCount === 0" size="small" @click="goWorkflows">
          {{ t('tasks.empty.goWorkflows') }}
        </n-button>
      </div>
    </div>

    <div v-else-if="filtered.length === 0" class="tl-empty">
      <div class="tl-empty-title">{{ t('tasks.noMatch') }}</div>
    </div>

    <div v-else class="tl-rows">
      <div v-for="task in filtered" :key="task.name" class="tl-row">
        <div class="tl-main">
          <div class="tl-head">
            <button type="button" class="tl-name" :title="task.name" @click="emit('edit-task', task.name)">
              {{ task.name }}
            </button>
            <n-tag v-if="!task.workflow_exists" type="warning" size="small" :bordered="false">
              {{ t('tasks.workflowMissing') }}
            </n-tag>
            <n-tag v-else size="small" :bordered="false">{{ task.workflow }}</n-tag>
          </div>
          <div v-if="task.description" class="tl-desc" :title="task.description">{{ task.description }}</div>
          <div class="tl-meta">
            <span>{{ t('tasks.inputCount', { count: task.input_count }) }}</span>
            <span>·</span>
            <span>{{ t('workflows.card.updated', { time: formatTime(task.updated_at) }) }}</span>
            <template v-if="task.has_work_dir">
              <span>·</span>
              <span>{{ t('tasks.hasWorkDir') }}</span>
            </template>
          </div>
        </div>

        <div class="tl-actions">
          <n-button
            size="tiny"
            type="primary"
            :disabled="!task.workflow_exists"
            :loading="runningName === task.name"
            @click="runTask(task)"
          >
            {{ t('tasks.actions.run') }}
          </n-button>
          <n-button size="tiny" quaternary @click="emit('edit-task', task.name)">
            {{ t('workflows.actions.edit') }}
          </n-button>
          <n-button size="tiny" quaternary @click="duplicate(task)">
            {{ t('workflows.actions.duplicate') }}
          </n-button>
          <n-button size="tiny" quaternary @click="emit('view-runs', task.name)">
            {{ t('tasks.actions.viewRuns') }}
          </n-button>
          <n-button size="tiny" quaternary type="error" @click="remove(task)">
            {{ t('tasks.actions.delete') }}
          </n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NAlert, NButton, NInput, NTag, useDialog } from 'naive-ui'
import AppIcon from '@components/ui/AppIcon.vue'

import type { TaskDefinitionSummary } from '../../../shared/ipc/protocol'
import unifiedApi from '@/api/unifiedApi'
import { useNotification } from '@composables/useNotification'
import { log } from '@utils/logger'

/** S3.1: the task-definition list. */
const emit = defineEmits<{
  (e: 'new-task'): void
  (e: 'edit-task', name: string): void
  (e: 'view-runs', taskName: string): void
}>()

const { t } = useI18n()
const router = useRouter()
const dialog = useDialog()
const { showSuccess, showError } = useNotification()

const tasks = ref<TaskDefinitionSummary[]>([])
const loading = ref(false)
const loadError = ref('')
const query = ref('')
const runningName = ref<string | null>(null)
/** 用于区分两种空态：有工作流 / 一个都没有。 */
const workflowCount = ref(0)

function errMsg(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [taskResult, templateResult] = await Promise.all([
      unifiedApi.call<{ tasks?: TaskDefinitionSummary[] }>('task.list'),
      unifiedApi.call<{ templates?: unknown[] }>('template.list', {}),
    ])
    tasks.value = Array.isArray(taskResult?.tasks) ? taskResult.tasks : []
    workflowCount.value = Array.isArray(templateResult?.templates) ? templateResult.templates.length : 0
  } catch (error) {
    log.error('[TaskListView] task.list failed:', error)
    loadError.value = errMsg(error)
    tasks.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return tasks.value
  return tasks.value.filter(
    (task) =>
      task.name.toLowerCase().includes(needle) ||
      (task.description ?? '').toLowerCase().includes(needle) ||
      (task.workflow ?? '').toLowerCase().includes(needle),
  )
})

function goWorkflows() {
  void router.push('/workflows')
}

/** 运行 = 用保存的入参直接执行；执行后由页面切到运行记录并预置任务筛选。 */
async function runTask(task: TaskDefinitionSummary) {
  runningName.value = task.name
  try {
    await unifiedApi.call('task.execute', {
      name: task.name,
      task_id: `task-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    })
    showSuccess(t('tasks.runStarted', { name: task.name }))
    emit('view-runs', task.name)
  } catch (error) {
    showError(t('tasks.runFailed', { error: errMsg(error) }))
  } finally {
    runningName.value = null
  }
}

async function duplicate(task: TaskDefinitionSummary) {
  const newName = `${task.name}-copy`
  try {
    const loaded = await unifiedApi.call<{ task?: { workflow?: string; inputs?: Record<string, unknown>; work_dir?: string; description?: string } }>(
      'task.get',
      { name: task.name },
    )
    const definition = loaded?.task
    if (!definition?.workflow) throw new Error(t('tasks.detail.notFound'))
    await unifiedApi.call('task.save', {
      name: newName,
      workflow: definition.workflow,
      inputs: definition.inputs ?? {},
      work_dir: definition.work_dir || undefined,
      description: definition.description || undefined,
    })
    showSuccess(t('tasks.duplicated', { name: newName }))
    await load()
    emit('edit-task', newName)
  } catch (error) {
    showError(t('tasks.duplicateFailed', { error: errMsg(error) }))
  }
}

function remove(task: TaskDefinitionSummary) {
  dialog.warning({
    title: t('tasks.deleteTitle'),
    content: t('tasks.deleteContent', { name: task.name }),
    positiveText: t('tasks.actions.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await unifiedApi.call('task.delete', { name: task.name })
        await load()
      } catch (error) {
        showError(t('tasks.deleteFailed', { error: errMsg(error) }))
      }
    },
  })
}

defineExpose({ load })
</script>

<style scoped>
.task-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tl-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.tl-search {
  width: 240px;
}

.tl-grow {
  flex: 1;
}

.tl-status {
  font-size: 12px;
  color: var(--app-text-muted);
}

.tl-status-row {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.tl-empty {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  padding: 40px 20px;
  text-align: center;
  border: 1px dashed var(--app-card-border);
  border-radius: var(--radius-control);
}

.tl-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.tl-empty-hint {
  max-width: 520px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--app-text-muted);
}

.tl-empty-actions {
  display: flex;
  gap: 8px;
}

.tl-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tl-row {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-control);
}

.tl-main {
  flex: 1;
  min-width: 0;
}

.tl-head {
  display: flex;
  gap: 8px;
  align-items: center;
}

.tl-name {
  max-width: 320px;
  overflow: hidden;
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--app-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  background: transparent;
  border: 0;
}

.tl-name:hover {
  color: var(--app-blue);
}

.tl-desc {
  margin-top: 2px;
  overflow: hidden;
  font-size: 11.5px;
  color: var(--app-text-dim);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-meta {
  display: flex;
  gap: 6px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--app-text-muted);
}

.tl-actions {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-shrink: 0;
}
</style>
