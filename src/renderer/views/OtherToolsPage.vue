<template>
  <div class="auto-page app-page">
    <div class="app-page-header">
      <div>
        <h1 class="app-page-title">{{ t('automation.title') }}</h1>
        <p class="app-page-sub">{{ t('automation.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <n-button size="small" type="primary" secondary :aria-label="t('automation.toolsInstall')" @click="toolInstallVisible = true">
          <template #icon><n-icon><Wrench /></n-icon></template>
          {{ t('automation.toolsInstall') }}
        </n-button>
      </div>
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
              <!-- 工具行：视图切换靠左、计数贴右（计数原来独占一行，并进这里，
                   腾出的高度给下面的「插入位」，整体净高度不变） -->
              <div class="steps-head">
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
                <span class="steps-count">{{ t('automation.stepCountLabel', { n: stepCountDisplay }) }}</span>
              </div>

              <!-- 「插入位」：站在列表顶部 = 新内容的落点。和行内「+」（落在该行
                   下方）同一套心智模型——按钮在哪，新步骤/录制片段就插在哪。
                   顶部入口一律插到开头，所以固定传 0。 -->
              <n-dropdown
                v-if="store.stepsView === 'ui'"
                trigger="click"
                placement="bottom-start"
                :options="addOptions"
                :disabled="runner.running"
                @select="(key: string | number) => onAdd(String(key), 0)"
              >
                <button class="insert-top" type="button" :disabled="runner.running">
                  <n-icon size="14"><Plus /></n-icon>
                  <span>{{ t('automation.insertStart') }}</span>
                </button>
              </n-dropdown>

              <StepListEditor
                v-if="store.stepsView === 'ui'"
                ref="stepListRef"
                v-model="store.editor.steps"
                v-model:selected-index="store.selectedStepIndex"
                :disabled="runner.running"
                :default-timeout="elementTimeoutMs"
                :can-grab="!!autoDeviceId"
                :add-options="addOptions"
                class="steps-editor"
                @pick="onStepPick"
                @grab-activity="onGrabActivity"
                @insert-below="(p: { index: number; key: string }) => onAdd(p.key, p.index + 1)"
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

          <!-- 录制面板：改成弹窗。原来停靠在编辑区下方会跟步骤列表抢垂直空间，
               而录制本身是一次性的模态活动（开始 → 看实时步骤流 → 停止 → 插入） -->
          <n-modal
            v-model:show="recordPanelOpen"
            preset="card"
            style="width: 560px"
          >
            <RecordPanel
              ref="recordPanelRef"
              :device-id="autoDeviceId"
              :disabled="runner.running && !recording"
              :has-selection="store.selectedStepIndex >= 0"
              :default-insert-at="recordInsertAt"
              @recording-start="onRecStart"
              @recorded="store.onRecorded"
              @recording-end="onRecEnd"
              @close="recordPanelOpen = false"
            />
          </n-modal>
        </template>
      </section>

      <div class="col-divider" @pointerdown.prevent="startResize('right', $event)" />

      <!-- ============ RIGHT: run console ============ -->
      <!-- 控制区 + 运行面板。次级入口（运行设置 / 运行记录）收进控制区最右的
           「功能」菜单，各自开弹窗 —— 右栏的常驻高度全部留给产出的运行面板。 -->
      <section class="col col-right">
        <RunControls
          v-model:auto-device-id="autoDeviceId"
          v-model:capture-traffic="captureTraffic"
          v-model:traffic-host-filter="trafficHostFilter"
          :running="runner.running"
          :can-run="canRun"
          :hints="runHints"
          :capture-unavailable="captureUnavailable"
          :history-count="runs.length"
          @run="runScript"
          @stop="runner.stopRun"
          @open-history="showHistory = true"
        />
        <RunPanel
          :running="runner.running"
          :run-result="runner.runResult"
          :live-steps="runner.liveSteps"
          :logs="runner.logs"
          :screenshots="runner.screenshots"
          :run-started-ts="runner.runStartedTs"
          :live-traffic="liveTraffic"
          :report="viewingReport"
          :exporting="exporting"
          @open-file="openReportFile"
          @download-report="downloadRunReport"
          @close-report="closeReport"
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

    <!-- ============ Screenshot coordinate picker modal ============ -->
    <ScreenshotPickerModal
      v-model:show="showShotPicker"
      :device-id="autoDeviceId"
      @apply="applyShotCoords"
    />

    <!-- ============ Run history dialog ============ -->
    <!-- 从「功能」菜单打开；点某一条会恢复进右栏面板并自动关掉本弹窗，
         删除某一条则保持打开（连续清理）。列表在弹窗里可以给到 60vh。 -->
    <n-modal
      v-model:show="showHistory"
      preset="card"
      :title="t('automation.runHistory')"
      style="width: 520px"
    >
      <div class="history-dialog">
        <RunHistory
          :runs="runs"
          :loading="runsLoading"
          :selected-task-id="viewingReport?.task_id || ''"
          @refresh="fetchRuns"
          @select="onSelectRunFromDialog"
          @remove="onDeleteRun"
        />
      </div>
    </n-modal>

    <!-- ============ Tool install modal (traffic capture / ADBKeyBoard) ============ -->
    <ToolInstallModal
      v-model:show="toolInstallVisible"
      :device-id="autoDeviceId"
      @changed="onToolInstallChanged"
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

// 「添加步骤」的 + 号 —— 之前漏了这行 import，模板里的 <Plus /> 解析不到
// 组件，图标槽渲染成空（按钮看起来没有图标）
import { Plus, Wrench } from 'lucide-vue-next'

import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import type { TrafficStatus, ImeStatus } from '@services/AutomationService'
import RecordPanel from '@components/automation/RecordPanel.vue'
import StepListEditor from '@components/automation/StepListEditor.vue'
import ProjectTree from '@components/automation/ProjectTree.vue'
import RunControls from '@components/automation/RunControls.vue'
import RunPanel from '@components/automation/RunPanel.vue'
import RunHistory from '@components/automation/RunHistory.vue'
import ToolInstallModal from '@components/automation/ToolInstallModal.vue'
import ElementPickerModal from '@components/automation/ElementPickerModal.vue'
import ScreenshotPickerModal from '@components/automation/ScreenshotPickerModal.vue'
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
// Traffic capture (mitmdump) — persisted like the device selection so the
// run-settings dialog doesn't reset on every session (the settings button's
// tooltip + the hints keep an active capture visible). The backend still
// restores the device proxy in a finally block on every exit path.
const captureTraffic = ref(localStorage.getItem('bt:autoCaptureTraffic') === '1')
watch(captureTraffic, (v) => {
  try { localStorage.setItem('bt:autoCaptureTraffic', v ? '1' : '0') } catch {}
})
// Filter conditions, comma-joined (the tags input in the run settings dialog
// edits this string). Persisted alongside the switch.
const trafficHostFilter = ref(localStorage.getItem('bt:autoTrafficHostFilter') || '')
watch(trafficHostFilter, (v) => {
  try { localStorage.setItem('bt:autoTrafficHostFilter', v) } catch {}
})

// ---------------- preflight capability probes (read-only) ----------------
// mitmproxy is PC-side (global); ADBKeyBoard is device-side (per device).
// Both surface as non-blocking hints under the run controls — they never
// block a run, the backend error messages carry the final word.
const trafficStatus = ref<TrafficStatus | null>(null)
const imeStatus = ref<ImeStatus | null>(null)

async function refreshTrafficStatus(force = false) {
  try {
    const svc = await serviceManager.getService('automation')
    trafficStatus.value = await svc.getTrafficStatus(force)
  } catch { /* 探测失败 = 未知态，不给提示（设置页有完整状态展示） */ }
}

async function refreshImeStatus(deviceId: string) {
  imeStatus.value = null
  if (!deviceId) return
  try {
    const svc = await serviceManager.getService('automation')
    imeStatus.value = await svc.getImeStatus(deviceId)
  } catch { /* best-effort */ }
}

// ---------------- tool install entry (page header button) ----------------
const toolInstallVisible = ref(false)

/** 工具安装弹窗报成功：清探测缓存 → force 重探两侧，runHints 与状态行即时更新。 */
async function onToolInstallChanged() {
  try {
    const svc = await serviceManager.getService('automation')
    svc.clearTrafficCache()
  } catch { /* best-effort */ }
  await refreshTrafficStatus(true)
  await refreshImeStatus(autoDeviceId.value)
}

// Mirrors backend input.py: `any(ord(c) > 0x7F for c in text)` — the exact
// condition that makes the backend require ADBKeyBoard. Kept char-by-char
// equivalent on purpose; changing one side without the other desyncs the hint.
function hasNonAsciiInput(steps: Step[]): boolean {
  return steps.some(s => {
    if (s.action !== 'input' || !s.text) return false
    for (const c of s.text) {
      if (c.charCodeAt(0) > 0x7F) return true
    }
    return false
  })
}

// Capture requested but this machine can't do it (mitmproxy missing / Python
// version mismatch). Surfaced twice on purpose: under the run row (visible
// when the dialog is closed) and inside the run settings dialog itself —
// that's where the capture switch lives now, so the warning must be visible
// while the user is toggling it (the row is masked then).
const captureUnavailable = computed(
  () => !!captureTraffic.value && !!trafficStatus.value && !trafficStatus.value.ready,
)

const runHints = computed(() => {
  const hints: string[] = []
  if (captureUnavailable.value) {
    hints.push(t('automation.captureTrafficUnavailable'))
  }
  if (autoDeviceId.value && imeStatus.value && !imeStatus.value.installed
      && hasNonAsciiInput(store.editor.steps)) {
    hints.push(t('automation.imeUnavailable'))
  }
  return hints
})

// Probes: traffic status once (service caches), IME per device selection.
// Toggling capture on re-checks (cached) so a just-installed mitmproxy is seen.
watch(captureTraffic, (on) => { if (on) void refreshTrafficStatus() })
watch(autoDeviceId, (id) => { void refreshImeStatus(id) }, { immediate: true })
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

function onAdd(action: string, atIndex = 0) {
  if (action === RECORD_KEY) {
    // 顶部「插入位」传 0 → 插到开头；行内「+」传 i+1 → 插到第 i 行下方。
    // 录制片段走 store.onRecorded：'start' 插开头、'after' 插在选中行之后。
    onRecordRequest(atIndex > 0 ? atIndex - 1 : null)
    return
  }
  const at = atIndex
  const list = [...store.editor.steps]
  list.splice(at, 0, defaultStep(action as StepAction))
  store.editor.steps = list
  if (store.stepsView === 'json') store.syncJsonText()
  // 新行成为选中行，并直接进入编辑状态
  store.selectedStepIndex = at
  nextTick(() => stepListRef.value?.openEditor(at))
}

/** 录制面板停靠开关（中栏编辑器下方）；入口 = 顶部「插入位」或行内「+」，
 * 关闭走面板自带的 X 按钮 */
const recordPanelOpen = ref(false)
const recording = ref(false)
const recordPanelRef = ref<InstanceType<typeof RecordPanel> | null>(null)
/** 录制片段的落点：由**入口**决定（顶部 = 开头；行内「+」= 该行下方），
 *  交给 RecordPanel 当默认值 */
const recordInsertAt = ref<'start' | 'after'>('start')

/** 录制片段入口：targetRow = null → 插到开头（顶部「插入位」）；
 *  传行下标 → 插在该行下方（行内「+」，靠选中行 + onRecorded 的 'after' 分支）。 */
function onRecordRequest(targetRow: number | null = null) {
  if (runner.running && !recording.value) {
    message.warning(t('automation.runStopFirst'))
    return
  }
  recordInsertAt.value = targetRow === null ? 'start' : 'after'
  if (targetRow !== null) store.selectedStepIndex = targetRow
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
/** 运行记录弹窗（从运行控件旁的「功能」菜单打开） */
const showHistory = ref(false)

async function fetchRuns() {
  runsLoading.value = true
  try {
    const api = window.electronAPI
    const res = await api.callBackendAPI('automation.list_runs', {})
    runs.value = res?.runs || []
  } catch {
    /* history is best-effort */
  } finally {
    runsLoading.value = false
  }
}
onMounted(() => { void fetchRuns() })

/** 从运行记录弹窗里选一条：把运行恢复进面板后**关掉弹窗**，
 *  否则报告被弹窗盖住 —— 这一步不能省。 */
async function onSelectRunFromDialog(taskId: string) {
  await onSelectRun(taskId)
  showHistory.value = false
}

/** 点运行记录 → 把那次运行的报告恢复到页面里 */
async function onSelectRun(taskId: string) {
  try {
    const api = window.electronAPI
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

/** 实时视图的抓包明细：流式不推，跑完后从落盘的 jsonl 补读一次 */
const liveTraffic = ref<any[]>([])

async function loadFinishedTraffic(taskId: string) {
  try {
    const api = window.electronAPI
    const res = await api.callBackendAPI('automation.read_run', { task_id: taskId, traffic_limit: 500 })
    // 只有还是同一次运行的结果时才填充（防止慢返回覆盖掉新开跑的空态）
    if (res?.success && res.report
        && String(runner.runResult?.task_id || runner.taskId || '') === taskId) {
      // `report` is `Record<string, unknown>` per the IPC contract, so the
      // traffic slice needs an explicit array narrowing before it can be
      // assigned to the `any[]` ref.
      const traffic = res.report.traffic
      liveTraffic.value = Array.isArray(traffic) ? traffic : []
    }
  } catch { /* 明细拉不到就空着，计数（traffic_requests）还在 */ }
}

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
  // 报告落盘了就把抓包明细补进实时视图 —— 「请求」页签跑完才有数据靠的就是这一步
  if (persisted) void loadFinishedTraffic(taskId)
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
      const api = window.electronAPI
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

const exporting = ref(false)

/** 内置 API：导出 HTML（始终在运行目录里留一份归档，返回其路径） */
async function buildRunReportHtml(taskId: string, target = ''): Promise<string> {
  const api = window.electronAPI
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
    // reveal:false → 系统默认程序真正打开（.html → 浏览器）；缺省会变成
    // 「在资源管理器中显示」——openPath 主进程对文件的历史语义就是 reveal
    await (window.electronAPI as any)?.openPath?.(path, { reveal: false })
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
  const api = window.electronAPI
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
    liveTraffic.value = []
    await runner.runScript({
      device_id: autoDeviceId.value,
      package_name: store.selectedProject?.package_name || '',
      steps: s.steps,
      capture_traffic: captureTraffic.value,
      traffic_host_filter: trafficHostFilter.value.trim(),
    })
  } catch (e: any) {
    message.error(e?.message || String(e))
  } finally {
    // 无论成功、失败还是取消，都要把「刚跑完的那条」对账进列表 —— report.json
    // 落在 complete 之后，所以这里必须轮询而不是只刷一次。
    // 但 IPC/流层就失败（没收到 complete、不会有落盘记录）时轮询纯属空转，
    // 还会让刷新按钮连闪 20 次 —— 只有真跑完过才对账。
    if (runner.runResult) void reconcileFinishedRun()
  }
}

// ---------------- element picker / screenshot picker ----------------
const dumping = ref(false)
const showElements = ref(false)
const elements = ref<UiNode[]>([])
/** 抽屉始终处于“填充步骤”模式（由编辑表单的拾取按钮打开）：
 *  element → UI dump 抽屉，screenshot → 截图取点弹窗，coord 为遗留分支 */
const pickTarget = ref<{ index: number; mode: 'coord' | 'element' | 'screenshot' } | null>(null)
const showShotPicker = ref(false)

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
    const api = window.electronAPI
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

function onStepPick(payload: { index: number; mode: 'coord' | 'element' | 'screenshot' }) {
  pickTarget.value = payload
  // screenshot pick: the modal captures + shows on open, then reports coords
  if (payload.mode === 'screenshot') {
    showShotPicker.value = true
    return
  }
  void getElements()
}

/** 截图上点选一个坐标：写入 coord 模式步骤（与 applyElement 的 coord 分支
 *  同样的写法 —— 换 mode、清 target/ms 防脏字段） */
function applyShotCoords(c: { x: number; y: number }) {
  const target = pickTarget.value
  if (!target) {
    message.warning(t('automation.pickNoTarget'))
    return
  }
  const steps = [...store.editor.steps]
  const s = { ...steps[target.index] } as any
  if (!s) return
  s.mode = 'coord'
  s.coord = { x: c.x, y: c.y }
  delete s.target
  delete s.ms
  steps[target.index] = s
  store.editor.steps = steps
  if (store.stepsView === 'json') store.syncJsonText()
  pickTarget.value = null
  showShotPicker.value = false
  message.success(`${c.x}, ${c.y}`)
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

/**
 * assert_activity「抓取当前」：页面持有设备 id 与后端调用（表单只发事件），
 * 抓住设备当前前台 Activity 后写回**正在编辑的那一步**。写回路径与
 * applyElement 完全一致（复制步骤数组 → 替换该行 → 回写 editor.steps →
 * JSON 视图同步），保证自动保存/运行都拿到新值。探测失败只弹错，不改字段。
 */
async function onGrabActivity(payload: { index: number }) {
  const idx = payload?.index ?? store.selectedStepIndex
  const step = store.editor.steps[idx]
  if (!step) return
  if (!autoDeviceId.value) {
    message.error(t('automation.noDevice'))
    return
  }
  try {
    const api = window.electronAPI
    const res = await api.callBackendAPI('device.current_activity', {
      device_id: autoDeviceId.value,
      timeout_ms: 3000,
    })
    if (!res || !res.success) {
      message.error(res?.error || 'grab activity failed')
      return
    }
    const steps = [...store.editor.steps]
    steps[idx] = { ...steps[idx], activity: res.activity }
    store.editor.steps = steps
    if (store.stepsView === 'json') store.syncJsonText()
  } catch (e: any) {
    message.error(e?.message || String(e))
  }
}

onMounted(() => {
  store.loadConfig()
})
</script>

<style scoped>
.auto-page { height: 100%; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
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
  font-size: var(--app-font-size-md); font-weight: 600; color: var(--app-text-primary);
  margin-bottom: 10px;
}
/* NOTE: the "元素超时" (element default timeout) control used to sit on this
   row. It is gone from the UI — whichever row it lived on it read as clutter,
   and a per-step timeout can already be set inside the step editor. The
   underlying `elementTimeoutMs` state is KEPT (it is still the fallback used
   when building steps), only the control is removed. */
.col-empty { margin: auto; text-align: center; }

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
  font-size: var(--app-font-size-md);
  font-weight: 600;
  color: var(--app-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.editor-desc {
  font-size: var(--app-font-size-xs);
  font-weight: 400;
  color: var(--app-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.autosave-hint {
  flex: none;
  font-size: var(--app-font-size-xs);
  color: var(--app-text-muted);
}
.autosave-hint.saved { color: var(--app-green); }
.fade-enter-active, .fade-leave-active { transition: opacity 0.4s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* right run console: controls / panel / history stacked with a uniform gap
   (the panel itself absorbs the slack) */
.col-right { gap: 8px; }
.steps-json { font-family: var(--app-font-mono); font-size: var(--app-font-size-sm); }
.json-status { font-size: var(--app-font-size-sm); margin-top: 4px; }
.json-status.ok { color: var(--app-green); }
.json-status.bad { color: var(--app-red); }
.editor-body { overflow: auto; flex: 1; display: flex; flex-direction: column; gap: 10px; scrollbar-gutter: stable; overscroll-behavior: contain; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: var(--app-font-size-sm); color: var(--app-text-muted); }
.steps-field { flex: 1; min-height: 0; min-width: 0; }
/* 工具行：视图切换靠左、计数贴右（两端撑开） */
.steps-head {
  display: flex; justify-content: space-between; align-items: center;
  gap: 8px; flex-wrap: wrap;
}
.steps-count { font-size: var(--app-font-size-sm); color: var(--app-text-secondary); }
/* 「插入位」：列表顶上的一条虚线幽灵行。它的位置就是落点，所以不放进工具行；
   放在列表滚动区之外 —— 列表滚起来时它始终可见，插到开头永远够得着。 */
.insert-top {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  width: 100%; margin-bottom: 5px; padding: 5px 8px;
  font-family: inherit; font-size: var(--app-font-size-sm);
  color: var(--app-text-muted); cursor: pointer;
  background: transparent;
  border: 1px dashed var(--app-card-border); border-radius: 8px;
  transition: color 0.13s, border-color 0.13s, background 0.13s;
}
.insert-top:hover:not(:disabled) {
  color: var(--app-blue); border-color: var(--app-blue);
  background: var(--app-blue-bg);
}
.insert-top:disabled { opacity: 0.5; cursor: not-allowed; }
.steps-editor { flex: 1; min-height: 0; min-width: 0; }
/* 页头右侧动作区：.app-page-header 已是 flex + space-between，这里只补间距 */
.header-actions { flex: none; display: flex; align-items: center; gap: 8px; }

/* 运行记录弹窗：列表在弹窗里可以给到接近整屏（右栏常驻时只有 140px） */
.history-dialog :deep(.rh-list) { max-height: 60vh; }
</style>
