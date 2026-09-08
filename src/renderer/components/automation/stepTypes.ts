/**
 * Automation step types + per-action parameter schemas.
 *
 * The step objects are persisted verbatim into the script (`appConfig` key
 * `automation`) and forwarded to the backend plugin `adb_auto` — the field
 * names below MUST match `backend/app/plugins/adb_auto.py::_exec_step`.
 * The extra `ts` field (recorded device-time seconds, added by
 * `getevent_parser`) is ignored by the executor; it is kept on recorded
 * steps so gaps can be recomputed, but hand-built steps never need it.
 */

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
  | 'tap_element'
  | 'wait_element'
  | 'assert_element'
  | 'assert_activity'
  | 'screenshot'

export interface Step {
  action: StepAction
  /** device-time seconds of the touch END marker (recorded steps only) */
  ts?: number
  [key: string]: unknown
}

export interface StepFieldDef {
  key: string
  /** i18n key under `automation.f` */
  labelKey: string
  type: 'text' | 'textarea' | 'number' | 'select'
  required?: boolean
  default?: string | number
  placeholder?: string
  options?: Array<{ value: string; label?: string; labelKey?: string }>
  /**
   * Render / validate this field ONLY when `<key>` equals one of `equals`.
   * Enables one action (e.g. `tap`) to switch between coordinate and
   * element targets via its `mode` field.
   */
  visibleWhen?: { key: string; equals: Array<string | number> }
}

/**
 * Per-action parameter schema. Order defines form rendering order.
 *
 * Design rule — **one action per intent, `mode` selects the target**:
 *   * `tap`  → mode: coord (x/y) | element (by/value)
 *   * `wait` → mode: time (ms)   | element (by/value)
 * Legacy names (`tap_element`, `wait_element`, `assert_element`) stay
 * readable/editable so existing scripts keep working, but they are no
 * longer offered when adding a step.
 */
/** Selector used to locate a UI element (shared by every "element" target). */
const BY_OPTIONS = [
  { value: 'text', label: 'text' },
  { value: 'resource_id', label: 'resource-id' },
  { value: 'content_desc', label: 'content-desc' },
  { value: 'class', label: 'class' },
]

function ELEMENT_FIELDS(visibleWhen?: { key: string; equals: Array<string | number> }): StepFieldDef[] {
  return [
    {
      key: 'by', labelKey: 'by', type: 'select', required: true, default: 'text',
      options: BY_OPTIONS,
      visibleWhen,
    },
    {
      key: 'value', labelKey: 'value', type: 'text', required: true, default: '',
      visibleWhen,
    },
    {
      key: 'timeout_ms', labelKey: 'timeoutMs', type: 'number', default: 10000,
      visibleWhen,
    },
    {
      key: 'instance', labelKey: 'instance', type: 'number', default: 0,
      visibleWhen: { key: 'by', equals: ['class'] },
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
      key: 'x', labelKey: 'x', type: 'number', required: true, default: 540,
      visibleWhen: { key: 'mode', equals: ['coord'] },
    },
    {
      key: 'y', labelKey: 'y', type: 'number', required: true, default: 960,
      visibleWhen: { key: 'mode', equals: ['coord'] },
    },
    ...ELEMENT_FIELDS({ key: 'mode', equals: ['element'] }),
  ],
  swipe: [
    { key: 'x1', labelKey: 'x1', type: 'number', required: true, default: 540 },
    { key: 'y1', labelKey: 'y1', type: 'number', required: true, default: 1200 },
    { key: 'x2', labelKey: 'x2', type: 'number', required: true, default: 540 },
    { key: 'y2', labelKey: 'y2', type: 'number', required: true, default: 400 },
    { key: 'duration_ms', labelKey: 'durationMs', type: 'number', default: 300 },
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
    ...ELEMENT_FIELDS({ key: 'mode', equals: ['element'] }),
  ],
  input: [
    { key: 'text', labelKey: 'text', type: 'textarea', required: true, default: '' },
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
  // Legacy element actions — kept readable/editable for existing scripts,
  // but no longer offered in the "add step" menu.
  tap_element: ELEMENT_FIELDS(),
  wait_element: ELEMENT_FIELDS(),
  assert_element: [
    ...ELEMENT_FIELDS(),
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

/** Build a fresh step of the given action from the schema defaults. */
export function defaultStep(action: StepAction): Step {
  const step: Step = { action }
  for (const f of STEP_FIELDS[action] || []) {
    if (f.default === undefined) continue
    // Skip fields hidden under the step's current mode — no stale by/value
    // pairs on a coord-mode tap, no ms on an element-mode wait, etc.
    if (f.visibleWhen && !f.visibleWhen.equals.includes(step[f.visibleWhen.key] as string | number)) {
      continue
    }
    step[f.key] = f.default
  }
  return step
}
