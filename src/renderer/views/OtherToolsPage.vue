<template>
  <div class="auto-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('automation.title') }}</h1>
        <p class="page-subtitle">{{ t('automation.subtitle') }}</p>
      </div>
      <n-space>
        <n-button size="small" @click="exportConfig">
          <template #icon><n-icon><Download /></n-icon></template>
          {{ t('automation.export') }}
        </n-button>
        <n-button size="small" @click="importConfig">
          <template #icon><n-icon><Upload /></n-icon></template>
          {{ t('automation.import') }}
        </n-button>
      </n-space>
    </div>

    <div class="three-cols" :style="gridStyle">
      <!-- ============ LEFT: project / script tree ============ -->
      <ProjectTree :store="store" :running="runner.running" />

      <div class="col-divider" @pointerdown.prevent="startResize('left', $event)" />

      <!-- ============ CENTER: script editor ============ -->
      <section class="col col-center">
        <n-empty v-if="!store.selectedProjectId || !store.selectedScriptId" :description="t('automation.noSelection')" class="col-empty" />

        <template v-else>
          <div class="col-head">
            <span class="editor-title">
              <span class="editor-name">{{ store.selectedScript?.name }}</span>
              <span v-if="store.selectedScript?.description" class="editor-desc">{{ store.selectedScript.description }}</span>
            </span>
            <transition name="fade">
              <span v-if="store.savedFlash" class="autosave-hint saved">{{ t('automation.savedNow') }}</span>
            </transition>
            <!-- 这一行只放脚本身份 + 自动保存提示：右上角是"已保存"闪现的位置，
                 视图切换/添加按钮放这儿会跟它抢，所以都留在 .steps-head -->
          </div>

          <div class="editor-body">
            <div class="field steps-field">
              <!-- 工具行：视图切换 + 添加步骤，整组右对齐（添加按钮贴最右） -->
              <div class="steps-head">
                <div class="steps-head-right">
                  <n-radio-group
                    class="view-switch"
                    size="small"
                    :value="store.stepsView"
                    :disabled="runner.running"
                    @update:value="store.onSwitchView"
                  >
                    <n-radio-button value="ui">{{ t('automation.viewSteps') }}</n-radio-button>
                    <n-radio-button value="json">{{ t('automation.viewJson') }}</n-radio-button>
                  </n-radio-group>
                  <n-dropdown
                    trigger="click"
                    placement="bottom-end"
                    :options="addOptions"
                    :disabled="runner.running || store.stepsView !== 'ui'"
                    @select="onAdd"
                  >
                    <n-button
                      class="add-step-btn"
                      size="small"
                      type="primary"
                      secondary
                      :disabled="runner.running || store.stepsView !== 'ui'"
                    >
                      <template #icon><n-icon><Plus /></n-icon></template>
                      {{ t('automation.addStep') }}
                    </n-button>
                  </n-dropdown>
                </div>
              </div>

              <!-- 计数单独一行，紧贴下面的列表，左对齐 -->
              <div class="steps-count-row">
                <span class="steps-count">{{ t('automation.stepCountLabel', { n: stepCountDisplay }) }}</span>
              </div>

              <StepListEditor
                v-if="store.stepsView === 'ui'"
                ref="stepListRef"
                v-model="store.editor.steps"
                v-model:selected-index="store.selectedStepIndex"
                :disabled="runner.running"
                :default-timeout="elementTimeoutMs"
                class="steps-editor"
                @pick="onStepPick"
              />
              <template v-else>
                <n-input
                  v-model:value="store.stepsText"
                  type="textarea"
                  :autosize="{ minRows: 14, maxRows: 26 }"
                  :disabled="runner.running"
                  class="steps-json"
                  @update:value="store.refreshJsonStatus"
                />
                <div v-if="store.jsonError" class="json-status bad">
                  {{ t('automation.jsonInvalid', { msg: store.jsonError }) }}
                </div>
              </template>
            </div>
          </div>

          <!-- 录制面板：停靠在中栏编辑器下方 -->
          <RecordPanel
            v-show="recordPanelOpen"
            ref="recordPanelRef"
            class="docked-record"
            :device-id="autoDeviceId"
            :disabled="runner.running && !recording"
            :has-selection="store.selectedStepIndex >= 0"
            @recording-start="onRecStart"
            @recorded="store.onRecorded"
            @recording-end="onRecEnd"
            @close="recordPanelOpen = false"
          />
        </template>
      </section>

      <div class="col-divider" @pointerdown.prevent="startResize('right', $event)" />

      <!-- ============ RIGHT: run console ============ -->
      <!-- top → bottom: run controls, the run panel (status bar + steps /
           requests / logs tabs, live or replayed), then run history. The
           history stays permanently expanded and a click replays that run
           into the panel above it. -->
      <section class="col col-right">
        <RunControls
          v-model:auto-device-id="autoDeviceId"
          v-model:capture-traffic="captureTraffic"
          :running="runner.running"
          :can-run="canRun"
          @run="runScript"
          @stop="runner.stopRun"
        />
        <RunPanel
          :running="runner.running"
          :run-result="runner.runResult"
          :live-steps="runner.liveSteps"
          :logs="runner.logs"
          :screenshots="runner.screenshots"
          :run-started-ts="runner.runStartedTs"
          :report="viewingReport"
          :exporting="exporting"
          @open-report="onOpenReport"
          @open-file="openReportFile"
          @download-report="downloadRunReport"
          @close-report="closeReport"
        />
        <RunHistory
          :runs="runs"
          :loading="runsLoading"
          :selected-task-id="viewingReport?.task_id || ''"
          @refresh="fetchRuns"
          @select="onSelectRun"
          @remove="onDeleteRun"
        />
      </section>
    </div>

    <!-- ============ Element picker modal ============ -->
    <ElementPickerModal
      v-model:show="showElements"
      :dumping="dumping"
      :elements="elements"
      @apply="applyElement"
    />

    <!-- ============ Project / script meta editor modal ============ -->
    <n-modal v-model:show="store.showMeta" :title="t('automation.editInfo')" preset="card" style="width: 440px">
      <div class="field">
        <label>{{ store.metaForm.kind === 'project' ? t('automation.projectName') : t('automation.scriptName') }}</label>
        <n-input v-model:value="store.metaForm.name" size="small" />
      </div>
      <div v-if="store.metaForm.kind === 'project'" class="field">
        <label>{{ t('automation.packageName') }}</label>
        <n-input v-model:value="store.metaForm.packageName" size="small" placeholder="com.example.app" />
      </div>
      <div class="field">
        <label>{{ t('automation.description') }}</label>
        <n-input
          v-model:value="store.metaForm.description"
          type="textarea"
          size="small"
          :autosize="{ minRows: 2, maxRows: 4 }"
        />
      </div>
      <template #footer>
        <n-space justify="end">
          <n-button size="small" @click="store.showMeta = false">{{ t('common.cancel') }}</n-button>
          <n-button size="small" type="primary" @click="store.saveMeta">{{ t('common.confirm') }}</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NInput,
  NModal,
  NEmpty,
  NIcon,
  NSpace,
  NRadioButton,
  NRadioGroup,
  NDropdown,
  useMessage,
  useDialog,
} from 'naive-ui'
import { Download, Upload } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import RecordPanel from '@components/automation/RecordPanel.vue'
import StepListEditor from '@components/automation/StepListEditor.vue'
import ProjectTree from '@components/automation/ProjectTree.vue'
import RunControls from '@components/automation/RunControls.vue'
import RunPanel from '@components/automation/RunPanel.vue'
import RunHistory from '@components/automation/RunHistory.vue'
import ElementPickerModal from '@components/automation/ElementPickerModal.vue'
import { parseUiDump, boundsCenter, type UiNode } from '@components/automation/uiDump'
import {
  ADDABLE_ACTIONS, defaultStep, type Step, type StepAction,
} from '@components/automation/stepTypes'
import { stepActionLabel } from '@components/automation/stepMeta'
import { useScriptRunner } from '@composables/automation/useScriptRunner'
import { useAutomationStore } from '@composables/automation/useAutomationStore'

const { t } = useI18n()
const message = useMessage()
const dialog = useDialog()
const deviceStore = useDeviceStore()

// ---------------- domain state (extracted) ----------------
// Runner owns the run lifecycle; the store owns projects/scripts/editor.
// Store mutations are blocked while a run (or recording, which flips the
// runner's running flag) is in flight.
const runner = useScriptRunner()
const store = useAutomationStore(() => runner.running)

// ---------------- column resize ----------------
// Side columns are user-resizable via the drag dividers; widths persist.
// Center column is minmax(0,1fr) and absorbs the remaining space.
const COL_MIN = 180
const COL_MAX = 520
function clampCol(v: number) {
  return Math.max(COL_MIN, Math.min(COL_MAX, Math.round(v)))
}
const colLeft = ref(clampCol(Number(localStorage.getItem('bt:autoColLeft')) || 240))
const colRight = ref(clampCol(Number(localStorage.getItem('bt:autoColRight')) || 320))
const gridStyle = computed(() => ({
  gridTemplateColumns: `${colLeft.value}px 12px minmax(0, 1fr) 12px ${colRight.value}px`,
}))

function startResize(side: 'left' | 'right', e: PointerEvent) {
  const startX = e.clientX
  const startW = side === 'left' ? colLeft.value : colRight.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  const onMove = (ev: PointerEvent) => {
    // Left divider: drag right → wider. Right divider: drag right → narrower.
    const w = side === 'left' ? startW + (ev.clientX - startX)
                              : startW - (ev.clientX - startX)
    if (side === 'left') colLeft.value = clampCol(w)
    else colRight.value = clampCol(w)
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    try {
      localStorage.setItem('bt:autoColLeft', String(colLeft.value))
      localStorage.setItem('bt:autoColRight', String(colRight.value))
    } catch {}
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

// ---------------- page-local state ----------------
// Automation-page device selection — deliberately DECOUPLED from the
// device page's list selection (which is only for the detail panel).
// Persisted locally so the page remembers the last device used.
const autoDeviceId = ref(localStorage.getItem('bt:automationDeviceId') || '')
watch(autoDeviceId, (v) => {
  try { localStorage.setItem('bt:automationDeviceId', v) } catch {}
})
// Traffic capture (mitmdump) — opt-in per run; the backend restores the
// device proxy in a finally block on every exit path.
const captureTraffic = ref(false)
// Default element-poll timeout (ms): applied when a step switches to
// element mode / picks an element; editable in the right column.
const elementTimeoutMs = ref(
  clampTimeout(Number(localStorage.getItem('bt:autoElementTimeoutMs')) || 10000)
)
function clampTimeout(v: number): number {
  return Math.max(500, Math.min(120000, Math.round(v)))
}
watch(elementTimeoutMs, (v) => {
  try { localStorage.setItem('bt:autoElementTimeoutMs', String(v)) } catch {}
})
// Drop the selection when the device vanishes from the live list.
watch(() => deviceStore.devices, (list) => {
  if (autoDeviceId.value && !(list as any[]).some(d => d.id === autoDeviceId.value)) {
    autoDeviceId.value = ''
  }
}, { immediate: true })

// Run is allowed only when both a device and a script are selected.
const canRun = computed(() => !!autoDeviceId.value && !!store.selectedScriptId && !recording.value)

// ---------------- steps header (count / add / view switch) ----------------
const stepListRef = ref<InstanceType<typeof StepListEditor> | null>(null)
/** 左侧计数：UI 视图取编辑器实时列表，JSON 视图取解析后的 stepCount */
const stepCountDisplay = computed(() =>
  store.stepsView === 'json' ? store.stepCount : store.editor.steps.length
)

const RECORD_KEY = '__record__'
const addOptions = computed(() => [
  {
    key: RECORD_KEY,
    label: t('automation.recordSegment'),
  },
  { type: 'divider' as const, key: 'd1' },
  ...ADDABLE_ACTIONS.map(a => ({
    key: a,
    label: stepActionLabel(a, t),
  })),
])

function onAdd(action: string) {
  if (action === RECORD_KEY) {
    onRecordRequest()
    return
  }
  const list: Step[] = [...store.editor.steps, defaultStep(action as StepAction)]
  store.editor.steps = list
  if (store.stepsView === 'json') store.syncJsonText()
  // 新步骤直接进入编辑状态
  nextTick(() => stepListRef.value?.openEditor(list.length - 1))
}

/** 录制面板停靠开关（中栏编辑器下方）；唯一入口 = 添加步骤 → 录制片段，
 * 关闭走面板自带的 X 按钮 */
const recordPanelOpen = ref(false)
const recording = ref(false)
const recordPanelRef = ref<InstanceType<typeof RecordPanel> | null>(null)

/** 「添加步骤 → 录制片段…」：展开中栏录制面板采集 */
function onRecordRequest() {
  if (runner.running && !recording.value) {
    message.warning(t('automation.runStopFirst'))
    return
  }
  recordPanelOpen.value = true
  message.info(t('automation.recordSegmentHint'))
}

// Recording reuses the runner's `running` flag as the global busy signal —
// every busy-guard in the store/runner keys off it.
function onRecStart() {
  recording.value = true
  runner.running = true
}
function onRecEnd() {
  recording.value = false
  runner.running = false
}

// ---------------- run history ----------------
// Each run persists report.json + categorized artifacts under
// {BT_AUTO_TASKS_DIR}/{task_id}/; the history list is always visible on the
// run page (no collapse) and a click restores that run into the panel below.
const runs = ref<any[]>([])
const runsLoading = ref(false)
const viewingReport = ref<any | null>(null)

async function fetchRuns() {
  runsLoading.value = true
  try {
    const api = window.electronAPI as any
    const res = await api.callBackendAPI('automation.list_runs', {})
    runs.value = res?.runs || []
  } catch {
    /* history is best-effort */
  } finally {
    runsLoading.value = false
  }
}
onMounted(() => { void fetchRuns() })

/** 点运行记录 → 把那次运行的报告恢复到页面里 */
async function onSelectRun(taskId: string) {
  try {
    const api = window.electronAPI as any
    const res = await api.callBackendAPI('automation.read_run', { task_id: taskId })
    if (!res?.success || !res.report) {
      message.error(t('automation.reportLoadFailed'))
      return
    }
    viewingReport.value = res.report
  } catch (e: any) {
    message.error(e?.message || String(e))
  }
}

const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

/**
 * 运行结束后的对账。
 *
 * `report.json` 是插件在 `finally` 里写的 —— 也就是**在 `complete` 事件之后**
 * 一点点。所以「收到 complete 就立刻刷一次列表」必然和写盘抢跑：列表里看不到
 * 刚跑完的那条（这就是「运行记录不会自动刷新」的原因）。
 * 这里轮询到记录真的落盘为止，再刷一次列表。
 *
 * 另外：如果实时控制台什么都没收到（没有日志也没有步骤），但磁盘上有这次运行
 * 的记录，就把落盘的报告回放到面板里 —— 保证「运行完，运行信息里有日志和步骤」。
 */
async function reconcileFinishedRun() {
  const taskId = String(runner.runResult?.task_id || runner.taskId || '')
  for (let i = 0; i < 20; i++) {
    await fetchRuns()
    if (!taskId || runs.value.some(r => String(r.task_id) === taskId)) break
    await sleep(200)
  }
  const persisted = !!taskId && runs.value.some(r => String(r.task_id) === taskId)
  // 实时流一条都没到（既没日志也没步骤）：用落盘报告回放面板，并明确提示 ——
  // 否则又是一个「运行信息里就一点点信息」的无声故障。
  if (persisted && !runner.liveSteps.length && !runner.logs.length) {
    await onSelectRun(taskId)
    message.warning(t('automation.streamSilentHint'))
  }
}

/** 回到实时/最近一次运行视图 */
function closeReport() {
  viewingReport.value = null
}

function onDeleteRun(taskId: string) {
  dialog.warning({
    title: t('automation.deleteRun'),
    content: t('automation.deleteRunConfirm'),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      const api = window.electronAPI as any
      try {
        const res = await api.callBackendAPI('automation.delete_run', { task_id: taskId })
        if (!res?.deleted) {
          message.error(res?.error || 'delete failed')
          return
        }
        if (viewingReport.value?.task_id === taskId) viewingReport.value = null
        void fetchRuns()
      } catch (e: any) {
        message.error(e?.message || String(e))
      }
    },
  })
}

// The run record is written to disk a beat AFTER the `complete` event, so the
// list must be reconciled rather than refreshed once — see
// `reconcileFinishedRun`. Called from the run's finally block below.

/** 当前要操作的那次运行：优先页面里正在看的那条，否则最近一次运行 */
function currentRunTaskId(): string {
  return viewingReport.value?.task_id || String(runner.runResult?.task_id || '')
}

/** 打开报告：把那次运行的报告恢复到页面里（带时间戳 + 请求日志的完整视图） */
async function onOpenReport() {
  const taskId = currentRunTaskId()
  if (!taskId) {
    message.warning(t('automation.reportUnavailable'))
    return
  }
  await onSelectRun(taskId)
}

const exporting = ref(false)

/** 内置 API：导出 HTML（始终在运行目录里留一份归档，返回其路径） */
async function buildRunReportHtml(taskId: string, target = ''): Promise<string> {
  const api = window.electronAPI as any
  const r = await api.callBackendAPI('automation.export_run', { task_id: taskId, target })
  if (!r?.success) {
    message.error(r?.error || t('automation.reportExportFailed'))
    return ''
  }
  return r.file_path || r.archive_path || ''
}

/** 浏览器打开：先落盘归档，再交给系统用默认程序打开 */
async function openReportFile() {
  const taskId = currentRunTaskId()
  if (!taskId) {
    message.warning(t('automation.reportUnavailable'))
    return
  }
  exporting.value = true
  try {
    const path = await buildRunReportHtml(taskId)
    if (!path) return
    await (window.electronAPI as any)?.openPath?.(path)
  } catch (e: any) {
    message.error(e?.message || String(e))
  } finally {
    exporting.value = false
  }
}

/** 下载报告：自包含 HTML（截图 base64 内嵌 + 请求表），存到用户选定路径 */
async function downloadRunReport() {
  const taskId = currentRunTaskId()
  if (!taskId) {
    message.warning(t('automation.reportUnavailable'))
    return
  }
  const api = window.electronAPI as any
  let target = ''
  if (api?.showSaveDialog) {
    const now = new Date()
    const pad = (v: number) => String(v).padStart(2, '0')
    const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`
    const res = await api.showSaveDialog({
      title: t('automation.downloadReport'),
      defaultPath: `automation-${taskId}-${ts}.html`,
      filters: [{ name: 'HTML', extensions: ['html'] }],
    })
    if (!res || res.canceled || !res.filePath) return
    target = res.filePath
  }
  exporting.value = true
  try {
    const path = await buildRunReportHtml(taskId, target)
    if (path) message.success(`${t('automation.downloadReport')} → ${path}`)
  } catch (e: any) {
    message.error(e?.message || String(e))
  } finally {
    exporting.value = false
  }
}

// ---------------- run ----------------
async function runScript() {
  if (runner.running) return
  if (!autoDeviceId.value) {
    message.error(t('automation.noDeviceSelectedRun'))
    return
  }
  if (!store.selectedScriptId) {
    message.warning(t('automation.noScriptSelected'))
    return
  }
  // flush any pending debounced auto-save so the run uses the latest edits
  store.flushAutoSaveNow()
  if (!store.commitEditor()) return
  const s = store.selectedScript
  if (!s || !s.steps.length) {
    message.warning(t('automation.noSteps'))
    return
  }
  try {
    // 报告视图会让位给实时日志：开跑就关掉历史报告，否则看不到运行中的日志
    viewingReport.value = null
    await runner.runScript({
      device_id: autoDeviceId.value,
      package_name: store.selectedProject?.package_name || '',
      steps: s.steps,
      capture_traffic: captureTraffic.value,
    })
  } catch (e: any) {
    message.error(e?.message || String(e))
  } finally {
    // 无论成功、失败还是取消，都要把「刚跑完的那条」对账进列表 —— report.json
    // 落在 complete 之后，所以这里必须轮询而不是只刷一次。
    void reconcileFinishedRun()
  }
}

// ---------------- element picker ----------------
const dumping = ref(false)
const showElements = ref(false)
const elements = ref<UiNode[]>([])
/** 元素抽屉始终处于“填充步骤”模式（由编辑表单的“获取界面元素”按钮打开） */
const pickTarget = ref<{ index: number; mode: 'coord' | 'element' } | null>(null)

async function getElements() {
  if (runner.running) return
  if (!autoDeviceId.value) {
    message.error(t('automation.noDevice'))
    return
  }
  dumping.value = true
  // Open the picker immediately with a loading state — a dump can take
  // seconds and a silent button looks frozen.
  showElements.value = true
  try {
    const api = window.electronAPI as any
    const res = await api.callBackendAPI('device.ui_dump', {
      device_id: autoDeviceId.value,
      timeout_ms: 15000,
    })
    if (!res || !res.success) {
      showElements.value = false
      message.error(t('automation.dumpFailed', { msg: res?.error || 'unknown' }))
      return
    }
    elements.value = parseUiDump(res.xml || '')
  } catch (e: any) {
    showElements.value = false
    message.error(t('automation.dumpFailed', { msg: e?.message || String(e) }))
  } finally {
    dumping.value = false
  }
}

function onStepPick(payload: { index: number; mode: 'coord' | 'element' }) {
  pickTarget.value = payload
  void getElements()
}

/** 元素抽屉里选中一个元素：填充正在编辑的步骤（v2 模型） */
function applyElement(el: UiNode) {
  const target = pickTarget.value
  if (!target) {
    // should not happen (modal only opens from a form pick) — surface it
    // instead of failing silently if state ever desyncs
    message.warning(t('automation.pickNoTarget'))
    return
  }
  const steps = [...store.editor.steps]
  const s = { ...steps[target.index] } as any
  if (!s) return
  if (target.mode === 'coord') {
    const c = boundsCenter(el.bounds)
    if (!c) {
      message.error(t('automation.dumpFailed', { msg: 'no bounds' }))
      return
    }
    s.mode = 'coord'
    s.coord = c
    delete s.target
    delete s.ms
  } else {
    // element target: tap/wait switch modes; input keeps its optional focus
    if (s.action === 'tap' || s.action === 'wait') s.mode = 'element'
    s.target = {
      by: el.by,
      value: el.value,
      instance: s.target?.instance ?? 0,
      timeout_ms: s.target?.timeout_ms ?? elementTimeoutMs.value,
    }
    delete s.coord
    delete s.ms
  }
  steps[target.index] = s
  store.editor.steps = steps
  if (store.stepsView === 'json') store.syncJsonText()
  pickTarget.value = null
  showElements.value = false
  if (el.matchCount > 1) {
    message.warning(t('automation.matchWarning', { n: el.matchCount }))
  } else {
    message.success(el.label)
  }
}

// ---------------- import / export ----------------
async function exportConfig() {
  if (!store.projects.length) {
    message.warning(t('automation.exportEmpty'))
    return
  }
  const api = window.electronAPI as any
  if (!api || typeof api.showSaveDialog !== 'function') {
    message.error('save dialog unavailable')
    return
  }
  const res = await api.showSaveDialog({
    title: t('automation.export'),
    defaultPath: 'automation.json',
    filters: [{ name: 'JSON', extensions: ['json'] }],
  })
  if (!res || res.canceled || !res.filePath) return
  const content = JSON.stringify({ projects: store.projects }, null, 2)
  if (api.writeFile) {
    await api.writeFile(res.filePath, content)
  } else {
    message.error('writeFile unavailable')
    return
  }
  message.success(t('automation.exportSuccess', { path: res.filePath }))
}

async function importConfig() {
  if (runner.running) return
  const api = window.electronAPI as any
  if (!api || typeof api.showOpenDialog !== 'function') {
    message.error('open dialog unavailable')
    return
  }
  const res = await api.showOpenDialog({
    title: t('automation.import'),
    properties: ['openFile'],
    filters: [{ name: 'JSON', extensions: ['json'] }],
  })
  if (!res || res.canceled || !res.filePaths || !res.filePaths.length) return
  const path = res.filePaths[0]
  let text = ''
  try {
    text = api.readFile ? await api.readFile(path) : ''
  } catch (e: any) {
    message.error(t('automation.importFailed', { msg: e?.message || String(e) }))
    return
  }
  let parsed: any
  try {
    parsed = JSON.parse(text)
  } catch (e: any) {
    message.error(t('automation.importFailed', { msg: 'JSON: ' + (e?.message || e) }))
    return
  }
  if (!parsed || !Array.isArray(parsed.projects)) {
    message.error(t('automation.importFailed', { msg: 'missing projects[]' }))
    return
  }
  dialog.warning({
    title: t('automation.import'),
    content: t('automation.importConfirm'),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => {
      store.projects = parsed.projects
      store.selectedProjectId = ''
      store.selectedScriptId = ''
      store.loadEditorFromSelection()
      store.persist()
      message.success(t('automation.importSuccess'))
    },
  })
}

onMounted(() => {
  store.loadConfig()
})
</script>

<style scoped>
.auto-page { max-width: var(--page-max-width); margin: 0 auto; height: 100%; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; flex: none; }
.page-title {
  font-family: Inter, sans-serif; font-size: 22px; font-weight: 700;
  color: var(--app-text-primary); margin: 0; letter-spacing: -0.02em;
}
.page-subtitle { font-size: 13px; color: var(--app-text-muted); margin: 4px 0 0; }
.three-cols {
  flex: 1; display: grid;
  /* 列宽由 gridStyle 内联给定：两侧列可拖拽调宽（localStorage 持久化），
     中栏 minmax(0,1fr) 吸收剩余空间——1fr 的 min-width 是 auto，内容会顶开
     轨道压到相邻列，因此必须 minmax(0,1fr)。
     行高同理用 minmax(0,1fr) 锁死：否则某列内容一高，auto 行就顶破容器，
     溢出内容会让外层 .main-content 长出页面级滚动条。 */
  grid-template-rows: minmax(0, 1fr);
  gap: 0; min-height: 0; overflow: hidden;
}
.col-divider {
  cursor: col-resize;
  border-radius: 3px;
  transition: background 0.15s;
}
.col-divider:hover { background: var(--app-card-border); }
.col {
  background: var(--app-card-bg); border: 1px solid var(--app-card-border);
  border-radius: 10px; padding: 12px; display: flex; flex-direction: column; min-height: 0;
  min-width: 0;
  /* clip: a child that outgrows the column must scroll inside it, never
     paint over the neighbouring column or the run history below */
  overflow: hidden;
}
.col-head {
  display: flex; justify-content: flex-start; align-items: center; gap: 10px;
  font-size: 13px; font-weight: 600; color: var(--app-text-primary);
  margin-bottom: 10px;
}
/* NOTE: the "元素超时" (element default timeout) control used to sit on this
   row. It is gone from the UI — whichever row it lived on it read as clutter,
   and a per-step timeout can already be set inside the step editor. The
   underlying `elementTimeoutMs` state is KEPT (it is still the fallback used
   when building steps), only the control is removed. */
.col-empty { margin: auto; text-align: center; }
.muted { color: var(--app-text-muted); font-size: 12px; }

/* center editor */
.editor-title {
  display: flex;
  flex-direction: column;
  /* absorb the slack so the view switch is pinned to the right edge */
  flex: 1 1 auto;
  min-width: 0;
}
.view-switch { flex: none; }
.editor-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.editor-desc {
  font-size: 11px;
  font-weight: 400;
  color: var(--app-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.autosave-hint {
  flex: none;
  font-size: 11px;
  color: var(--app-text-muted);
}
.autosave-hint.saved { color: #18a058; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.4s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* right run console: controls / panel / history stacked with a uniform gap
   (the panel itself absorbs the slack) */
.col-right { gap: 8px; }
.steps-json { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 12px; }
.json-status { font-size: 11.5px; margin-top: 4px; }
.json-status.ok { color: #18a058; }
.json-status.bad { color: #d03050; }
.editor-body { overflow: auto; flex: 1; display: flex; flex-direction: column; gap: 10px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 12px; color: var(--app-text-muted); }
.steps-field { flex: 1; min-height: 0; min-width: 0; }
/* 工具行：只放右侧一组控件（切换 + 添加），整组贴右 */
.steps-head {
  display: flex; justify-content: flex-end; align-items: center;
  gap: 8px; flex-wrap: wrap;
}
.steps-head-right { display: flex; align-items: center; gap: 8px; }
/* 计数单独一行，落在工具行下面、贴着列表，左对齐 */
.steps-count-row { display: flex; align-items: center; }
.steps-count { font-size: 12px; color: var(--app-text-secondary); }
.add-step-btn { flex: none; }
.steps-editor { flex: 1; min-height: 0; min-width: 0; }

/* right run */
.docked-record { flex: 0 0 auto; border-top: 1px solid var(--app-card-border); padding-top: 10px; }
</style>
