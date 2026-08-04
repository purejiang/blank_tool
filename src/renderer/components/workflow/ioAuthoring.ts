/**
 * Pure workflow-level input/output port authoring helpers (T6).
 *
 * The editor panel edits a `PortDraft` per port; these functions translate
 * between the draft and the wire `PortJSON`, validate against the backend's
 * naming convention, and update port lists immutably. Keeping them pure and
 * Vue-free makes the authoring contract unit-testable without mounting the
 * vue-flow page (see tests/unit/workflow-editor/ioAuthoring.test.ts).
 *
 * Type model (decision-complete, T2 constraint): there is NO select BaseType
 * in the protocol. The 8 UI choices map to the wire as:
 *   file/directory/text/number/boolean/json → same base, no extras
 *   单选 (single_select) → base 'text' + options
 *   多选 (multi_select)  → base 'text' + options + multi:true
 * Reverse mapping: base 'text' + non-empty options (+ multi) → select kinds;
 * base 'text' without options → text; unknown bases degrade to 'text'
 * (mirrors the run dialog's portBase advisory typing).
 */
import type { PortJSON } from './serializer'

/** The 8 UI type choices, in display order. */
export type PortTypeKey =
  | 'file'
  | 'directory'
  | 'text'
  | 'number'
  | 'boolean'
  | 'json'
  | 'single_select'
  | 'multi_select'

export const PORT_TYPE_KEYS: PortTypeKey[] = [
  'file',
  'directory',
  'text',
  'number',
  'boolean',
  'json',
  'single_select',
  'multi_select',
]

/** Port naming convention enforced by the backend (snake_case identifiers). */
export const PORT_NAME_PATTERN = /^[a-z][a-z0-9_]*$/

/**
 * Validation error channels. Values are i18n keys (workflow.editor.io.errors.*)
 * so the panel resolves user-facing text via vue-i18n and tests assert on
 * stable identifiers without mounting i18n.
 */
export const IO_ERRORS = {
  nameRequired: 'workflow.editor.io.errors.nameRequired',
  nameInvalid: 'workflow.editor.io.errors.nameInvalid',
  nameDuplicate: 'workflow.editor.io.errors.nameDuplicate',
  optionsRequired: 'workflow.editor.io.errors.optionsRequired',
} as const

/** Editable form state for one port, before it is committed to meta. */
export interface PortDraft {
  name: string
  typeKey: PortTypeKey
  required: boolean
  description: string
  /** Only meaningful when typeKey is single_select / multi_select. */
  options: string[]
}

/** Defaults for a brand-new port. `required` defaults on (backend default). */
export function createEmptyDraft(): PortDraft {
  return { name: '', typeKey: 'text', required: true, description: '', options: [] }
}

/** True for the two select kinds — the only ones that carry an options list. */
export function typeKeyUsesOptions(typeKey: PortTypeKey): boolean {
  return typeKey === 'single_select' || typeKey === 'multi_select'
}

/** Trim every option and drop empties; order is preserved. */
function cleanOptions(options: string[] | undefined | null): string[] {
  if (!Array.isArray(options)) return []
  return options.map((o) => String(o ?? '').trim()).filter((o) => o.length > 0)
}

/** Wire base for a UI type key — both select kinds ride on base 'text' (T2). */
function wireBase(typeKey: PortTypeKey): string {
  return typeKeyUsesOptions(typeKey) ? 'text' : typeKey
}

/** Draft → wire PortJSON. Performs NO validation; call validatePortDraft first. */
export function portFromDraft(draft: PortDraft): PortJSON {
  const port: PortJSON = {
    name: draft.name.trim(),
    type: { base: wireBase(draft.typeKey) },
    required: draft.required,
  }
  const description = draft.description.trim()
  if (description) port.description = description
  if (typeKeyUsesOptions(draft.typeKey)) {
    port.options = cleanOptions(draft.options)
    if (draft.typeKey === 'multi_select') port.multi = true
  }
  return port
}

/** Wire PortJSON → UI type key (reverse mapping; see module header). */
export function portJsonToTypeKey(port: PortJSON): PortTypeKey {
  const base = String(port?.type?.base ?? '').toLowerCase()
  if (base === 'text') {
    if (cleanOptions(port?.options).length > 0) {
      return port?.multi ? 'multi_select' : 'single_select'
    }
    return 'text'
  }
  if (
    base === 'file' ||
    base === 'directory' ||
    base === 'number' ||
    base === 'boolean' ||
    base === 'json'
  ) {
    return base
  }
  // Advisory typing: unknown/missing bases degrade to text, same as portBase
  // in WorkflowEditorPage's run dialog.
  return 'text'
}

/** Wire PortJSON → editable draft (deep enough: options array is copied). */
export function draftFromPort(port: PortJSON): PortDraft {
  return {
    name: port.name,
    typeKey: portJsonToTypeKey(port),
    required: port.required !== false,
    description: typeof port.description === 'string' ? port.description : '',
    options: Array.isArray(port.options) ? [...port.options] : [],
  }
}

/**
 * Validate a draft against its sibling ports. Returns an IO_ERRORS i18n key,
 * or null when the draft may be committed.
 *
 * @param siblings the CURRENT port list of the side being edited.
 * @param originalName the port's name before editing (edit mode); excludes
 *   the port itself from the duplicate check when the name was kept.
 */
export function validatePortDraft(
  draft: PortDraft,
  siblings: PortJSON[],
  originalName?: string,
): string | null {
  const name = draft.name.trim()
  if (!name) return IO_ERRORS.nameRequired
  if (!PORT_NAME_PATTERN.test(name)) return IO_ERRORS.nameInvalid
  if ((siblings ?? []).some((p) => p?.name === name && name !== originalName)) {
    return IO_ERRORS.nameDuplicate
  }
  if (typeKeyUsesOptions(draft.typeKey) && cleanOptions(draft.options).length === 0) {
    return IO_ERRORS.optionsRequired
  }
  return null
}

/** commitPort result: either a validation error or the new immutable list. */
export type CommitResult = { error: string; ports?: undefined } | { error: null; ports: PortJSON[] }

/**
 * Validate + normalize + upsert a draft in one step (the seam the panel calls
 * on Save). Never mutates the input list.
 *
 * New ports append; edits (originalName given) replace in place, preserving
 * list position across renames.
 */
export function commitPort(
  ports: PortJSON[],
  draft: PortDraft,
  originalName?: string,
): CommitResult {
  const error = validatePortDraft(draft, ports, originalName)
  if (error) return { error }

  const port = portFromDraft(draft)
  const existing = (ports ?? []).filter((p) => p && typeof p.name === 'string')
  if (originalName && existing.some((p) => p.name === originalName)) {
    return { error: null, ports: existing.map((p) => (p.name === originalName ? port : p)) }
  }
  return { error: null, ports: [...existing, port] }
}

/** Immutable removal by name; unknown names leave the list content unchanged. */
export function removePortByName(ports: PortJSON[], name: string): PortJSON[] {
  return (ports ?? []).filter((p) => p?.name !== name)
}
