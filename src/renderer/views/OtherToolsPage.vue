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
                <span :title="p.name">{{ p.name }}</span>
              </div>
              <div class="row-actions">
                <n-button size="tiny" text type="primary" :disabled="running" @click.stop="renameProject(p)">
                  <template #icon><n-icon><Pencil /></n-icon></template>
                </n-button>
                <n-button size="tiny" text type="error" :disabled="running" @click.stop="deleteProject(p)">
                  <template #icon><n-icon><Trash2 /></n-icon></template>
                </n-button>
              </div>
            </div>

            <div v-if="p.id === selectedProjectId" class="scripts">
              <div
                v-for="s in p.scripts"
                :key="s.id"
                class="script-row"
                :class="{ active: s.id === selectedScriptId }"
                @click="selectScript(p.id, s.id)"
              >
                <n-icon size="13"><FileText /></n-icon>
                <span :title="s.name">{{ s.name }}</span>
                <n-button
                  size="tiny"
                  text
                  type="error"
                  class="script-del"
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
            <span>{{ t('automation.editor') }}</span>
            <n-button size="small" type="primary" :disabled="running" @click="saveScript">
              <template #icon><n-icon><Save /></n-icon></template>
              {{ t('automation.save') }}
            </n-button>
          </div>

          <div class="editor-body">
            <div class="field">
              <label>{{ t('automation.projectName') }}</label>
              <n-input v-model:value="editor.projectName" size="small" :disabled="running" />
            </div>
            <div class="field">
              <label>{{ t('automation.packageName') }}</label>
              <n-input v-model:value="editor.packageName" size="small" :disabled="running" placeholder="com.example.app" />
            </div>
            <div class="field">
              <label>{{ t('automation.scriptName') }}</label>
              <n-input v-model:value="editor.scriptName" size="small" :disabled="running" />
            </div>

            <div class="field steps-field">
              <div class="steps-head">
                <label>{{ t('automation.steps') }}</label>
                <n-space size="small">
                  <n-button size="tiny" @click="loadTemplate">{{ t('automation.loadTemplate') }}</n-button>
                  <n-button size="tiny" @click="getElements" :loading="dumping">
                    <template #icon><n-icon><MousePointerClick /></n-icon></template>
                    {{ t('automation.getElements') }}
                  </n-button>
                </n-space>
              </div>
              <n-input
                v-model:value="editor.stepsText"
                type="textarea"
                :autosize="{ minRows: 14, maxRows: 26 }"
                :disabled="running"
                class="steps-input"
                @update:value="onStepsInput"
              />
              <div class="json-status" :class="jsonError ? 'bad' : 'ok'">
                <template v-if="jsonError">{{ t('automation.validateError', { msg: jsonError }) }}</template>
                <template v-else>{{ t('automation.validateOk') }} · {{ stepCount }} steps</template>
              </div>
            </div>
          </div>
        </template>
      </section>

      <!-- ============ RIGHT: run / log / result ============ -->
      <section class="col col-right">
        <div class="col-head">
          <span>{{ t('automation.run') }}</span>
        </div>

        <div class="run-bar">
          <n-select
            :value="deviceStore.selectedDeviceId"
            :options="deviceOptions"
            size="small"
            :placeholder="t('automation.selectDevice')"
            @update:value="(v: string) => deviceStore.selectDevice(v)"
          />
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
            {{ !deviceStore.selectedDeviceId ? t('automation.noDevice') : t('automation.noScriptSelected') }}
          </n-tooltip>
          <n-button v-else type="warning" size="small" block @click="stopRun">
            <template #icon><n-icon><Square /></n-icon></template>
            {{ t('automation.stop') }}
          </n-button>
        </div>

        <div class="result-block" v-if="runResult">
          <div class="result-summary">
            <n-tag :type="runResult.cancelled ? 'warning' : (runResult.success ? 'success' : 'error')" size="small">
              {{ runResult.cancelled ? t('automation.cancelled') : (runResult.success ? t('automation.success') : t('automation.failed')) }}
            </n-tag>
            <span class="sum-item">{{ t('automation.total') }}: {{ runResult.total ?? 0 }}</span>
            <span class="sum-item ok">{{ t('automation.passed') }}: {{ runResult.passed ?? 0 }}</span>
            <span class="sum-item bad">{{ t('automation.failed') }}: {{ runResult.failed ?? 0 }}</span>
          </div>

          <div class="steps-result">
            <div v-for="st in runResult.steps || []" :key="st.index" class="step-line" :class="st.ok ? 'ok' : 'bad'">
              <span class="step-idx">#{{ st.index }}</span>
              <span class="step-act">{{ actLabel(st.action) }}</span>
              <span class="step-msg">{{ st.message || (st.ok ? 'ok' : 'fail') }}</span>
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
      </section>
    </div>

    <!-- ============ Element picker modal ============ -->
    <n-modal v-model:show="showElements" :title="t('automation.elements')" preset="card" style="width: 520px">
      <p class="muted">{{ t('automation.elementsDesc') }}</p>
      <n-empty v-if="!elements.length" :description="t('automation.noElements')" size="small" />
      <n-list v-else bordered class="elem-list">
        <n-list-item v-for="(el, i) in elements" :key="i" @click="insertElement(el)" class="elem-item">
          <div class="elem-main">
            <span class="elem-label">{{ el.label }}</span>
            <span class="elem-by">{{ el.by }} = {{ el.value }}</span>
          </div>
          <span class="elem-bounds">{{ el.bounds }}</span>
        </n-list-item>
      </n-list>
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
  MousePointerClick,
} from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { ConfigService } from '@services/ConfigService'

const { t } = useI18n()
const message = useMessage()
const dialog = useDialog()
const deviceStore = useDeviceStore()
const config = new ConfigService()

// ---------------- types ----------------
interface Step {
  action: string
  [k: string]: unknown
}
interface Script {
  id: string
  name: string
  updated_at: string
  steps: Step[]
}
interface Project {
  id: string
  name: string
  package_name?: string
  scripts: Script[]
}
interface UiNode {
  text: string
  resource_id: string
  content_desc: string
  class: string
  bounds: string
  by: string
  value: string
  label: string
}

// ---------------- state ----------------
const projects = ref<Project[]>([])
const selectedProjectId = ref('')
const selectedScriptId = ref('')
const editor = ref({
  projectName: '',
  packageName: '',
  scriptName: '',
  stepsText: '[]',
})
const jsonError = ref('')
const stepCount = ref(0)

const running = ref(false)
const taskId = ref('')
const logs = ref<string[]>([])
const runResult = ref<any>(null)
const screenshots = ref<string[]>([])

const dumping = ref(false)
const showElements = ref(false)
const elements = ref<UiNode[]>([])
const logScroll = ref<any>(null)

// ---------------- helpers ----------------
function genId(): string {
  try {
    return (crypto as any).randomUUID()
  } catch {
    return 'id-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8)
  }
}

function findProject(id: string): Project | undefined {
  return projects.value.find((p) => p.id === id)
}
function findScript(pid: string, sid: string): Script | undefined {
  return findProject(pid)?.scripts.find((s) => s.id === sid)
}

function actLabel(action: string): string {
  const key = 'automation.act.' + action
  const v = t(key)
  return v === key ? action : (v as string)
}

function fileUrl(p: string): string {
  if (!p) return ''
  if (p.startsWith('file://')) return p
  return 'file:///' + p.replace(/\\/g, '/')
}

function parseSteps(text: string): { ok: boolean; data: Step[]; error: string } {
  if (!text || !text.trim()) return { ok: true, data: [], error: '' }
  try {
    const data = JSON.parse(text)
    if (!Array.isArray(data)) return { ok: false, data: [], error: 'not an array' }
    for (const s of data) {
      if (typeof s !== 'object' || s === null || typeof s.action !== 'string') {
        return { ok: false, data: [], error: 'step missing "action"' }
      }
    }
    return { ok: true, data, error: '' }
  } catch (e: any) {
    return { ok: false, data: [], error: e?.message || String(e) }
  }
}

function refreshJsonStatus() {
  const r = parseSteps(editor.value.stepsText)
  jsonError.value = r.ok ? '' : r.error
  stepCount.value = r.ok ? r.data.length : 0
}

const logsText = computed(() => logs.value.join('\n'))

const deviceOptions = computed(() =>
  deviceStore.devices.map((d: any) => ({
    label: `${d.name || d.id}${d.status ? ' (' + d.status + ')' : ''}`,
    value: d.id,
  })),
)

// Run is allowed only when both a device and a script are selected.
const canRun = computed(() => !!deviceStore.selectedDeviceId && !!selectedScriptId.value)

const selectedProject = computed(() => findProject(selectedProjectId.value))
const selectedScript = computed(() => {
  if (!selectedProjectId.value || !selectedScriptId.value) return undefined
  return findScript(selectedProjectId.value, selectedScriptId.value)
})

// ---------------- persistence ----------------
async function persist() {
  try {
    await config.setAppConfig('automation', { projects: projects.value })
  } catch (e) {
    message.error(String((e as any)?.message || e))
  }
}

async function loadConfig() {
  try {
    const raw = (await config.getAppConfig('automation')) as any
    const list = raw?.projects
    if (Array.isArray(list)) {
      projects.value = list as Project[]
    }
  } catch {
    projects.value = []
  }
}

// ---------------- selection / editing ----------------
function loadEditorFromSelection() {
  const p = selectedProject.value
  const s = selectedScript.value
  if (!p || !s) {
    editor.value = { projectName: '', packageName: '', scriptName: '', stepsText: '[]' }
    return
  }
  editor.value.projectName = p.name
  editor.value.packageName = p.package_name || ''
  editor.value.scriptName = s.name
  editor.value.stepsText = JSON.stringify(s.steps || [], null, 2)
  refreshJsonStatus()
}

/** Commit editor back into projects[]. Returns false if JSON invalid (abort switch). */
function commitEditor(): boolean {
  const p = selectedProject.value
  const s = selectedScript.value
  if (!p || !s) return true
  const r = parseSteps(editor.value.stepsText)
  if (!r.ok) {
    message.error(t('automation.validateError', { msg: r.error }))
    return false
  }
  p.name = editor.value.projectName.trim() || p.name
  p.package_name = editor.value.packageName.trim() || undefined
  s.name = editor.value.scriptName.trim() || s.name
  s.steps = r.data
  s.updated_at = new Date().toISOString()
  return true
}

function onStepsInput() {
  refreshJsonStatus()
}

function selectProject(id: string) {
  if (running.value) return
  if (selectedProjectId.value && selectedProjectId.value !== id) {
    if (!commitEditor()) return
    persist()
  }
  selectedProjectId.value = id
  // keep current script only if it belongs to this project
  if (selectedScriptId.value && !findScript(id, selectedScriptId.value)) {
    selectedScriptId.value = ''
  }
  loadEditorFromSelection()
}

function selectScript(pid: string, sid: string) {
  if (running.value) return
  if (selectedScriptId.value && (selectedProjectId.value !== pid || selectedScriptId.value !== sid)) {
    if (!commitEditor()) return
    persist()
  }
  selectedProjectId.value = pid
  selectedScriptId.value = sid
  loadEditorFromSelection()
}

function newProject() {
  if (running.value) return
  if (selectedProjectId.value && !commitEditor()) return
  const proj: Project = { id: genId(), name: t('automation.newProject'), package_name: '', scripts: [] }
  projects.value.push(proj)
  selectedProjectId.value = proj.id
  selectedScriptId.value = ''
  editor.value = { projectName: proj.name, packageName: '', scriptName: '', stepsText: '[]' }
  persist()
}

function newScript(pid: string) {
  if (running.value) return
  const p = findProject(pid)
  if (!p) return
  if (selectedScriptId.value && !commitEditor()) return
  const scr: Script = {
    id: genId(),
    name: t('automation.newScript'),
    updated_at: new Date().toISOString(),
    steps: [],
  }
  p.scripts.push(scr)
  selectedProjectId.value = pid
  selectedScriptId.value = scr.id
  editor.value = { projectName: p.name, packageName: p.package_name || '', scriptName: scr.name, stepsText: '[]' }
  persist()
}

function deleteProject(p: Project) {
  if (running.value) return
  dialog.warning({
    title: t('automation.delete'),
    content: t('automation.deleteProjectConfirm', { name: p.name }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => {
      projects.value = projects.value.filter((x) => x.id !== p.id)
      if (selectedProjectId.value === p.id) {
        selectedProjectId.value = ''
        selectedScriptId.value = ''
        loadEditorFromSelection()
      }
      persist()
    },
  })
}

function deleteScript(pid: string, sid: string) {
  if (running.value) return
  const p = findProject(pid)
  if (!p) return
  const s = findScript(pid, sid)
  dialog.warning({
    title: t('automation.delete'),
    content: t('automation.deleteScriptConfirm', { name: s?.name || '' }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => {
      p.scripts = p.scripts.filter((x) => x.id !== sid)
      if (selectedScriptId.value === sid) {
        selectedScriptId.value = ''
        loadEditorFromSelection()
      }
      persist()
    },
  })
}

function renameProject(p: Project) {
  if (running.value) return
  const value = window.prompt(t('automation.rename'), p.name)
  if (value && value.trim()) {
    p.name = value.trim()
    if (selectedProjectId.value === p.id) editor.value.projectName = p.name
    persist()
  }
}

function saveScript() {
  if (running.value) return
  if (!commitEditor()) return
  persist()
  message.success(t('automation.saved'))
}

function loadTemplate() {
  const pkg = editor.value.packageName.trim() || 'com.example.app'
  const tpl: Step[] = [
    { action: 'launch_app', package: pkg },
    { action: 'wait', ms: 2000 },
    { action: 'tap_element', by: 'text', value: '登录', timeout_ms: 10000 },
    { action: 'wait_element', by: 'resource_id', value: 'com.example.app:id/et_account', timeout_ms: 8000 },
    { action: 'input', text: 'user@example.com' },
    { action: 'keyevent', key: 'KEYCODE_TAB' },
    { action: 'screenshot', name: 'login-form' },
    { action: 'assert_activity', activity: '.LoginActivity' },
    { action: 'back' },
  ]
  editor.value.stepsText = JSON.stringify(tpl, null, 2)
  refreshJsonStatus()
}

// ---------------- element picker ----------------
function attr(tag: string, name: string): string {
  const m = tag.match(new RegExp(`${name}="([^"]*)"`))
  return m ? m[1] : ''
}

function parseUiDump(xml: string): UiNode[] {
  if (!xml) return []
  const openTags = xml.match(/<node[^>]*>/g) || []
  const nodes: UiNode[] = []
  for (const tag of openTags) {
    const text = attr(tag, 'text')
    const rid = attr(tag, 'resource-id')
    const desc = attr(tag, 'content-desc')
    const cls = attr(tag, 'class')
    const bounds = attr(tag, 'bounds')
    if (!text && !rid && !desc) continue
    let by = ''
    let value = ''
    if (text) {
      by = 'text'
      value = text
    } else if (rid) {
      by = 'resource_id'
      value = rid
    } else if (desc) {
      by = 'content_desc'
      value = desc
    }
    nodes.push({ text, resource_id: rid, content_desc: desc, class: cls, bounds, by, value, label: text || rid || desc })
  }
  return nodes
}

async function getElements() {
  if (running.value) return
  if (!deviceStore.selectedDeviceId) {
    message.error(t('automation.noDevice'))
    return
  }
  dumping.value = true
  try {
    const api = window.electronAPI as any
    const res = await api.callBackendAPI('device.ui_dump', {
      device_id: deviceStore.selectedDeviceId,
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

function insertElement(el: UiNode) {
  const step: Step = { action: 'tap_element', by: el.by, value: el.value, timeout_ms: 10000 }
  const r = parseSteps(editor.value.stepsText)
  const arr = r.ok ? r.data : []
  arr.push(step)
  editor.value.stepsText = JSON.stringify(arr, null, 2)
  refreshJsonStatus()
  showElements.value = false
  message.success(el.label)
}

// ---------------- run / stop ----------------
async function runScript() {
  if (running.value) return
  if (!deviceStore.selectedDeviceId) {
    message.error(t('automation.noDeviceSelectedRun'))
    return
  }
  if (!selectedScriptId.value) {
    message.warning(t('automation.noScriptSelected'))
    return
  }
  if (!commitEditor()) return
  const s = selectedScript.value
  if (!s || !s.steps.length) {
    message.warning(t('automation.noSteps'))
    return
  }

  running.value = true
  logs.value = []
  runResult.value = null
  screenshots.value = []

  const id = genId()
  taskId.value = id

  const taskStream = (await serviceManager.getService('taskStream')) as any
  taskStream.bindTask(id)
  taskStream.setCallbacks(id, {
    onLog: (line: string) => {
      logs.value.push(String(line))
    },
    onError: (msg: string) => {
      logs.value.push('[ERROR] ' + msg)
      running.value = false
    },
    onCancelled: () => {
      logs.value.push('[CANCELLED]')
      running.value = false
    },
    onComplete: (payload: any) => {
      runResult.value = payload || {}
      screenshots.value = (payload?.screenshots || []).slice()
      running.value = false
    },
  })
  taskStream.setPhase(id, 'operation')

  const api = window.electronAPI as any
  try {
    const init = await api.callBackendAPI('plugin.run', {
      name: 'adb_auto',
      params: {
        device_id: deviceStore.selectedDeviceId,
        package_name: selectedProject.value?.package_name || '',
        steps: s.steps,
        continue_on_error: false,
      },
      task_id: id,
    })
    if (!init || !init.stream_id) throw new Error('no stream_id')
    await taskStream.waitForPhase(id, 'operation')
  } catch (e: any) {
    const m = e?.message
    if (m !== 'cancelled' && m !== 'unbound') {
      logs.value.push('[ERROR] ' + (m || String(e)))
      message.error(m || String(e))
    }
    running.value = false
  }
}

async function stopRun() {
  if (!taskId.value) return
  const api = window.electronAPI as any
  if (api && typeof api.cancelApkTask === 'function') {
    try {
      await api.cancelApkTask(taskId.value)
    } catch {
      /* ignore */
    }
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
      projects.value = parsed.projects as Project[]
      selectedProjectId.value = ''
      selectedScriptId.value = ''
      loadEditorFromSelection()
      persist()
      message.success(t('automation.importSuccess'))
    },
  })
}

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
  flex: 1; display: grid; grid-template-columns: 280px 1fr 360px;
  gap: 14px; min-height: 0;
}
/* Responsive fallback: shrink side columns on narrower viewports so the
   editor column keeps usable width instead of being crushed. */
@media (max-width: 1180px) {
  .three-cols { grid-template-columns: 230px 1fr 300px; }
}
@media (max-width: 920px) {
  .three-cols { grid-template-columns: 200px 1fr 260px; gap: 10px; }
}
.col {
  background: var(--app-card-bg); border: 1px solid var(--app-card-border);
  border-radius: 10px; padding: 12px; display: flex; flex-direction: column; min-height: 0;
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
.script-row span { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.script-row.active { background: var(--app-blue-bg); color: var(--app-text-primary); }
.script-del { opacity: 0; }
.script-row:hover .script-del { opacity: 1; }

/* center editor */
.editor-body { overflow: auto; flex: 1; display: flex; flex-direction: column; gap: 10px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 12px; color: var(--app-text-muted); }
.steps-field { flex: 1; min-height: 0; }
.steps-head { display: flex; justify-content: space-between; align-items: center; }
.steps-input { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 12px; }
.json-status { font-size: 11.5px; margin-top: 4px; }
.json-status.ok { color: #18a058; }
.json-status.bad { color: #d03050; }

/* right run */
.run-bar { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.result-block { flex: 0 0 auto; }
.result-summary { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 8px; }
.sum-item { font-size: 12px; color: var(--app-text-secondary); }
.sum-item.ok { color: #18a058; }
.sum-item.bad { color: #d03050; }
.steps-result { max-height: 200px; overflow: auto; border: 1px solid var(--app-card-border); border-radius: 8px; padding: 6px; }
.step-line { display: flex; gap: 8px; align-items: baseline; font-size: 12px; padding: 2px 0; border-bottom: 1px dashed var(--app-card-border); }
.step-line.ok .step-idx { color: #18a058; }
.step-line.bad .step-idx { color: #d03050; }
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
.elem-label { font-size: 13px; color: var(--app-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.elem-by { font-size: 11px; color: var(--app-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.elem-bounds { font-size: 10.5px; color: var(--app-text-muted); flex: 0 0 auto; }
</style>
