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
      <ProjectTree :store="store" :running="runner.running" />

      <!-- ============ CENTER: script editor ============ -->
      <section class="col col-center">
        <n-empty v-if="!store.selectedProjectId || !store.selectedScriptId" :description="t('automation.noSelection')" class="col-empty" />

        <template v-else>
          <div class="col-head">
            <span class="editor-title">
              <span class="editor-name">{{ store.selectedScript?.name }}</span>
              <span v-if="store.selectedScript?.description" class="editor-desc">{{ store.selectedScript.description }}</span>
            </span>
            <n-button size="small" type="primary" :disabled="runner.running" @click="store.saveScript">
              <template #icon><n-icon><Save /></n-icon></template>
              {{ t('automation.save') }}
            </n-button>
          </div>

          <div class="editor-body">
            <div class="field steps-field">
              <div class="steps-head">
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

              <StepListEditor
                v-if="store.stepsView === 'ui'"
                v-model="store.editor.steps"
                v-model:selected-index="store.selectedStepIndex"
                :disabled="runner.running"
                class="steps-editor"
                @record-request="onRecordRequest"
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
                <div class="json-status" :class="store.jsonError ? 'bad' : 'ok'">
                  <template v-if="store.jsonError">{{ t('automation.jsonInvalid', { msg: store.jsonError }) }}</template>
                  <template v-else>{{ t('automation.jsonOk', { n: store.stepCount }) }}</template>
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
          <!-- 运行模式的操作按钮（录制模式的开始/停止在 RecordPanel 内，同一位置随模式切换） -->
          <RunControls
            :mode="rightMode"
            v-model:auto-device-id="autoDeviceId"
            v-model:capture-traffic="captureTraffic"
            :running="runner.running"
            :can-run="canRun"
            @run="runScript"
            @stop="runner.stopRun"
          />
        </div>

        <RecordPanel
          v-show="rightMode === 'record'"
          ref="recordPanelRef"
          :device-id="autoDeviceId"
          :disabled="runner.running && !recording"
          :has-selection="store.selectedStepIndex >= 0"
          @recording-start="onRecStart"
          @recorded="store.onRecorded"
          @recording-end="onRecEnd"
        />

        <ResultPanel
          v-show="rightMode === 'run'"
          :active="rightMode === 'run'"
          :running="runner.running"
          :run-result="runner.runResult"
          :live-steps="runner.liveSteps"
          :screenshots="runner.screenshots"
          :logs="runner.logs"
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
import { ref, computed, onMounted, watch } from 'vue'
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
  useMessage,
  useDialog,
} from 'naive-ui'
import { Download, Upload, Save } from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import RecordPanel from '@components/automation/RecordPanel.vue'
import StepListEditor from '@components/automation/StepListEditor.vue'
import ProjectTree from '@components/automation/ProjectTree.vue'
import RunControls from '@components/automation/RunControls.vue'
import ResultPanel from '@components/automation/ResultPanel.vue'
import ElementPickerModal from '@components/automation/ElementPickerModal.vue'
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
const store = useAutomationStore(() => runner.running)

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

// Run is allowed only when both a device and a script are selected.
const canRun = computed(() => !!autoDeviceId.value && !!store.selectedScriptId)

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
  if (v === 'record' && runner.running) {
    message.warning(t('automation.runStopFirst'))
    return
  }
  rightMode.value = v as 'record' | 'run'
}

/** 「添加步骤 → 录制片段…」：切到右栏录制模式采集 */
function onRecordRequest() {
  if (runner.running && !recording.value) {
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
  runner.running = true
}
function onRecEnd() {
  recording.value = false
  runner.running = false
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
  if (!store.commitEditor()) return
  const s = store.selectedScript
  if (!s || !s.steps.length) {
    message.warning(t('automation.noSteps'))
    return
  }
  try {
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

/** 元素抽屉里选中一个元素：填充正在编辑的步骤（v2 模型） */
function applyElement(el: UiNode) {
  const target = pickTarget.value
  if (!target) return
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
      timeout_ms: s.target?.timeout_ms ?? 10000,
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
</style>
