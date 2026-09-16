/**
 * Projects / scripts state for the automation page: persistence
 * (app-config key `automation`), selection, step editor model (UI list +
 * raw-JSON view), CRUD and the meta dialog.
 *
 * UI feedback uses Naive UI's useMessage/useDialog internally — this
 * composable must be created inside a component setup context.
 * Mutating actions bail out while `isBusy()` returns true (a run is in
 * flight or recording).
 */
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, useDialog } from 'naive-ui'
import { ConfigService } from '@services/ConfigService'
import type { Step } from '@components/automation/stepTypes'
import { genId } from '@utils/id'

export interface Script {
  id: string
  name: string
  description?: string
  updated_at: string
  steps: Step[]
}
export interface Project {
  id: string
  name: string
  description?: string
  package_name?: string
  scripts: Script[]
}

/**
 * Page preferences that used to be six ad-hoc `localStorage` keys
 * (`bt:automationDeviceId`, `bt:autoCaptureTraffic`, …). They live in the
 * `automation` app-config document as of storage v3 so that ONE schema owns
 * the whole feature and export/backup of the config carries them too.
 */
export interface AutomationUiState {
  /** last device used on the automation page (decoupled from the device page) */
  deviceId: string
  captureTraffic: boolean
  trafficHostFilter: string
  /** default element-poll timeout applied to new element steps */
  elementTimeoutMs: number
  /** 三列布局宽度（px） */
  colLeft: number
  colRight: number
  /** 步骤失败后继续（默认 false：首个失败即中止） */
  continueOnError: boolean
  /** 目标进程消失/重启即中止（默认 true） */
  abortOnCrash: boolean
  /** 允许运行时切换输入法以输入中文（默认 true；关闭后含非 ASCII 的输入步骤失败） */
  enableChineseInput: boolean
  /**
   * 步骤之间的默认等待（ms）。**0 = 不等待**，所以它是唯一允许为 0 的数值项
   * （sanitize 里单独处理）。单个步骤可以用自己的 `delay_ms` 覆盖它。
   */
  stepIntervalMs: number
}

export const AUTOMATION_UI_DEFAULTS: AutomationUiState = {
  deviceId: '',
  captureTraffic: false,
  trafficHostFilter: '',
  elementTimeoutMs: 10000,
  colLeft: 240,
  colRight: 320,
  continueOnError: false,
  abortOnCrash: true,
  enableChineseInput: true,
  stepIntervalMs: 300,
}

/** `bt:*` keys the v2 build wrote; adopted once, then removed. */
export const LEGACY_UI_KEYS: Record<string, keyof AutomationUiState> = {
  'bt:automationDeviceId': 'deviceId',
  'bt:autoCaptureTraffic': 'captureTraffic',
  'bt:autoTrafficHostFilter': 'trafficHostFilter',
  'bt:autoElementTimeoutMs': 'elementTimeoutMs',
  'bt:autoColLeft': 'colLeft',
  'bt:autoColRight': 'colRight',
}

/** Coerce whatever is on disk into a usable UI bag (never throws). */
export function sanitizeUi(raw: any): AutomationUiState {
  const out: AutomationUiState = { ...AUTOMATION_UI_DEFAULTS }
  if (!raw || typeof raw !== 'object') return out
  if (typeof raw.deviceId === 'string') out.deviceId = raw.deviceId
  if (typeof raw.captureTraffic === 'boolean') out.captureTraffic = raw.captureTraffic
  if (typeof raw.trafficHostFilter === 'string') out.trafficHostFilter = raw.trafficHostFilter
  for (const key of ['elementTimeoutMs', 'colLeft', 'colRight'] as const) {
    const n = Number(raw[key])
    if (Number.isFinite(n) && n > 0) out[key] = Math.round(n)
  }
  // 0 是合法值（= 不插入间隔），所以这条不能并进上面的 `n > 0` 循环；
  // `null`/缺失都退回默认（Number(null) === 0 会把缺失当成「明确关闭」）
  {
    const n = Number(raw.stepIntervalMs ?? NaN)
    if (Number.isFinite(n) && n >= 0) out.stepIntervalMs = Math.round(n)
  }
  if (typeof raw.continueOnError === 'boolean') out.continueOnError = raw.continueOnError
  if (typeof raw.abortOnCrash === 'boolean') out.abortOnCrash = raw.abortOnCrash
  if (typeof raw.enableChineseInput === 'boolean') out.enableChineseInput = raw.enableChineseInput
  return out
}

export function useAutomationStore(isBusy?: () => boolean) {
  const { t } = useI18n()
  const message = useMessage()
  const dialog = useDialog()
  const config = new ConfigService()

  const busy = () => !!isBusy?.()

  // ---------------- state ----------------
  const projects = ref<Project[]>([])
  const selectedProjectId = ref('')
  const selectedScriptId = ref('')
  /** step editing model — the single source the UI list binds to */
  const editor = ref({
    steps: [] as Step[],
  })

  /** center column view: visual list vs raw JSON */
  const stepsView = ref<'ui' | 'json'>('ui')
  const stepsText = ref('[]')
  const jsonError = ref('')
  const stepCount = ref(0)

  /** 录制片段可插入到当前选中步骤之后（-1 无） */
  const selectedStepIndex = ref(-1)

  // ---------------- meta dialog ----------------
  const showMeta = ref(false)
  const metaForm = reactive({
    kind: 'project' as 'project' | 'script',
    targetId: '',
    name: '',
    packageName: '',
    description: '',
  })

  function openProjectMeta(p: Project) {
    if (busy()) return
    metaForm.kind = 'project'
    metaForm.targetId = p.id
    metaForm.name = p.name
    metaForm.packageName = p.package_name || ''
    metaForm.description = p.description || ''
    showMeta.value = true
  }

  function openScriptMeta(pid: string, s: Script) {
    if (busy()) return
    metaForm.kind = 'script'
    metaForm.targetId = `${pid}::${s.id}`
    metaForm.name = s.name
    metaForm.packageName = ''
    metaForm.description = s.description || ''
    showMeta.value = true
  }

  function saveMeta() {
    const name = metaForm.name.trim()
    if (!name) return
    if (metaForm.kind === 'project') {
      const p = findProject(metaForm.targetId)
      if (!p) return
      p.name = name
      p.package_name = metaForm.packageName.trim() || undefined
      p.description = metaForm.description.trim() || undefined
    } else {
      const [pid, sid] = metaForm.targetId.split('::')
      const s = findScript(pid, sid)
      if (!s) return
      s.name = name
      s.description = metaForm.description.trim() || undefined
      s.updated_at = new Date().toISOString()
    }
    persist()
    showMeta.value = false
  }

  // ---------------- persistence ----------------
  // v3 = v2 + the `ui` bag (page preferences moved out of localStorage).
  // v1 and anything unversioned stay DROPPED: the v2 step model is not
  // backwards compatible by design, and adopting a legacy project list would
  // produce steps the backend cannot execute.
  const STORAGE_VERSION = 3

  const ui = reactive<AutomationUiState>({ ...AUTOMATION_UI_DEFAULTS })
  let uiDirty = false
  let uiTimer: ReturnType<typeof setTimeout> | null = null

  /**
   * One-shot adoption of the six `bt:*` keys the v2 build wrote.
   *
   * Runs only when the stored document has no `ui` bag yet — i.e. exactly on
   * the first load after the upgrade — so a later deliberately-reset value
   * can never be overwritten by a stale key. The keys are removed afterwards.
   */
  function adoptLegacyUi() {
    let adopted = 0
    for (const [key, field] of Object.entries(LEGACY_UI_KEYS)) {
      let stored: string | null = null
      try { stored = localStorage.getItem(key) } catch { stored = null }
      if (stored === null) continue
      const fallback = (AUTOMATION_UI_DEFAULTS as any)[field]
      if (typeof fallback === 'boolean') (ui as any)[field] = stored === '1'
      else if (typeof fallback === 'number') {
        const n = Number(stored)
        if (Number.isFinite(n) && n > 0) (ui as any)[field] = Math.round(n)
      } else (ui as any)[field] = stored
      adopted++
      try { localStorage.removeItem(key) } catch { /* private mode */ }
    }
    if (adopted) uiDirty = true
  }

  /** serialize the whole document — `ui` included, or a project save would
   *  wipe the preferences (app-config `set` replaces the value). */
  async function persist() {
    try {
      await config.setAppConfig('automation', {
        version: STORAGE_VERSION,
        projects: projects.value,
        ui: { ...ui },
      })
      uiDirty = false
    } catch (e) {
      message.error(String((e as any)?.message || e))
    }
  }

  async function loadConfig() {
    try {
      const raw = (await config.getAppConfig('automation')) as any
      if (raw?.version === STORAGE_VERSION && Array.isArray(raw.projects)) {
        projects.value = raw.projects as Project[]
        Object.assign(ui, sanitizeUi(raw.ui))
      } else if (raw?.version === 2 && Array.isArray(raw.projects)) {
        // v2 → v3 upgrade: projects survive untouched, the preferences come
        // from the legacy localStorage keys.
        //
        // Deliberately NOT keyed on `raw.ui`: the main process' appStore runs
        // `syncStoreDefaults()` at startup and MERGES the schema defaults into
        // this document, so a stored v2 document already carries a `ui` bag
        // full of DEFAULTS while `version` is still 2 (numbers are never
        // overwritten by the merge). Trusting that bag would silently reset
        // the user's device / capture / timeout settings to defaults. The
        // version field is the only trustworthy discriminator.
        projects.value = raw.projects as Project[]
        adoptLegacyUi()
      } else {
        projects.value = []
        adoptLegacyUi()
      }
      if (uiDirty) void persist()
    } catch {
      projects.value = []
    }
  }

  /**
   * Persist UI changes on a short debounce: the column widths update on every
   * pointer move during a drag, which must not become one config write per
   * pixel. Any project save flushes the pending value too (`persist()`).
   */
  function persistUiSoon(delay = 500) {
    uiDirty = true
    if (uiTimer) clearTimeout(uiTimer)
    uiTimer = setTimeout(() => {
      uiTimer = null
      if (uiDirty) void persist()
    }, delay)
  }

  // ---------------- helpers ----------------
  function findProject(id: string): Project | undefined {
    return projects.value.find((p) => p.id === id)
  }
  function findScript(pid: string, sid: string): Script | undefined {
    return findProject(pid)?.scripts.find((s) => s.id === sid)
  }

  const selectedProject = computed(() => findProject(selectedProjectId.value))
  const selectedScript = computed(() => {
    const pid = selectedProjectId.value
    if (!pid) return undefined
    return findScript(pid, selectedScriptId.value)
  })

  // ---------------- selection / editing ----------------
  function loadEditorFromSelection() {
    const p = selectedProject.value
    const s = selectedScript.value
    if (!p || !s) {
      editor.value = { steps: [] }
      syncJsonText()
      return
    }
    // legacy guard: very old builds may have stored steps as a JSON string
    const raw = s.steps as unknown
    if (typeof raw === 'string') {
      try {
        s.steps = JSON.parse(raw)
      } catch {
        s.steps = []
      }
    }
    editor.value.steps = JSON.parse(JSON.stringify(s.steps || []))
    selectedStepIndex.value = -1
    syncJsonText()
  }

  /** re-serialize editor.steps into the JSON view buffer */
  function syncJsonText() {
    stepsText.value = JSON.stringify(editor.value.steps || [], null, 2)
    refreshJsonStatus()
  }

  function refreshJsonStatus() {
    const r = _parseStepsText(stepsText.value)
    jsonError.value = r.ok ? '' : r.error
    stepCount.value = r.ok ? r.data.length : 0
  }

  function _parseStepsText(text: string): { ok: boolean; data: Step[]; error: string } {
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

  /** view switch: UI -> JSON serializes; JSON -> UI validates (stay on error) */
  function onSwitchView(v: string) {
    if (v === stepsView.value) return
    if (v === 'json') {
      syncJsonText()
      stepsView.value = 'json'
      return
    }
    const r = _parseStepsText(stepsText.value)
    if (!r.ok) {
      jsonError.value = r.error
      message.error(t('automation.jsonInvalid', { msg: r.error }))
      return // stay in JSON view until fixed
    }
    editor.value.steps = r.data
    stepsView.value = 'ui'
  }

  /** Commit editor steps into projects[]. Returns false when JSON invalid. */
  function commitEditor(): boolean {
    const p = selectedProject.value
    const s = selectedScript.value
    if (!p || !s) return true
    if (stepsView.value === 'json') {
      const r = _parseStepsText(stepsText.value)
      if (!r.ok) {
        message.error(t('automation.jsonInvalid', { msg: r.error }))
        return false
      }
      s.steps = r.data
    } else {
      s.steps = JSON.parse(JSON.stringify(editor.value.steps))
    }
    s.updated_at = new Date().toISOString()
    return true
  }

  function selectProject(id: string) {
    if (busy()) return
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
    if (busy()) return
    if (selectedScriptId.value && (selectedProjectId.value !== pid || selectedScriptId.value !== sid)) {
      if (!commitEditor()) return
      persist()
    }
    selectedProjectId.value = pid
    selectedScriptId.value = sid
    loadEditorFromSelection()
  }

  function newProject() {
    if (busy()) return
    if (selectedProjectId.value && !commitEditor()) return
    const proj: Project = { id: genId(), name: t('automation.newProject'), scripts: [] }
    projects.value.push(proj)
    selectedProjectId.value = proj.id
    selectedScriptId.value = ''
    editor.value = { steps: [] }
    syncJsonText()
    persist()
  }

  function newScript(pid: string) {
    if (busy()) return
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
    editor.value = { steps: [] }
    syncJsonText()
    persist()
  }

  function deleteProject(p: Project) {
    if (busy()) return
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
    if (busy()) return
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

  // ---------------- auto-save ----------------
  /**
   * Auto-save: any editor change (UI list or JSON typing) commits to the
   * selected script and persists after a short debounce. The save button
   * was removed — this is the only persistence path besides the
   * commit-on-selection-switch in selectProject/selectScript.
   *
   * JSON view: invalid JSON is skipped SILENTLY (no toast per keystroke)
   * and resumes saving once it parses again.
   */
  let autoSaveTimer: ReturnType<typeof setTimeout> | null = null

  function flushAutoSave() {
    autoSaveTimer = null
    const s = selectedScript.value
    if (!s) return
    let next: Step[]
    if (stepsView.value === 'json') {
      const r = _parseStepsText(stepsText.value)
      if (!r.ok) return // wait until the JSON is valid again
      next = r.data
    } else {
      next = JSON.parse(JSON.stringify(editor.value.steps))
    }
    // skip the write when nothing actually changed (e.g. editor reload
    // after switching scripts would otherwise bump updated_at forever)
    if (JSON.stringify(s.steps) === JSON.stringify(next)) return
    s.steps = next
    s.updated_at = new Date().toISOString()
    persist()
    flashSaved()
  }

  /** transient "saved" indicator — the header shows it for ~2s per save */
  const savedFlash = ref(false)
  let savedFlashTimer: ReturnType<typeof setTimeout> | null = null
  function flashSaved() {
    savedFlash.value = true
    if (savedFlashTimer) clearTimeout(savedFlashTimer)
    savedFlashTimer = setTimeout(() => {
      savedFlash.value = false
      savedFlashTimer = null
    }, 2000)
  }

  watch(
    () => [editor.value.steps, stepsText.value] as const,
    () => {
      if (autoSaveTimer) clearTimeout(autoSaveTimer)
      autoSaveTimer = setTimeout(flushAutoSave, 600)
    },
    { deep: true },
  )

  /** Flush immediately (used when leaving the page / before a run). */
  function flushAutoSaveNow() {
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer)
      flushAutoSave()
    }
  }

  // ---------------- recording ----------------
  /**
   * Recorder steps arrive in the parser's flat shape
   * ({action:'tap', x, y, ts} / {action:'swipe', x1..y2, duration_ms, ts});
   * convert them into the v2 nested model here, at the boundary.
   *
   * `ts` (device time) is deliberately DROPPED: 录制只记录操作本身，步骤之间的
   * 节奏由运行配置里的默认步骤间隔（ui.stepIntervalMs）+ 单步 `delay_ms` 控制，
   * 所以脚本里不需要（也不再使用）录制时间线。
   */
  function toV2Step(raw: any): Step {
    const base: any = { id: genId(), action: raw?.action }
    if (raw?.action === 'tap') {
      base.mode = 'coord'
      base.coord = { x: Number(raw.x) || 0, y: Number(raw.y) || 0 }
    } else if (raw?.action === 'swipe') {
      base.path = {
        x1: Number(raw.x1) || 0, y1: Number(raw.y1) || 0,
        x2: Number(raw.x2) || 0, y2: Number(raw.y2) || 0,
        duration_ms: Number(raw.duration_ms) || 300,
      }
    }
    return base
  }

  function onRecorded(payload: {
    steps: any[]
    insertAt: 'end' | 'start' | 'after'
  }) {
    // 无脚本选中时拒绝写入（片段仍暂存在录制面板，可先建脚本再应用）
    if (!selectedScript.value) {
      message.warning(t('automation.noScriptSelected'))
      return
    }
    // JSON 视图下的缓冲先校验落库，避免用旧数组插入
    if (stepsView.value === 'json') {
      const r = _parseStepsText(stepsText.value)
      if (!r.ok) {
        message.error(t('automation.jsonInvalid', { msg: r.error }))
        return
      }
      editor.value.steps = r.data
    }

    const raw = Array.isArray(payload?.steps) ? payload.steps : []
    // 直接插入录到的操作：等待不再合成步骤（见 toV2Step 的注释）
    const add = raw.map(toV2Step)

    const old = editor.value.steps
    const at = payload?.insertAt || 'end'
    if (at === 'start') {
      editor.value.steps = [...add, ...old]
    } else if (at === 'after' && selectedStepIndex.value >= 0 && selectedStepIndex.value < old.length) {
      const next = [...old]
      next.splice(selectedStepIndex.value + 1, 0, ...add)
      editor.value.steps = next
      selectedStepIndex.value = selectedStepIndex.value + add.length
    } else {
      editor.value.steps = [...old, ...add]
    }
    if (stepsView.value === 'json') syncJsonText()
    message.success(t('automation.recordApplied'))
  }

  return reactive({
    // state
    projects,
    selectedProjectId,
    selectedScriptId,
    editor,
    stepsView,
    stepsText,
    jsonError,
    stepCount,
    savedFlash,
    selectedStepIndex,
    showMeta,
    // page preferences (storage v3); mutate + call persistUiSoon()
    ui,
    persistUiSoon,
    metaForm,
    // computed / finders
    selectedProject,
    selectedScript,
    findProject,
    findScript,
    // persistence
    persist,
    loadConfig,
    // editing / selection
    loadEditorFromSelection,
    syncJsonText,
    refreshJsonStatus,
    onSwitchView,
    commitEditor,
    selectProject,
    selectScript,
    newProject,
    newScript,
    deleteProject,
    deleteScript,
    flushAutoSaveNow,
    saveMeta,
    openProjectMeta,
    openScriptMeta,
    // recording
    onRecorded,
  })
}

export type AutomationStore = ReturnType<typeof useAutomationStore>
