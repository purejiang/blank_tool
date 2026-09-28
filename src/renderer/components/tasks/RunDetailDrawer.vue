<template>
  <!-- S5 运行详情（docs/08 §3-S5）：行展开后的抽屉，回答"这次为什么失败 /
       每一步花了多久 / 输出了什么"。数据源 history.get {run_id}。 -->
  <n-drawer :show="show" :width="720" placement="right" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="t('tasks.detail.title')" closable :native-scrollbar="false">
      <div v-if="loading" class="rd-status">{{ t('tasks.detail.loading') }}</div>
      <div v-else-if="loadError" class="rd-status rd-status--error">
        {{ t('tasks.loadFailed', { error: loadError }) }}
      </div>

      <div v-else-if="run" class="rd-body">
        <!-- 头部：状态 + 工作流 + 任务名 + 身份 + 起止/耗时 -->
        <div class="rd-head">
          <StatusBadge :status="status" />
          <span class="rd-workflow">{{ run.workflow_name || '—' }}</span>
          <span v-if="taskLabel" class="rd-task">{{ taskLabel }}</span>
          <n-button v-if="!run.task_name" size="tiny" quaternary @click="emit('save-as-task', run)">
            {{ t('tasks.detail.saveAsTask') }}
          </n-button>
        </div>

        <div class="rd-ident">
          <span>{{ t('tasks.detail.runId') }}: <code>{{ run.run_id }}</code></span>
          <span v-if="run.task_id">{{ t('tasks.detail.taskId') }}: <code>{{ run.task_id }}</code></span>
        </div>
        <div class="rd-ident">
          <span>{{ t('tasks.detail.started') }}: {{ formatTime(run.started_at) }}</span>
          <span>{{ t('tasks.detail.ended') }}: {{ formatTime(run.ended_at) }}</span>
          <span>{{ t('tasks.detail.duration') }}: {{ formatMs(run.duration_ms) }}</span>
        </div>

        <n-alert v-if="run.error" type="error" :show-icon="false" class="rd-error">
          {{ run.error }}
        </n-alert>

        <!-- 操作 -->
        <div class="rd-actions">
          <n-button size="tiny" :disabled="!run.run_dir" @click="openRunDir">
            {{ t('tasks.detail.openRunDir') }}
          </n-button>
          <n-button size="tiny" :loading="rerunning" @click="emit('rerun', run)">
            {{ t('tasks.detail.rerun') }}
          </n-button>
          <n-button size="tiny" type="error" quaternary @click="emit('delete', run)">
            {{ t('tasks.detail.deleteRecord') }}
          </n-button>
        </div>

        <!-- 输入快照 -->
        <div class="rd-section">
          <div class="rd-section-title">{{ t('tasks.detail.inputs') }}</div>
          <div v-if="inputEntries.length === 0" class="rd-empty">{{ t('tasks.detail.noInputs') }}</div>
          <div v-else class="rd-kv">
            <div v-for="[key, value] in inputEntries" :key="key" class="rd-kv-row">
              <span class="rd-kv-key">{{ key }}</span>
              <span class="rd-kv-value">
                {{ prettyValue(value) }}
                <n-button v-if="isPathLike(value)" size="tiny" quaternary @click="openPath(value)">
                  {{ t('tasks.detail.open') }}
                </n-button>
              </span>
            </div>
          </div>
        </div>

        <!-- 逐节点步骤（按 '/' 分层缩进） -->
        <div class="rd-section">
          <div class="rd-section-title">{{ t('tasks.detail.steps') }}</div>
          <div v-if="nodeEntries.length === 0" class="rd-empty">{{ t('tasks.detail.noSteps') }}</div>
          <div v-else class="rd-nodes">
            <div
              v-for="entry in nodeEntries"
              :key="entry.path"
              class="rd-node"
              :style="{ marginLeft: `${entry.depth * 14}px` }"
            >
              <div class="rd-node-head">
                <StatusBadge :status="entry.status" />
                <code class="rd-node-path">{{ entry.path }}</code>
                <span class="rd-node-meta">
                  {{ formatMs(entry.durationMs) }}
                  <template v-if="entry.attempts && entry.attempts > 1"> · {{ t('tasks.detail.attempts', { count: entry.attempts }) }}</template>
                </span>
              </div>
              <div v-if="entry.error" class="rd-node-error">{{ entry.error }}</div>
              <div v-if="entry.outputs.length > 0" class="rd-node-outputs">
                <div v-for="output in entry.outputs" :key="output.key" class="rd-output-row">
                  <span class="rd-output-key">{{ output.key }}</span>
                  <!-- 截断标记必须专门渲染（docs/08 §3-S5） -->
                  <span v-if="output.truncated" class="rd-output-truncated">
                    {{ t('tasks.detail.truncated') }}
                    <span v-if="output.note" class="rd-output-note">({{ output.note }})</span>
                    <pre v-if="output.preview" class="rd-pre rd-pre--preview">{{ output.preview }}</pre>
                  </span>
                  <span v-else class="rd-output-value">
                    {{ output.text }}
                    <n-button v-if="output.pathLike" size="tiny" quaternary @click="openPath(output.raw as string)">
                      {{ t('tasks.detail.open') }}
                    </n-button>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 日志区：task.read_log {task_id} -->
        <div class="rd-section">
          <div class="rd-section-title">
            {{ t('tasks.detail.log') }}
            <n-button size="tiny" quaternary :loading="logLoading" @click="loadLog">
              {{ t('tasks.detail.refreshLog') }}
            </n-button>
            <n-button size="tiny" quaternary :disabled="!logPath" @click="openLogFile">
              {{ t('tasks.detail.openLog') }}
            </n-button>
          </div>
          <div v-if="!logTaskId" class="rd-empty">{{ t('tasks.detail.noLog') }}</div>
          <template v-else>
            <div v-if="logError" class="rd-status rd-status--error">{{ logError }}</div>
            <pre v-else class="rd-pre">{{ logContent || t('tasks.detail.logEmpty') }}</pre>
            <div v-if="logTruncated" class="rd-log-hint">{{ t('tasks.detail.logTruncated') }}</div>
          </template>
        </div>
      </div>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAlert, NButton, NDrawer, NDrawerContent } from 'naive-ui'

import StatusBadge from '@components/ui/StatusBadge.vue'
import {
  formatMs,
  isPathLike,
  isTruncatedOutput,
  nodeDepth,
  nodeStatusOf,
  prettyValue,
  runStatusOf,
  truncationNote,
  type RunStatusKey,
} from './runFormat'
import type { NodeResultEntry, RunRecord, TaskLogResult } from '../../../shared/ipc/protocol'
import unifiedApi from '@/api/unifiedApi'
import serviceManager from '@services/ServiceManager'
import { log } from '@utils/logger'

/**
 * S5: full detail of one run record.
 *
 * Read-only except for the explicit actions (open run dir / rerun / delete /
 * save-as-task), which are emitted so the owning page can keep list state in
 * sync.
 */
const props = defineProps<{
  show: boolean
  /** Run id to load; empty closes the content. */
  runId: string
  rerunning?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'rerun', run: RunRecord): void
  (e: 'delete', run: RunRecord): void
  (e: 'save-as-task', run: RunRecord): void
}>()

const { t } = useI18n()

const run = ref<RunRecord | null>(null)
const loading = ref(false)
const loadError = ref('')

const status = computed<RunStatusKey>(() => runStatusOf(run.value))

const taskLabel = computed(() => {
  const name = run.value?.task_name
  return name ? `${t('tasks.detail.task')}: ${name}` : t('tasks.detail.oneShot')
})

function errMsg(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

async function load() {
  if (!props.runId) {
    run.value = null
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const result = await unifiedApi.call<{ run: RunRecord }>('history.get', { run_id: props.runId })
    run.value = result?.run ?? null
    if (!run.value) loadError.value = t('tasks.detail.notFound')
  } catch (error) {
    log.error('[RunDetailDrawer] history.get failed:', error)
    loadError.value = errMsg(error)
    run.value = null
  } finally {
    loading.value = false
  }
  void loadLog()
}

watch(() => [props.show, props.runId] as const, ([open]) => {
  if (!open) return
  void load()
}, { immediate: true })

// ---- 输入 / 输出 / 节点投影 ------------------------------------------------

const inputEntries = computed(() => Object.entries(run.value?.inputs ?? {}))

/**
 * 逐节点步骤。运行记录里**没有运行级 outputs**（`history.store.record_run`
 * 只写 `node_results`），所以不编造该区块——最后一个节点的输出就是整轮的产出。
 */
const nodeEntries = computed(() => {
  const results = (run.value?.node_results ?? {}) as Record<string, NodeResultEntry>
  return Object.entries(results).map(([path, entry]) => {
    const outputs = Object.entries(entry?.outputs ?? {}).map(([key, value]) => {
      if (isTruncatedOutput(value)) {
        return {
          key,
          truncated: true as const,
          note: truncationNote(value),
          preview: typeof value._preview === 'string' ? value._preview : '',
          text: '',
          pathLike: false,
          raw: value as unknown,
        }
      }
      return {
        key,
        truncated: false as const,
        note: '',
        preview: '',
        text: prettyValue(value),
        pathLike: isPathLike(value),
        raw: value as unknown,
      }
    })
    return {
      path,
      depth: nodeDepth(path),
      status: nodeStatusOf(entry?.status),
      durationMs: entry?.duration_ms,
      attempts: entry?.attempts,
      error: entry?.error ?? '',
      outputs,
    }
  })
})

// ---- 日志 ------------------------------------------------------------------

const logTaskId = computed(() => run.value?.task_id || '')
const logContent = ref('')
const logTruncated = ref(false)
const logPath = ref('')
const logLoading = ref(false)
const logError = ref('')

async function loadLog() {
  const taskId = logTaskId.value
  if (!taskId) {
    logContent.value = ''
    logPath.value = ''
    return
  }
  logLoading.value = true
  logError.value = ''
  try {
    const result = await unifiedApi.call<TaskLogResult>('task.read_log', { task_id: taskId })
    if (result?.error) throw new Error(result.error)
    logContent.value = result?.content ?? ''
    logTruncated.value = result?.truncated ?? false
    logPath.value = result?.log_path ?? ''
  } catch (error) {
    logError.value = t('tasks.detail.logFailed', { error: errMsg(error) })
  } finally {
    logLoading.value = false
  }
}

async function openLogFile() {
  if (!logPath.value) return
  await openPath(logPath.value)
}

// ---- 打开路径 --------------------------------------------------------------

async function openPath(target: string) {
  try {
    const svc = (await serviceManager.getService('system')) as any
    await svc.openPath(target)
  } catch (error) {
    log.error('[RunDetailDrawer] openPath failed:', error)
  }
}

function openRunDir() {
  if (run.value?.run_dir) void openPath(run.value.run_dir)
}
</script>

<style scoped>
.rd-status {
  font-size: 12px;
  color: var(--app-text-muted);
}

.rd-status--error {
  color: var(--app-red);
}

.rd-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rd-head {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.rd-workflow {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.rd-task {
  font-size: 12px;
  color: var(--app-text-secondary);
}

.rd-ident {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--app-text-dim);
}

.rd-ident code,
.rd-node-path {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
}

.rd-error {
  margin: 0;
}

.rd-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.rd-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--app-card-border);
}

.rd-section-title {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--app-text-secondary);
}

.rd-empty {
  font-size: 12px;
  color: var(--app-text-muted);
}

.rd-kv {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rd-kv-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 12px;
}

.rd-kv-key {
  flex-shrink: 0;
  min-width: 140px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  color: var(--app-text-secondary);
}

.rd-kv-value {
  min-width: 0;
  word-break: break-all;
  white-space: pre-wrap;
  color: var(--app-text-primary);
}

.rd-nodes {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rd-node {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-chip);
}

.rd-node-head {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.rd-node-meta {
  margin-left: auto;
  font-size: 11px;
  color: var(--app-text-dim);
}

.rd-node-error {
  font-size: 12px;
  color: var(--app-red);
  white-space: pre-wrap;
}

.rd-node-outputs {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rd-output-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 12px;
}

.rd-output-key {
  flex-shrink: 0;
  min-width: 140px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  color: var(--app-text-secondary);
}

.rd-output-value {
  min-width: 0;
  word-break: break-all;
  white-space: pre-wrap;
}

.rd-output-truncated {
  font-size: 11px;
  color: var(--app-orange, var(--app-yellow));
}

.rd-output-note {
  color: var(--app-text-dim);
}

.rd-pre {
  max-height: 260px;
  margin: 0;
  padding: 8px;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  background: var(--app-code-bg, var(--app-storage-bg));
  border-radius: var(--radius-chip);
}

.rd-pre--preview {
  max-height: 120px;
  margin-top: 4px;
}

.rd-log-hint {
  font-size: 11px;
  color: var(--app-text-dim);
}
</style>
