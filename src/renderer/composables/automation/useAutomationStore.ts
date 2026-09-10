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
  const STORAGE_VERSION = 2

  async function persist() {
    try {
      await config.setAppConfig('automation', { version: STORAGE_VERSION, projects: projects.value })
    } catch (e) {
      message.error(String((e as any)?.message || e))
    }
  }

  async function loadConfig() {
    try {
      const raw = (await config.getAppConfig('automation')) as any
      // v2-only: anything else (missing version / legacy format) is dropped —
      // the v2 data model is not backwards compatible by design.
      if (raw?.version === STORAGE_VERSION && Array.isArray(raw.projects)) {
        projects.value = raw.projects as Project[]
      } else {
        projects.value = []
      }
    } catch {
      projects.value = []
    }
  }

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
   */
  function toV2Step(raw: any): Step {
    const base: any = { id: genId(), action: raw?.action }
    if (typeof raw?.ts === 'number') base.ts = raw.ts
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

  /**
   * Insert fixed-wait steps between recorded steps whose gap exceeds the
   * configured threshold. Uses each step's `ts` (device-time seconds of the
   * touch END marker); a swipe's own duration is subtracted so the wait
   * measures true idle time. Gap is capped at maxMs.
   */
  function withWaits(
    steps: Step[],
    gap: { enabled: boolean; thresholdMs: number; maxMs: number },
  ): Step[] {
    if (!gap?.enabled || steps.length < 2) return steps
    const out: Step[] = []
    for (let i = 0; i < steps.length; i++) {
      const cur = steps[i]
      if (i > 0) {
        const prev = steps[i - 1]
        if (typeof prev?.ts === 'number' && typeof cur?.ts === 'number') {
          const dur = (cur as any).path?.duration_ms ?? (cur as any).duration_ms ?? 0
          const startOfCur = cur.ts - (Number(dur) || 0) / 1000
          const gapMs = Math.max(0, Math.round((startOfCur - prev.ts) * 1000))
          if (gapMs > gap.thresholdMs) {
            out.push({
              id: genId(), action: 'wait', mode: 'time',
              ms: Math.min(gapMs, gap.maxMs),
            })
          }
        }
      }
      out.push(cur)
    }
    return out
  }

  function onRecorded(payload: {
    steps: any[]
    gap: { enabled: boolean; thresholdMs: number; maxMs: number }
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
    const gap = payload?.gap || { enabled: true, thresholdMs: 500, maxMs: 5000 }
    const add = withWaits(raw.map(toV2Step), gap)

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
    message.success(
      gap.enabled ? t('automation.autoWaitInserted') : t('automation.recordApplied'),
    )
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
    selectedStepIndex,
    showMeta,
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
