/**
 * Workflow expression ("placeholder") bindings — pure helpers for the editor.
 *
 * The engine (cli/app/workflow/expression.py) resolves `$`-references inside
 * any node param. Two forms exist and the difference matters:
 *
 *   whole value   `"$nodes.scan.outputs.count"` — a string that IS one
 *                 expression. The resolved value keeps its own type (a number
 *                 stays a number, an object stays an object).
 *   interpolation `"found ${nodes.scan.outputs.count} matches"` — any string
 *                 containing `${...}`; each occurrence is rendered as TEXT.
 *                 `$${` produces a literal `${`.
 *
 * Consequences this module encodes:
 *  - `insertBinding` picks the whole-value form for an EMPTY field and the
 *    interpolation form when the field already has text (so typing a prefix
 *    cannot silently destroy a typed binding);
 *  - if a value mixes a bare leading `$expr` with `${...}` somewhere, the
 *    engine takes the interpolation path and the bare part stays LITERAL text
 *    — reported as a warning;
 *  - `$nodes.<id>.*` may only reference UPSTREAM nodes: the engine accumulates
 *    results as it walks the chain, so a downstream reference fails at runtime
 *    with "missing node". The editor therefore blocks it up front.
 *
 * Allowed roots / pipes / path shapes mirror expression.py exactly; keep the
 * two in sync when the engine gains a root or a pipe.
 *
 * Pure and Vue-free (see tests/unit/workflow-editor/expressionBinding.test.ts).
 */

import { isPortCompatible } from './PortConnection'

/** Context roots the engine accepts (`ExpressionEngine._roots`). */
export const EXPRESSION_ROOTS = ['inputs', 'nodes', 'env', 'workdir', 'rundir'] as const
export type ExpressionRoot = (typeof EXPRESSION_ROOTS)[number]

/** Built-in pipe transforms (`ExpressionEngine._pipes`). */
export const EXPRESSION_PIPES = ['basename', 'dirname', 'default'] as const
export type ExpressionPipe = (typeof EXPRESSION_PIPES)[number]

/** Node result sections reachable through `$nodes.<id>.<section>.<key>`. */
export const NODE_SECTIONS = ['outputs', 'params'] as const

/** Picker groups (labels are i18n'd by the consumer). */
export const BINDING_GROUPS = ['inputs', 'nodes', 'runtime'] as const
export type BindingGroup = (typeof BINDING_GROUPS)[number]

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** One reference offered by the picker. */
export interface ReferenceCandidate {
  /** Expression body without `$`: e.g. `nodes.convert.outputs.apks_path`. */
  path: string
  /** Display name (port / input / variable name). */
  label: string
  /** Secondary text (node id, tool, type), already human-readable. */
  detail?: string
  group: BindingGroup
}

/** Port shape needed for validation/type checks (structurally compatible). */
export interface BindingPort {
  name: string
  type?: string | { base?: string; subtype?: string | null }
  description?: string
}

/** Per-node info used to validate `$nodes.<id>.*` references. */
export interface BindingNodeInfo {
  label?: string
  tool?: string
  outputs?: BindingPort[]
  /** Keys of the node's saved params/inputs (for `.params.<key>`). */
  paramKeys?: string[]
}

/** Everything `validateValue` needs to judge a bound value. */
export interface BindingContext {
  /** Declared workflow input names (meta.inputs). */
  inputNames?: readonly string[]
  /** Node id → info, for `$nodes.<id>.outputs.<port>` / `.params.<key>`. */
  nodes?: Record<string, BindingNodeInfo>
  /**
   * Ids of nodes that execute BEFORE the edited node. When provided, a
   * reference to any other node is an error (runtime "missing node").
   */
  upstreamIds?: readonly string[]
  /** Base type of the port this value is bound to (type-mismatch warning). */
  targetBase?: string | null
}

/** One finding for a bound value. */
export interface BindingIssue {
  severity: 'error' | 'warning'
  /** Stable machine code (asserted by tests). */
  code: string
  /** vue-i18n key: `workflow.editor.binding.errors|warnings.<code>`. */
  messageKey: string
  /** Interpolation params for the i18n message. */
  params?: Record<string, string>
}

/** One recognised binding inside a value. */
export interface BindingToken {
  /** Exact source text of the token. */
  raw: string
  start: number
  end: number
  /** True for a bare `$root...` whole-value expression. */
  wholeValue: boolean
  /** Expression body without `$`/`${}` and without the pipe tail. */
  path: string
  /** Pipe tail as written, e.g. `['basename', 'default:x']`. */
  pipes: string[]
}

/** A `$`-trigger typed by the user, used to open the candidate picker. */
export interface BindingTrigger {
  /** Index in the value where the replacement starts. */
  start: number
  /** Text typed after `$` (or `${`) — used to filter candidates. */
  fragment: string
  /** True when the trigger sits inside an already-open `${`. */
  interpolation: boolean
}

// ---------------------------------------------------------------------------
// Building references
// ---------------------------------------------------------------------------

/** `${` marker (kept as constants so the escape rules stay readable). */
const INTERP_OPEN = '${'
const ESCAPED_INTERP_OPEN = '$${'

/** Join a path with optional pipes into an expression body (no `$`, no braces). */
export function withPipes(path: string, pipes?: readonly string[] | null): string {
  const clean = (pipes ?? []).map((pipe) => String(pipe).trim()).filter((pipe) => pipe.length > 0)
  return clean.length > 0 ? `${path} | ${clean.join(' | ')}` : path
}

/** `nodes.a.outputs.b` + `['basename']` → `$nodes.a.outputs.b | basename`. */
export function toWholeValueRef(path: string, pipes?: readonly string[] | null): string {
  return `$${withPipes(path, pipes)}`
}

/** `nodes.a.outputs.b` → `${nodes.a.outputs.b}` (text interpolation). */
export function toInterpolationRef(path: string, pipes?: readonly string[] | null): string {
  return `${INTERP_OPEN}${withPipes(path, pipes)}}`
}

/** Path for a workflow input: `inputs.<name>`. */
export function inputPath(name: string): string {
  return `inputs.${name}`
}

/** Path for a node output: `nodes.<id>.outputs.<port>`. */
export function nodeOutputPath(nodeId: string, portName: string): string {
  return `nodes.${nodeId}.outputs.${portName}`
}

/** Path for a node's resolved param: `nodes.<id>.params.<key>`. */
export function nodeParamPath(nodeId: string, key: string): string {
  return `nodes.${nodeId}.params.${key}`
}

// ---------------------------------------------------------------------------
// Trigger detection + insertion
// ---------------------------------------------------------------------------

/**
 * Detect a `$`-trigger at the tail of *value*.
 *
 * Both shapes open the picker: a bare whole-value start (`$inp`, at the start
 * of the field or after whitespace) and an open interpolation (`${nod`).
 * Returns null when there is nothing to complete.
 */
export function findTrigger(value: unknown): BindingTrigger | null {
  if (typeof value !== 'string' || value.length === 0) return null

  const openIdx = value.lastIndexOf(INTERP_OPEN)
  const closeIdx = value.lastIndexOf('}')
  if (openIdx > closeIdx) {
    const fragment = value.slice(openIdx + INTERP_OPEN.length)
    // Still typing a path inside `${...}`: letters, digits, dots, underscores.
    if (!/^[A-Za-z0-9_.]*$/.test(fragment)) return null
    return { start: openIdx, fragment, interpolation: true }
  }

  const match = /\$([A-Za-z0-9_.]*)$/.exec(value)
  if (!match) return null
  const start = match.index
  // `$$` is the escape for a literal `$` — never a trigger.
  if (start > 0 && value[start - 1] === '$') return null
  return { start, fragment: match[1], interpolation: false }
}

/**
 * True when *ref* is a plausible completion for *trigger* (filtering only —
 * the picker also offers everything when the fragment is empty).
 */
export function matchesTrigger(candidate: string, trigger: BindingTrigger | null): boolean {
  if (!trigger || trigger.fragment.length === 0) return true
  const fragment = trigger.fragment.toLowerCase()
  const haystack = String(candidate ?? '').toLowerCase()
  if (haystack.includes(fragment)) return true
  // Also match on the last path segment ("apks_path" → nodes.a.outputs.apks_path).
  const lastSegment = haystack.slice(haystack.lastIndexOf('.') + 1)
  return lastSegment.startsWith(fragment)
}

/**
 * Complete a detected trigger with *path* (and optional pipes).
 *
 * The replacement keeps the whole-value form only when nothing else remains in
 * the field; otherwise it becomes an interpolation, because a whole-value
 * expression mixed with text would be a literal string.
 */
export function completeTrigger(
  value: string,
  trigger: BindingTrigger,
  path: string,
  pipes?: readonly string[] | null,
): string {
  const before = value.slice(0, trigger.start)
  if (trigger.interpolation) {
    return `${before}${toInterpolationRef(path, pipes)}`
  }
  return before.trim().length === 0
    ? `${before}${toWholeValueRef(path, pipes)}`
    : `${before}${toInterpolationRef(path, pipes)}`
}

/**
 * Insert a binding into *value* (the "插入引用" button path — no trigger typed).
 *
 * Empty field → whole-value reference (typed value preserved by the engine);
 * non-empty field → appended `${...}` interpolation. A trailing `$fragment`
 * trigger is completed instead of appending (so the type-ahead and the button
 * agree).
 */
export function insertBinding(value: unknown, path: string, pipes?: readonly string[] | null): string {
  const current = typeof value === 'string' ? value : ''
  const trigger = findTrigger(current)
  if (trigger) return completeTrigger(current, trigger, path, pipes)

  if (current.trim().length === 0) return toWholeValueRef(path, pipes)
  const separator = /\s$/.test(current) ? '' : ' '
  return `${current}${separator}${toInterpolationRef(path, pipes)}`
}

// ---------------------------------------------------------------------------
// Scanning
// ---------------------------------------------------------------------------

/**
 * Every binding appearing in *value*.
 *
 * Interpolations are found anywhere; a bare whole-value expression is only
 * recognised when the string starts with `$` AND contains no `${` — the same
 * precedence the engine applies (`resolve`). `$$`/`$${` escapes are skipped.
 */
export function collectBindings(value: unknown): BindingToken[] {
  if (typeof value !== 'string' || value.length === 0) return []
  const tokens: BindingToken[] = []

  let index = 0
  let hasInterpolation = false
  while (index < value.length) {
    if (value.startsWith(ESCAPED_INTERP_OPEN, index)) {
      index += ESCAPED_INTERP_OPEN.length
      continue
    }
    if (value.startsWith(INTERP_OPEN, index)) {
      const closing = value.indexOf('}', index + INTERP_OPEN.length)
      if (closing === -1) break
      const body = value.slice(index + INTERP_OPEN.length, closing)
      const { path, pipes } = splitPipes(body)
      tokens.push({
        raw: value.slice(index, closing + 1),
        start: index,
        end: closing + 1,
        wholeValue: false,
        path,
        pipes,
      })
      hasInterpolation = true
      index = closing + 1
      continue
    }
    index += 1
  }

  if (hasInterpolation) return tokens
  if (!value.startsWith('$') || value.startsWith('$$')) return tokens
  const { path, pipes } = splitPipes(value.slice(1))
  if (path.length === 0) return tokens
  tokens.push({ raw: value, start: 0, end: value.length, wholeValue: true, path, pipes })
  return tokens
}

/** Split an expression body into its path and pipe tail. */
export function splitPipes(body: string): { path: string; pipes: string[] } {
  const segments = String(body ?? '').split(' | ')
  const path = (segments[0] ?? '').trim()
  const pipes = segments.slice(1).map((pipe) => pipe.trim()).filter((pipe) => pipe.length > 0)
  return { path, pipes }
}

/** Remove a binding token from a value (chip "×" affordance). */
export function removeBinding(value: unknown, token: BindingToken): string {
  if (typeof value !== 'string') return ''
  const before = value.slice(0, token.start)
  const after = value.slice(token.end)
  return `${before}${after}`.replace(/\s{2,}/g, ' ').trim()
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

const DUNDER_RE = /^_/

function portBase(port: BindingPort | undefined): string {
  const type = port?.type
  if (typeof type === 'string') return type.toLowerCase()
  if (type && typeof type === 'object' && typeof type.base === 'string') return type.base.toLowerCase()
  return ''
}

function issue(severity: 'error' | 'warning', code: string, params?: Record<string, string>): BindingIssue {
  return {
    severity,
    code,
    messageKey: `workflow.editor.binding.${severity === 'error' ? 'errors' : 'warnings'}.${code}`,
    params,
  }
}

/**
 * Validate one expression path (already split from its pipes).
 *
 * Returns every problem found; an empty list means the path is resolvable in
 * principle (the engine remains the authority at runtime).
 */
function validatePath(path: string, ctx: BindingContext): BindingIssue[] {
  const issues: BindingIssue[] = []
  if (path.length === 0) return [issue('error', 'emptyExpression')]
  if (path.includes(' ')) {
    return [issue('error', 'spacesInExpression', { path })]
  }

  const parts = path.split('.')
  for (const part of parts) {
    if (DUNDER_RE.test(part)) return [issue('error', 'privateAccess', { part })]
  }

  const root = parts[0] as ExpressionRoot
  if (!(EXPRESSION_ROOTS as readonly string[]).includes(root)) {
    return [issue('error', 'unknownRoot', { root })]
  }

  const rest = parts.slice(1)
  switch (root) {
    case 'workdir':
    case 'rundir':
      if (rest.length > 0) issues.push(issue('error', 'rootTakesNoKeys', { root, path }))
      break
    case 'inputs': {
      if (rest.length !== 1) {
        issues.push(issue('error', 'malformedPath', { path, expected: '$inputs.<key>' }))
        break
      }
      const names = ctx.inputNames
      if (names && !names.includes(rest[0])) {
        issues.push(issue('warning', 'unknownInput', { key: rest[0] }))
      }
      break
    }
    case 'env': {
      if (rest.length !== 1) {
        issues.push(issue('error', 'malformedPath', { path, expected: '$env.<name>' }))
      }
      break
    }
    case 'nodes': {
      issues.push(...validateNodePath(path, rest, ctx))
      break
    }
    default:
      break
  }
  return issues
}

function validateNodePath(path: string, rest: string[], ctx: BindingContext): BindingIssue[] {
  const issues: BindingIssue[] = []
  if (rest.length !== 3) {
    return [
      issue('error', 'malformedPath', {
        path,
        expected: '$nodes.<id>.outputs.<port> | $nodes.<id>.params.<key>',
      }),
    ]
  }
  const [nodeId, section, key] = rest
  if (!(NODE_SECTIONS as readonly string[]).includes(section)) {
    return [issue('error', 'unknownSection', { section, nodeId })]
  }

  const nodes = ctx.nodes
  if (!nodes || !nodes[nodeId]) {
    return [issue('error', 'unknownNode', { nodeId })]
  }
  if (ctx.upstreamIds && !ctx.upstreamIds.includes(nodeId)) {
    // The engine accumulates node results as it walks the chain: a downstream
    // reference can only fail at runtime.
    return [issue('error', 'notUpstream', { nodeId })]
  }

  const info = nodes[nodeId]
  if (section === 'outputs') {
    const port = (info.outputs ?? []).find((entry) => entry.name === key)
    if (!port) {
      issues.push(issue('warning', 'unknownOutputPort', { nodeId, port: key }))
      return issues
    }
    const targetBase = ctx.targetBase
    const sourceBase = portBase(port)
    if (targetBase && sourceBase && !isPortCompatible(sourceBase, targetBase)) {
      issues.push(
        issue('warning', 'typeMismatch', { nodeId, port: key, source: sourceBase, target: targetBase }),
      )
    }
  } else {
    const keys = info.paramKeys ?? []
    if (keys.length > 0 && !keys.includes(key)) {
      issues.push(issue('warning', 'unknownParamKey', { nodeId, key }))
    }
  }
  return issues
}

function validatePipes(pipes: string[], path: string): BindingIssue[] {
  const issues: BindingIssue[] = []
  for (const pipe of pipes) {
    const name = pipe.split(':')[0].trim()
    if (name.length === 0) {
      issues.push(issue('error', 'emptyPipe', { path }))
      continue
    }
    if (!(EXPRESSION_PIPES as readonly string[]).includes(name)) {
      issues.push(issue('error', 'unknownPipe', { pipe: name }))
    }
  }
  return issues
}

/**
 * Validate a bound value: malformed templates, unknown roots / pipes / nodes
 * (errors) plus resolvability warnings (unknown port/key/input, type mismatch,
 * mixed whole-value + interpolation).
 *
 * Errors should block saving (they can only fail at runtime); warnings are
 * informational.
 */
export function validateValue(value: unknown, ctx: BindingContext = {}): BindingIssue[] {
  if (typeof value !== 'string' || !value.includes('$')) return []

  const issues: BindingIssue[] = []
  let sawInterpolation = false

  // Pass 1 — every `${...}` occurrence (escaped `$${` skipped).
  let index = 0
  while (index < value.length) {
    if (value.startsWith(ESCAPED_INTERP_OPEN, index)) {
      index += ESCAPED_INTERP_OPEN.length
      continue
    }
    if (value.startsWith(INTERP_OPEN, index)) {
      const closing = value.indexOf('}', index + INTERP_OPEN.length)
      if (closing === -1) {
        issues.push(issue('error', 'unterminatedInterpolation'))
        return issues
      }
      const body = value.slice(index + INTERP_OPEN.length, closing).trim()
      if (body.length === 0) {
        issues.push(issue('error', 'emptyExpression'))
        return issues
      }
      const { path, pipes } = splitPipes(body)
      issues.push(...validatePath(path, ctx), ...validatePipes(pipes, path))
      sawInterpolation = true
      index = closing + 1
      continue
    }
    index += 1
  }

  if (!sawInterpolation && value.startsWith('$') && !value.startsWith('$$')) {
    // Whole-value expression: the engine keeps its type, and the WHOLE string
    // must be one expression.
    const { path, pipes } = splitPipes(value.slice(1))
    issues.push(...validatePath(path, ctx), ...validatePipes(pipes, path))
    return issues
  }

  if (sawInterpolation) {
    // The engine interpolates as soon as `${` appears; a bare leading `$expr`
    // in the same string therefore stays LITERAL text.
    const leading = /^\$([A-Za-z][A-Za-z0-9_.]*)/.exec(value)
    if (leading) {
      issues.push(issue('warning', 'mixedBindingForms', { path: leading[1] }))
    }
  }

  return issues
}

/** True when at least one issue blocks saving. */
export function hasBlockingIssue(issues: readonly BindingIssue[]): boolean {
  return issues.some((entry) => entry.severity === 'error')
}
