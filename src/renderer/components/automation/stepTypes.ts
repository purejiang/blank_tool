/**
 * Automation step types + per-action parameter schemas — **v2 data model**.
 *
 * Design rules:
 *  - Every step carries a stable `id` (list keys, result alignment).
 *  - One action per intent; a `mode` discriminator switches the target:
 *      * `tap`  → mode: coord (`coord:{x,y}`) | element (`target:{by,...}`)
 *      * `wait` → mode: time (`ms`)           | element (`target:{by,...}`)
 *  - The element target is a NESTED object shared by tap/wait/assert_element
 *    and by `input` (as the optional pre-typing focus tap).
 *  - Schema field keys use dotted paths (`target.by`) — StepEditForm
 *    resolves them against nested step objects.
 *  - Legacy actions (`tap_element` / `wait_element`) are GONE — storage
 *    reset to v2 (user decision: no backwards compatibility).
 *
 * Step objects are persisted verbatim into the script (app-config key
 * `automation`, `version: 2`) and forwarded to the backend plugin
 * `adb_auto`, whose step executor consumes exactly this shape.
 */

export type By = 'text' | 'resource_id' | 'content_desc' | 'class'

export type StepAction =
  | 'launch_app'
  | 'tap'
  | 'swipe'
  | 'input'
  | 'keyevent'
  | 'back'
  | 'home'
  | 'clear_app_data'
  | 'shell'
  | 'wait'
  | 'assert_element'
  | 'assert_activity'
  | 'screenshot'

/** Selector used to locate a UI element (shared by every element target). */
export interface ElementTarget {
  by: By
  value: string
  /** 0-based match index among same-selector nodes (class locators) */
  instance?: number
  timeout_ms?: number
}

export interface Step {
  id: string
  action: StepAction
  /** tap: coordinate target */
  mode?: 'coord' | 'element' | 'time'
  coord?: { x: number; y: number }
  /** swipe: stroke */
  path?: { x1: number; y1: number; x2: number; y2: number; duration_ms?: number }
  /** element target (tap/wait element mode, input focus, assert_element) */
  target?: ElementTarget
  text?: string
  key?: string
  package?: string
  command?: string
  /** wait: fixed duration */
  ms?: number
  expect?: 'exists' | 'not_exists'
  activity?: string
  name?: string
  /** device-time seconds of the touch END marker (recorded steps only) */
  ts?: number
  [key: string]: unknown
}

export interface StepFieldDef {
  /** dotted path into the step object (`target.by`, `coord.x`, …) */
  key: string
  /** i18n key under `automation.f` */
  labelKey: string
  type: 'text' | 'textarea' | 'number' | 'select'
  required?: boolean
  default?: string | number
  placeholder?: string
  options?: Array<{ value: string; label?: string; labelKey?: string }>
  /**
   * Render / validate this field ONLY when the (dotted) key `key` equals
   * one of `equals` — e.g. show `coord.x` only when `mode === 'coord'`.
   */
  visibleWhen?: { key: string; equals: Array<string | number> }
}

const BY_OPTIONS = [
  { value: 'text', label: 'text' },
  { value: 'resource_id', label: 'resource-id' },
  { value: 'content_desc', label: 'content-desc' },
  { value: 'class', label: 'class' },
]

/** Element-target fields, nested under `target.` (dotted schema paths). */
function TARGET_FIELDS(visibleWhen?: { key: string; equals: Array<string | number> }): StepFieldDef[] {
  return [
    {
      key: 'target.by', labelKey: 'by', type: 'select', required: true, default: 'text',
      options: BY_OPTIONS,
      visibleWhen,
    },
    {
      key: 'target.value', labelKey: 'value', type: 'text', required: true, default: '',
      visibleWhen,
    },
    {
      key: 'target.timeout_ms', labelKey: 'timeoutMs', type: 'number', default: 10000,
      visibleWhen,
    },
    {
      key: 'target.instance', labelKey: 'instance', type: 'number', default: 0,
      visibleWhen: { key: 'target.by', equals: ['class'] },
    },
  ]
}

export const STEP_FIELDS: Record<StepAction, StepFieldDef[]> = {
  tap: [
    {
      key: 'mode', labelKey: 'target', type: 'select', required: true, default: 'coord',
      options: [
        { value: 'coord', labelKey: 'byCoord' },
        { value: 'element', labelKey: 'byElement' },
      ],
    },
    {
      key: 'coord.x', labelKey: 'x', type: 'number', required: true, default: 540,
      visibleWhen: { key: 'mode', equals: ['coord'] },
    },
    {
      key: 'coord.y', labelKey: 'y', type: 'number', required: true, default: 960,
      visibleWhen: { key: 'mode', equals: ['coord'] },
    },
    ...TARGET_FIELDS({ key: 'mode', equals: ['element'] }),
  ],
  swipe: [
    { key: 'path.x1', labelKey: 'x1', type: 'number', required: true, default: 540 },
    { key: 'path.y1', labelKey: 'y1', type: 'number', required: true, default: 1200 },
    { key: 'path.x2', labelKey: 'x2', type: 'number', required: true, default: 540 },
    { key: 'path.y2', labelKey: 'y2', type: 'number', required: true, default: 400 },
    { key: 'path.duration_ms', labelKey: 'durationMs', type: 'number', default: 300 },
  ],
  wait: [
    {
      key: 'mode', labelKey: 'target', type: 'select', required: true, default: 'time',
      options: [
        { value: 'time', labelKey: 'byDuration' },
        { value: 'element', labelKey: 'byElement' },
      ],
    },
    {
      key: 'ms', labelKey: 'ms', type: 'number', required: true, default: 500,
      visibleWhen: { key: 'mode', equals: ['time'] },
    },
    ...TARGET_FIELDS({ key: 'mode', equals: ['element'] }),
  ],
  input: [
    { key: 'text', labelKey: 'text', type: 'textarea', required: true, default: '' },
    // Optional focus tap: `input text` only types into the focused editor,
    // so the step can tap the field first (empty target = no tap).
    { key: 'target.by', labelKey: 'focusBy', type: 'select', default: 'text', options: BY_OPTIONS },
    { key: 'target.value', labelKey: 'focusValue', type: 'text', default: '' },
    { key: 'target.timeout_ms', labelKey: 'timeoutMs', type: 'number', default: 10000 },
    {
      key: 'target.instance', labelKey: 'instance', type: 'number', default: 0,
      visibleWhen: { key: 'target.by', equals: ['class'] },
    },
  ],
  keyevent: [
    {
      key: 'key', labelKey: 'key', type: 'select', required: true, default: 'BACK',
      options: [
        { value: 'BACK', label: 'BACK' },
        { value: 'HOME', label: 'HOME' },
        { value: 'ENTER', label: 'ENTER' },
        { value: 'MENU', label: 'MENU' },
        { value: 'VOLUME_UP', label: 'VOLUME_UP' },
        { value: 'VOLUME_DOWN', label: 'VOLUME_DOWN' },
        { value: 'POWER', label: 'POWER' },
        { value: 'DEL', label: 'DEL' },
        { value: 'TAB', label: 'TAB' },
      ],
    },
  ],
  launch_app: [
    { key: 'package', labelKey: 'package', type: 'text', placeholder: 'com.example.app' },
  ],
  back: [],
  home: [],
  clear_app_data: [
    { key: 'package', labelKey: 'package', type: 'text', placeholder: 'com.example.app' },
  ],
  shell: [
    { key: 'command', labelKey: 'command', type: 'textarea', required: true, default: '' },
  ],
  assert_element: [
    ...TARGET_FIELDS(),
    {
      key: 'expect', labelKey: 'expect', type: 'select', default: 'exists',
      options: [
        { value: 'exists', label: 'exists' },
        { value: 'not_exists', label: 'not_exists' },
      ],
    },
  ],
  assert_activity: [
    { key: 'activity', labelKey: 'activity', type: 'text', required: true, default: '' },
    { key: 'timeout_ms', labelKey: 'timeoutMs', type: 'number', default: 3000 },
  ],
  screenshot: [
    { key: 'name', labelKey: 'name', type: 'text', default: '' },
  ],
}

/** Order of actions in the "add step" dropdown (most used first). */
export const ADDABLE_ACTIONS: StepAction[] = [
  'tap', 'wait', 'swipe', 'input', 'keyevent', 'back', 'home',
  'launch_app', 'screenshot', 'shell', 'clear_app_data', 'assert_activity',
]

function newId(): string {
  try {
    return (crypto as any).randomUUID()
  } catch {
    return 'step-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8)
  }
}

/** Build a fresh v2 step of the given action from the schema defaults. */
export function defaultStep(action: StepAction): Step {
  const step: any = { id: newId(), action }
  for (const f of STEP_FIELDS[action] || []) {
    if (f.default === undefined) continue
    if (f.visibleWhen && !f.visibleWhen.equals.includes(getPath(step, f.visibleWhen.key) as string | number)) {
      continue
    }
    setPath(step, f.key, f.default)
  }
  return step
}

// ---------------- dotted-path helpers (shared with StepEditForm) ----------------

export function getPath(obj: any, key: string): any {
  return key.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj)
}

export function setPath(obj: any, key: string, value: unknown): void {
  const ks = key.split('.')
  let o = obj
  for (let i = 0; i < ks.length - 1; i++) {
    if (typeof o[ks[i]] !== 'object' || o[ks[i]] === null) o[ks[i]] = {}
    o = o[ks[i]]
  }
  o[ks[ks.length - 1]] = value
}
