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

    <div class="three-cols">
      <!-- ============ LEFT: project / script tree ============ -->
      <section class="col col-left">
        <div class="col-head">
          <span>{{ t('automation.projects') }}</span>
          <n-button size="tiny" tertiary type="primary" :disabled="running" @click="newProject">
            <template #icon><n-icon><FolderPlus /></n-icon></template>
          </n-button>
        </div>

        <n-empty v-if="!projects.length" :description="t('automation.noProject')" size="small" class="col-empty">
          <template #extra>
            <span class="muted">{{ t('automation.noProjectDesc') }}</span>
          </template>
        </n-empty>

        <div v-else class="tree">
          <div v-for="p in projects" :key="p.id" class="proj">
            <div class="proj-row" :class="{ active: p.id === selectedProjectId }">
              <div class="proj-name" @click="selectProject(p.id)">
                <n-icon size="14"><Box /></n-icon>
                <span class="name-line" :title="p.description ? `${p.name} · ${p.description}` : p.name">{{ p.name }}</span>
              </div>
              <div class="row-actions">
                <n-button size="tiny" text type="primary" :disabled="running" :title="t('automation.editInfo')" @click.stop="openProjectMeta(p)">
                  <template #icon><n-icon><Pencil /></n-icon></template>
                </n-button>
                <n-button size="tiny" text type="error" :disabled="running" @click.stop="deleteProject(p)">
                  <template #icon><n-icon><Trash2 /></n-icon></template>
                </n-button>
              </div>
            </div>
            <div v-if="p.description" class="row-desc" :title="p.description">{{ p.description }}</div>

            <div v-if="p.id === selectedProjectId" class="scripts">
              <div
                v-for="s in p.scripts"
                :key="s.id"
                class="script-row"
                :class="{ active: s.id === selectedScriptId }"
                @click="selectScript(p.id, s.id)"
              >
                <n-icon size="13"><FileText /></n-icon>
                <div class="script-name-wrap" :title="s.description ? `${s.name} · ${s.description}` : s.name">
                  <span class="name-line">{{ s.name }}</span>
                  <span v-if="s.description" class="script-desc">{{ s.description }}</span>
                </div>
                <n-button
                  size="tiny"
                  text
                  type="primary"
                  class="script-ops"
                  :disabled="running"
                  :title="t('automation.editInfo')"
                  @click.stop="openScriptMeta(p.id, s)"
                >
                  <template #icon><n-icon><Pencil /></n-icon></template>
                </n-button>
                <n-button
                  size="tiny"
                  text
                  type="error"
                  class="script-ops"
                  :disabled="running"
                  @click.stop="deleteScript(p.id, s.id)"
                >
                  <template #icon><n-icon><Trash2 /></n-icon></template>
                </n-button>
              </div>
              <n-button
                size="tiny"
                dashed
                block
                :disabled="running"
                @click="newScript(p.id)"
              >
                <template #icon><n-icon><FilePlus /></n-icon></template>
                {{ t('automation.newScript') }}
              </n-button>
            </div>
          </div>
        </div>
      </section>

      <!-- ============ CENTER: script editor ============ -->
      <section class="col col-center">
        <n-empty v-if="!selectedProjectId || !selectedScriptId" :description="t('automation.noSelection')" class="col-empty" />

        <template v-else>
          <div class="col-head">
            <span class="editor-title">
              <span class="editor-name">{{ selectedScript?.name }}</span>
              <span v-if="selectedScript?.description" class="editor-desc">{{ selectedScript.description }}</span>
            </span>
            <n-button size="small" type="primary" :disabled="running" @click="saveScript">
              <template #icon><n-icon><Save /></n-icon></template>
              {{ t('automation.save') }}
            </n-button>
          </div>

          <div class="editor-body">
            <div class="field steps-field">
              <div class="steps-head">
                <n-radio-group
                  size="small"
                  :value="stepsView"
                  :disabled="running"
                  @update:value="onSwitchView"
                >
                  <n-radio-button value="ui">{{ t('automation.viewSteps') }}</n-radio-button>
                  <n-radio-button value="json">{{ t('automation.viewJson') }}</n-radio-button>
                </n-radio-group>
              </div>

              <StepListEditor
                v-if="stepsView === 'ui'"
                v-model="editor.steps"
                v-model:selected-index="selectedStepIndex"
                :disabled="running"
                class="steps-editor"
                @record-request="onRecordRequest"
                @pick="onStepPick"
              />
              <template v-else>
                <n-input
                  v-model:value="stepsText"
                  type="textarea"
                  :autosize="{ minRows: 14, maxRows: 26 }"
                  :disabled="running"
                  class="steps-json"
                  @update:value="refreshJsonStatus"
                />
                <div class="json-status" :class="jsonError ? 'bad' : 'ok'">
                  <template v-if="jsonError">{{ t('automation.jsonInvalid', { msg: jsonError }) }}</template>
                  <template v-else>{{ t('automation.jsonOk', { n: stepCount }) }}</template>
                </div>
              </template>
            </div>
          </div>
        </template>
      </section>

      <!-- ============ RIGHT: record / run (mutually exclusive modes) ============ -->
      <section class="col col-right">
        <div class="col-head">
          <n-radio-group
            size="small"
            :value="rightMode"
            @update:value="onSwitchMode"
          >
            <n-radio-button value="record">{{ t('automation.record') }}</n-radio-button>
            <n-radio-button value="run">{{ t('automation.run') }}</n-radio-button>
          </n-radio-group>
        </div>

        <div class="run-bar">
          <n-select
            :value="autoDeviceId"
            :options="deviceOptions"
            size="small"
            :placeholder="t('automation.selectDevice')"
            @update:value="(v: string) => (autoDeviceId = v)"
          />
          <!-- 运行模式的操作按钮（录制模式的开始/停止在 RecordPanel 内，同一位置随模式切换） -->
          <template v-if="rightMode === 'run'">
            <n-checkbox v-model:checked="captureTraffic" size="small" class="capture-toggle">
              {{ t('automation.captureTraffic') }}
            </n-checkbox>
            <n-tooltip v-if="!running" :disabled="canRun" placement="top">
              <template #trigger>
                <n-button
                  type="primary"
                  size="small"
                  block
                  :disabled="!canRun"
                  @click="runScript"
                >
                  <template #icon><n-icon><Play /></n-icon></template>
                  {{ t('automation.run') }}
                </n-button>
              </template>
              {{ !autoDeviceId ? t('automation.noDevice') : t('automation.noScriptSelected') }}
            </n-tooltip>
            <n-button v-else type="warning" size="small" block @click="stopRun">
              <template #icon><n-icon><Square /></n-icon></template>
              {{ t('automation.stop') }}
            </n-button>
          </template>
        </div>

        <RecordPanel
          v-show="rightMode === 'record'"
          ref="recordPanelRef"
          :device-id="autoDeviceId"
          :disabled="running && !recording"
          :has-selection="selectedStepIndex >= 0"
          @recording-start="onRecStart"
          @recorded="onRecorded"
          @recording-end="onRecEnd"
        />

        <template v-if="rightMode === 'run'">
        <div class="result-block" v-if="runResult || liveSteps.length">
          <div class="result-summary">
            <n-tag v-if="runResult" :type="runResult.cancelled ? 'warning' : (runResult.success ? 'success' : 'error')" size="small">
              {{ runResult.cancelled ? t('automation.cancelled') : (runResult.success ? t('automation.success') : t('automation.failed')) }}
            </n-tag>
            <n-tag v-else type="info" size="small">{{ t('automation.running') }}</n-tag>
            <span class="sum-item">{{ t('automation.total') }}: {{ runResult ? (runResult.total ?? 0) : stepRows.length }}</span>
            <span class="sum-item ok">{{ t('automation.passed') }}: {{ stepPassed }}</span>
            <span class="sum-item bad">{{ t('automation.failed') }}: {{ stepFailed }}</span>
          </div>

          <div class="crash-note" v-if="runResult?.aborted_by_crash">
            <span class="crash-text">{{ t('automation.crashAborted') }}</span>
            <span v-if="runResult?.crash_log" class="crash-log">{{ t('automation.crashLog') }}: {{ runResult.crash_log }}</span>
          </div>

          <div class="crash-note" v-if="runResult?.traffic_log">
            <span class="crash-text">{{ t('automation.trafficRequests') }}: {{ runResult.traffic_requests ?? 0 }}</span>
            <span class="crash-log">{{ t('automation.trafficLog') }}: {{ runResult.traffic_log }}</span>
          </div>

          <div class="steps-result" ref="stepsScroll">
            <div v-for="st in stepRows" :key="st.index" class="step-line" :class="stepRowClass(st)">
              <span class="step-idx">#{{ st.index }}</span>
              <span class="step-act">{{ actLabel(st.action) }}</span>
              <span class="step-msg">{{ st.pending ? t('automation.stepPending') : (st.message || (st.ok ? 'ok' : 'fail')) }}</span>
              <span class="step-dur" v-if="st.duration_ms">{{ st.duration_ms }}ms</span>
            </div>
          </div>

          <div class="shots" v-if="screenshots.length">
            <div class="shots-title">{{ t('automation.screenshots') }}</div>
            <div class="shot-grid">
              <n-image
                v-for="(sp, i) in screenshots"
                :key="i"
                :src="fileUrl(sp)"
                width="96"
                height="170"
                object-fit="cover"
                :alt="sp"
              />
            </div>
          </div>
        </div>
        <n-empty v-else :description="t('automation.noResult')" size="small" class="col-empty" />

        <div class="log-head">{{ t('automation.runLog') }}</div>
        <n-scrollbar class="log-scroll" ref="logScroll">
          <pre class="log-box">{{ logsText }}</pre>
        </n-scrollbar>
        </template>
      </section>
    </div>

    <!-- ============ Element picker modal ============ -->
    <n-modal v-model:show="showElements" :title="t('automation.elements')" preset="card" style="width: 520px">
      <p class="muted">{{ t('automation.pickHint') }}</p>
      <n-empty v-if="!elements.length" :description="t('automation.noElements')" size="small" />
      <n-list v-else bordered class="elem-list">
        <n-list-item v-for="(el, i) in elements" :key="i" @click="applyElement(el)" class="elem-item">
          <div class="elem-main">
            <div class="elem-label-row">
              <span class="elem-label">{{ el.label }}</span>
              <span v-if="el.clickable" class="elem-click">{{ t('automation.clickable') }}</span>
              <span v-if="el.matchCount > 1" class="elem-multi">{{ t('automation.multiMatch', { n: el.matchCount }) }}</span>
            </div>
            <span class="elem-by">{{ el.by }} = {{ el.value }}</span>
          </div>
          <span class="elem-bounds">{{ el.bounds }}</span>
        </n-list-item>
      </n-list>
    </n-modal>

    <!-- ============ Project / script meta editor modal ============ -->
    <n-modal v-model:show="showMeta" :title="t('automation.editInfo')" preset="card" style="width: 440px">
      <div class="field">
        <label>{{ metaForm.kind === 'project' ? t('automation.projectName') : t('automation.scriptName') }}</label>
        <n-input v-model:value="metaForm.name" size="small" />
      </div>
      <div v-if="metaForm.kind === 'project'" class="field">
        <label>{{ t('automation.packageName') }}</label>
        <n-input v-model:value="metaForm.packageName" size="small" placeholder="com.example.app" />
      </div>
      <div class="field">
        <label>{{ t('automation.description') }}</label>
        <n-input
          v-model:value="metaForm.description"
          type="textarea"
          size="small"
          :autosize="{ minRows: 2, maxRows: 4 }"
        />
      </div>
      <template #footer>
        <n-space justify="end">
          <n-button size="small" @click="showMeta = false">{{ t('common.cancel') }}</n-button>
          <n-button size="small" type="primary" @click="saveMeta">{{ t('common.confirm') }}</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NInput,
  NSelect,
  NModal,
  NList,
  NListItem,
  NScrollbar,
  NEmpty,
  NIcon,
  NTooltip,
  NTag,
  NImage,
  NSpace,
  NRadioButton,
  NRadioGroup,
  useMessage,
  useDialog,
} from 'naive-ui'
import {
  Download,
  Upload,
  Trash2,
  Play,
  Square,
  FolderPlus,
  FilePlus,
  FileText,
  Pencil,
  Save,
  Box,
} from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import RecordPanel from '@components/automation/RecordPanel.vue'
import StepListEditor from '@components/automation/StepListEditor.vue'
import { stepActionLabel } from '@components/automation/stepMeta'
import { parseUiDump, boundsCenter, type UiNode } from '@components/automation/uiDump'
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
const store = useAutomationStore(() => runner.running.value)

const {
  projects,
  selectedProjectId,
  selectedScriptId,
  editor,
  stepsView,
  stepsText,
  jsonError,
  stepCount,
  selectedStepIndex,
  showMeta,
  metaForm,
  selectedScript,
  selectedProject,
  loadConfig,
  loadEditorFromSelection,
  syncJsonText,
  persist,
  onSwitchView,
  refreshJsonStatus,
  selectProject,
  selectScript,
  newProject,
  newScript,
  deleteProject,
  deleteScript,
  saveScript,
  saveMeta,
  openProjectMeta,
  openScriptMeta,
  onRecorded,
} = store
const {
  running,
  runResult,
  screenshots,
  liveSteps,
  stepRows,
  stepPassed,
  stepFailed,
  stepRowClass,
  runScript: startRun,
  stopRun,
} = runner
const logs = runner.logs
const logsText = computed(() => logs.value.join('\n'))

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
// Drop the selection when the device vanishes from the live list.
watch(() => deviceStore.devices, (list) => {
  if (autoDeviceId.value && !(list as any[]).some(d => d.id === autoDeviceId.value)) {
    autoDeviceId.value = ''
  }
}, { immediate: true })

const deviceOptions = computed(() =>
  deviceStore.devices.map((d: any) => ({
    label: `${d.name || d.id}${d.status ? ' (' + d.status + ')' : ''}`,
    value: d.id,
  })),
)

// Run is allowed only when both a device and a script are selected.
const canRun = computed(() => !!autoDeviceId.value && !!selectedScriptId.value)

/** 右栏二选一模式：录制 / 运行（步骤展示与运行日志共用这一块区域） */
const rightMode = ref<'record' | 'run'>('record')
const recording = ref(false)
const recordPanelRef = ref<InstanceType<typeof RecordPanel> | null>(null)

function onSwitchMode(v: string) {
  if (v === rightMode.value) return
  // 互斥：录制中不能切运行；脚本执行中不能切录制
  if (v === 'run' && recording.value) {
    message.warning(t('automation.recordStopFirst'))
    return
  }
  if (v === 'record' && running.value) {
    message.warning(t('automation.runStopFirst'))
    return
  }
  rightMode.value = v as 'record' | 'run'
}

/** 「添加步骤 → 录制片段…」：切到右栏录制模式采集 */
function onRecordRequest() {
  if (running.value && !recording.value) {
    message.warning(t('automation.runStopFirst'))
    return
  }
  rightMode.value = 'record'
  message.info(t('automation.recordSegmentHint'))
}

// Recording reuses the runner's `running` flag as the global busy signal —
// every busy-guard in the store/runner keys off it.
function onRecStart() {
  recording.value = true
  runner.running.value = true
}
function onRecEnd() {
  recording.value = false
  runner.running.value = false
}

// ---------------- run ----------------
async function runScript() {
  if (running.value) return
  if (!autoDeviceId.value) {
    message.error(t('automation.noDeviceSelectedRun'))
    return
  }
  if (!selectedScriptId.value) {
    message.warning(t('automation.noScriptSelected'))
    return
  }
  if (!store.commitEditor()) return
  const s = selectedScript.value
  if (!s || !s.steps.length) {
    message.warning(t('automation.noSteps'))
    return
  }
  try {
    await startRun({
      device_id: autoDeviceId.value,
      package_name: selectedProject.value?.package_name || '',
      steps: s.steps,
      capture_traffic: captureTraffic.value,
    })
  } catch (e: any) {
    message.error(e?.message || String(e))
  }
}

function actLabel(action: string): string {
  return stepActionLabel(action, t)
}

function fileUrl(p: string): string {
  if (!p) return ''
  if (p.startsWith('file://')) return p
  return 'file:///' + p.replace(/\\/g, '/')
}

// ---------------- element picker ----------------
const dumping = ref(false)
const showElements = ref(false)
const elements = ref<UiNode[]>([])
/** 元素抽屉始终处于“填充步骤”模式（由编辑表单的“获取界面元素”按钮打开） */
const pickTarget = ref<{ index: number; mode: 'coord' | 'element' } | null>(null)

async function getElements() {
  if (running.value) return
  if (!autoDeviceId.value) {
    message.error(t('automation.noDevice'))
    return
  }
  dumping.value = true
  try {
    const api = window.electronAPI as any
    const res = await api.callBackendAPI('device.ui_dump', {
      device_id: autoDeviceId.value,
      timeout_ms: 15000,
    })
    if (!res || !res.success) {
      message.error(t('automation.dumpFailed', { msg: res?.error || 'unknown' }))
      return
    }
    elements.value = parseUiDump(res.xml || '')
    showElements.value = true
  } catch (e: any) {
    message.error(t('automation.dumpFailed', { msg: e?.message || String(e) }))
  } finally {
    dumping.value = false
  }
}

function onStepPick(payload: { index: number; mode: 'coord' | 'element' }) {
  pickTarget.value = payload
  void getElements()
}

/** 元素抽屉里选中一个元素：填充正在编辑的步骤 */
function applyElement(el: UiNode) {
  const target = pickTarget.value
  if (!target) return
  const steps = [...editor.value.steps]
  const s = { ...steps[target.index] } as any
  if (!s) return
  if (target.mode === 'coord') {
    const c = boundsCenter(el.bounds)
    if (!c) {
      message.error(t('automation.dumpFailed', { msg: 'no bounds' }))
      return
    }
    s.x = c.x
    s.y = c.y
    delete s.by
    delete s.value
  } else {
    // input has no `mode` field — by/value is the optional focus tap
    if (s.action !== 'input') s.mode = 'element'
    s.by = el.by
    s.value = el.value
    if (s.timeout_ms === undefined) s.timeout_ms = 10000
    if (s.action === 'wait') delete s.ms
  }
  steps[target.index] = s
  editor.value.steps = steps
  if (stepsView.value === 'json') syncJsonText()
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
  if (!projects.value.length) {
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
  const content = JSON.stringify({ projects: projects.value }, null, 2)
  if (api.writeFile) {
    await api.writeFile(res.filePath, content)
  } else {
    message.error('writeFile unavailable')
    return
  }
  message.success(t('automation.exportSuccess', { path: res.filePath }))
}

async function importConfig() {
  if (running.value) return
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
      projects.value = parsed.projects
      selectedProjectId.value = ''
      selectedScriptId.value = ''
      loadEditorFromSelection()
      persist()
      message.success(t('automation.importSuccess'))
    },
  })
}

// auto-scroll refs (DOM anchors live in the template)
const logScroll = ref<any>(null)
const stepsScroll = ref<HTMLElement | null>(null)

// auto-scroll step results to bottom as rows stream in
watch(
  () => liveSteps.value.length,
  async () => {
    await nextTick()
    const el = stepsScroll.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

// auto-scroll log to bottom
watch(
  () => logs.value.length,
  async () => {
    await nextTick()
    const inst = logScroll.value?.instRef
    const el = inst?.$el as HTMLElement | undefined
    if (el) el.scrollTop = el.scrollHeight
  },
)

onMounted(() => {
  loadConfig()
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
  /* 中栏必须 minmax(0,1fr)：1fr 的 min-width 是 auto，内容（JSON 域/按钮行）
     会把轨道顶开压到相邻列上——这就是窄窗口下排版重叠的根因 */
  grid-template-columns: minmax(210px, 280px) minmax(0, 1fr) minmax(290px, 360px);
  gap: 14px; min-height: 0;
}
/* Responsive fallback: shrink side columns on narrower viewports so the
   editor column keeps usable width instead of being crushed. */
@media (max-width: 1180px) {
  .three-cols { grid-template-columns: minmax(190px, 230px) minmax(0, 1fr) minmax(270px, 300px); }
}
@media (max-width: 920px) {
  .three-cols { grid-template-columns: minmax(170px, 200px) minmax(0, 1fr) minmax(250px, 260px); gap: 10px; }
}
.col {
  background: var(--app-card-bg); border: 1px solid var(--app-card-border);
  border-radius: 10px; padding: 12px; display: flex; flex-direction: column; min-height: 0;
  min-width: 0;
}
.col-head {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px; font-weight: 600; color: var(--app-text-primary);
  margin-bottom: 10px;
}
.col-empty { margin: auto; text-align: center; }
.muted { color: var(--app-text-muted); font-size: 12px; }

/* left tree */
.tree { overflow: auto; flex: 1; }
.proj { margin-bottom: 8px; }
.proj-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 8px; border-radius: 8px; cursor: pointer;
}
.proj-row.active { background: var(--app-blue-bg); }
.proj-name { display: flex; align-items: center; gap: 6px; font-weight: 600; font-size: 13px; color: var(--app-text-primary); overflow: hidden; }
.proj-name span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row-actions { display: flex; gap: 2px; opacity: 0; }
.proj-row:hover .row-actions { opacity: 1; }
.scripts { margin: 4px 0 8px 18px; display: flex; flex-direction: column; gap: 3px; }
.script-row {
  display: flex; align-items: center; gap: 6px; padding: 5px 8px; border-radius: 7px;
  cursor: pointer; font-size: 12.5px; color: var(--app-text-secondary);
}
.script-row.active { background: var(--app-blue-bg); color: var(--app-text-primary); }

/* left tree */
.row-desc {
  font-size: 11px;
  color: var(--app-text-muted);
  padding: 0 10px 2px 30px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.script-name-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}
.script-row .name-line,
.proj-name .name-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.script-desc {
  font-size: 10.5px;
  color: var(--app-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.script-ops { opacity: 0; }
.script-row:hover .script-ops { opacity: 1; }

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
.steps-json { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 12px; }
.json-status { font-size: 11.5px; margin-top: 4px; }
.json-status.ok { color: #18a058; }
.json-status.bad { color: #d03050; }
.editor-body { overflow: auto; flex: 1; display: flex; flex-direction: column; gap: 10px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 12px; color: var(--app-text-muted); }
.steps-field { flex: 1; min-height: 0; min-width: 0; }
.steps-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; }
.steps-editor { flex: 1; min-height: 0; min-width: 0; }

/* right run */
.run-bar { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; min-width: 0; }
.result-block { flex: 0 0 auto; }
.result-summary { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 8px; }
.sum-item { font-size: 12px; color: var(--app-text-secondary); }
.sum-item.ok { color: #18a058; }
.sum-item.bad { color: #d03050; }
.crash-note { display: flex; flex-direction: column; gap: 2px; font-size: 12px; margin: 6px 0; }
.crash-text { color: #d03050; font-weight: 600; }
.crash-log { color: var(--app-text-muted); word-break: break-all; }
.steps-result { max-height: 200px; overflow: auto; border: 1px solid var(--app-card-border); border-radius: 8px; padding: 6px; }
.step-line { display: flex; gap: 8px; align-items: baseline; font-size: 12px; padding: 2px 0; border-bottom: 1px dashed var(--app-card-border); }
.step-line.ok .step-idx { color: #18a058; }
.step-line.bad .step-idx { color: #d03050; }
.step-line.pending .step-idx { color: #2080f0; }
.step-line.pending .step-msg { color: #2080f0; font-style: italic; }
.step-idx { font-weight: 600; }
.step-act { color: var(--app-text-primary); font-weight: 500; }
.step-msg { color: var(--app-text-muted); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.step-dur { color: var(--app-text-muted); font-size: 11px; }
.shots { margin-top: 10px; }
.shots-title { font-size: 12px; color: var(--app-text-secondary); margin-bottom: 6px; }
.shot-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.log-head { font-size: 12px; color: var(--app-text-muted); margin: 12px 0 4px; }
.log-scroll { flex: 1; min-height: 120px; border: 1px solid var(--app-card-border); border-radius: 8px; background: #0f1115; }
.log-box {
  margin: 0; padding: 10px; color: #c8d0da; font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 11.5px; line-height: 1.5; white-space: pre-wrap; word-break: break-all;
}
.elem-list { max-height: 360px; overflow: auto; }
.elem-item { cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.elem-item:hover { background: var(--app-blue-bg); }
.elem-main { display: flex; flex-direction: column; min-width: 0; }
.elem-label-row { display: flex; align-items: center; gap: 6px; min-width: 0; }
.elem-label { font-size: 13px; color: var(--app-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.elem-click { flex: 0 0 auto; font-size: 10px; line-height: 16px; color: var(--app-green); border: 1px solid currentColor; border-radius: 3px; padding: 0 4px; }
.elem-multi { flex: 0 0 auto; font-size: 10px; line-height: 16px; color: var(--app-warning, #d97706); border: 1px solid currentColor; border-radius: 3px; padding: 0 4px; }
.elem-by { font-size: 11px; color: var(--app-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.elem-bounds { font-size: 10.5px; color: var(--app-text-muted); flex: 0 0 auto; }
</style>
