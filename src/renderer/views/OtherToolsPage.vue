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
            <!-- 默认超时是脚本编辑侧的东西：元素模式的步骤没显式填 timeout 时用它 -->
            <div class="head-timeout">
              <span class="ht-label">{{ t('automation.elementTimeout') }}</span>
              <n-input-number
                :value="elementTimeoutMs"
                size="tiny"
                :min="500"
                :max="120000"
                :step="1000"
                :disabled="runner.running"
                class="ht-ctl"
                @update:value="(v: number | null) => (elementTimeoutMs = clampTimeout(v ?? 10000))"
              />
              <span class="ht-unit">ms</span>
            </div>
            <transition name="fade">
              <span v-if="store.savedFlash" class="autosave-hint saved">{{ t('automation.savedNow') }}</span>
            </transition>
          </div>

          <div class="editor-body">
            <div class="field steps-field">
              <!-- 统一头行：左侧步骤计数，右侧 添加步骤 + 视图切换 -->
              <div class="steps-head">
                <span class="steps-count">{{ t('automation.stepCountLabel', { n: stepCountDisplay }) }}</span>
                <div class="steps-head-right">
                  <n-dropdown
                    trigger="click"
                    placement="bottom-end"
                    :options="addOptions"
                    :disabled="runner.running || store.stepsView !== 'ui'"
                    @select="onAdd"
                  >
                    <n-button size="tiny" type="primary" dashed :disabled="runner.running || store.stepsView !== 'ui'">
                      <template #icon><n-icon><Plus /></n-icon></template>
                      {{ t('automation.addStep') }}
                    </n-button>
                  </n-dropdown>
                  <n-radio-group
                    size="small"
                    :value="store.stepsView"
                    :disabled="runner.running"
                    @update:value="store.onSwitchView"
                  >
                    <n-radio-button value="ui">{{ t('automation.viewSteps') }}</n-radio-button>
                    <n-radio-button value="json">{{ t('automation.viewJson') }}</n-radio-button>
                  </n-radio-group>
                </div>
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
      <section class="col col-right">
        <div class="right-head">
          <span class="right-title">{{ t('automation.runResultTitle') }}</span>
        </div>
        <RunControls
          v-model:auto-device-id="autoDeviceId"
          v-model:capture-traffic="captureTraffic"
          :running="runner.running"
          :can-run="canRun"
          @run="runScript"
          @stop="runner.stopRun"
        />
        <!-- 运行记录常驻展开：点一条即把那次运行恢复到下面的区域 -->
        <RunHistory
          :runs="runs"
          :loading="runsLoading"
          :selected-task-id="viewingReport?.task_id || ''"
          @refresh="fetchRuns"
          @select="onSelectRun"
          @remove="onDeleteRun"
        />
        <!-- 报告视图：步骤 + 请求 + 截图同一条时间线，可浏览器打开 / 下载 -->
        <RunReport
          v-if="viewingReport"
          :report="viewingReport"
          :exporting="exporting"
          @close="closeReport"
          @open-file="openReportFile"
          @download="downloadRunReport"
        />
        <!-- 实时/最近一次运行：运行中看步骤与日志，结束后给报告按钮 -->
        <ResultPanel
          v-else
          :running="runner.running"
          :run-result="runner.runResult"
          :live-steps="runner.liveSteps"
          :screenshots="runner.screenshots"
          :logs="runner.logs"
          @open-report="onOpenReport"
          @download-report="downloadRunReport"
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
  NInputNumber,
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
import ResultPanel from '@components/automation/ResultPanel.vue'
import RunReport from '@components/automation/RunReport.vue'
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

// refresh the list when a run completes — the new run must show up as a record
watch(() => runner.runResult, () => {
  if (runner.runResult) void fetchRuns()
})

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
.auto-page { max-width: var(--page-max-width); margin: 0 auto; height: 100%; display: flex; flex-direction: column; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
.page-title {
  font-family: Inter, sans-serif; font-size: 22px; font-weight: 700;
  color: var(--app-text-primary); margin: 0; letter-spacing: -0.02em;
}
.page-subtitle { font-size: 13px; color: var(--app-text-muted); margin: 4px 0 0; }
.three-cols {
  flex: 1; display: grid;
  /* 列宽由 gridStyle 内联给定：两侧列可拖拽调宽（localStorage 持久化），
     中栏 minmax(0,1fr) 吸收剩余空间——1fr 的 min-width 是 auto，内容会顶开
     轨道压到相邻列，因此必须 minmax(0,1fr) */
  gap: 0; min-height: 0;
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
}
.col-head {
  display: flex; justify-content: flex-start; align-items: center; gap: 10px;
  font-size: 13px; font-weight: 600; color: var(--app-text-primary);
  margin-bottom: 10px;
}
/* script-level default timeout — lives on the script page, not the run page */
.head-timeout {
  display: flex; align-items: center; gap: 5px;
  margin-left: auto; flex: none; font-weight: 400;
}
.ht-label { font-size: 11px; color: var(--app-text-muted); white-space: nowrap; }
.ht-ctl { width: 96px; }
.ht-unit { font-size: 11px; color: var(--app-text-muted); }
.col-empty { margin: auto; text-align: center; }
.muted { color: var(--app-text-muted); font-size: 12px; }

/* center editor */
.editor-title {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
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

/* right run console */
.right-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}
.right-title { font-size: 12px; font-weight: 600; color: var(--app-text-primary); }
.steps-json { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 12px; }
.json-status { font-size: 11.5px; margin-top: 4px; }
.json-status.ok { color: #18a058; }
.json-status.bad { color: #d03050; }
.editor-body { overflow: auto; flex: 1; display: flex; flex-direction: column; gap: 10px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 12px; color: var(--app-text-muted); }
.steps-field { flex: 1; min-height: 0; min-width: 0; }
.steps-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; }
.steps-count { font-size: 12px; color: var(--app-text-muted); }
.steps-head-right { display: flex; align-items: center; gap: 8px; }
.steps-editor { flex: 1; min-height: 0; min-width: 0; }

/* right run */
.docked-record { flex: 0 0 auto; border-top: 1px solid var(--app-card-border); padding-top: 10px; }
</style>
