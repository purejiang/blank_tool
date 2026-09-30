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

import { portJsonToTypeKey, type PortTypeKey } from './ioAuthoring'
import { isPortCompatible } from './PortConnection'
import { portTypeLabel } from './toolMeta'

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
  /** 该候选的类型（用于类型徽标与兼容性排序）；runtime/env 项没有。 */
  typeKey?: PortTypeKey
  /** 端口 subtype（徽标上的 `文件 · apk` 后缀）。 */
  subtype?: string | null
  /** 候选来源：入参 / 节点输出 / 节点已解析参数 / 运行时。 */
  kind: 'input' | 'output' | 'param' | 'runtime' | 'env'
  /** `kind === 'output'` 时所属节点（分组标题与 chip 友好名要用）。 */
  nodeId?: string
  /** 节点展示名（`label` 优先，回落 id）。 */
  nodeLabel?: string
  /** 运行时项：`workdir` / `rundir` 的 i18n key。 */
  runtimeKey?: 'workdir' | 'rundir'
}

/** 选择器里的一组候选：工作流入参 / 某个上游节点 / 运行时。 */
export interface ReferenceGroup {
  /** 稳定 key：`inputs` / `runtime` / `node:<id>`。 */
  key: string
  /** 大组（i18n 用）；节点组也归 `nodes`。 */
  group: BindingGroup
  /** 节点组：节点 id 与展示名。 */
  nodeId?: string
  nodeLabel?: string
  /** 节点组：该节点的工具名（标题副文本）。 */
  nodeTool?: string
  items: ReferenceCandidate[]
}

/** Port shape needed for validation/type checks (structurally compatible). */
export interface BindingPort {
  name: string
  type?: string | { base?: string; subtype?: string | null }
  description?: string
  /** Select-like port options (used for the type badge). */
  options?: unknown
  /** Select-like multi flag (used for the type badge). */
  multi?: unknown
}

/** 上游节点（结构上兼容 toolMeta.UpstreamNodeRef）。 */
export interface UpstreamBindingRef {
  id: string
  label?: string
  tool?: string
  outputs?: BindingPort[]
  /** Keys of the node's saved params/inputs (for `.params.<key>`). */
  paramKeys?: string[]
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
// Candidate discovery (the picker's data source — pure, so it is unit-testable)
// ---------------------------------------------------------------------------

/** 端口类型 → 类型徽标用的 UI 类型键（与节点面板口径一致）。 */
function candidateTypeKey(port: BindingPort | undefined): PortTypeKey | undefined {
  if (!port) return undefined
  const base = portBase(port)
  if (!base) return undefined
  return portJsonToTypeKey({
    name: port.name,
    type: { base },
    options: Array.isArray(port.options) ? (port.options as string[]) : [],
    multi: port.multi === true,
  })
}

function candidateSubtype(port: BindingPort | undefined): string | null {
  const type = port?.type
  if (type && typeof type === 'object' && typeof type.subtype === 'string') return type.subtype
  return null
}

/**
 * 按来源分组收集候选：工作流入参 → 每个上游节点一组（输出端口 + 已解析参数）
 * → 运行时上下文。
 *
 * 分组只描述"数据从哪来"，i18n 文案由组件负责（这里返回结构化的 key / 名字），
 * 因此本函数保持纯函数、可用单测锁住候选集合。
 */
export function buildReferenceGroups(
  inputs?: readonly BindingPort[] | null,
  upstreamNodes?: readonly UpstreamBindingRef[] | null,
): ReferenceGroup[] {
  const groups: ReferenceGroup[] = []

  const inputItems: ReferenceCandidate[] = []
  for (const port of inputs ?? []) {
    if (!port?.name) continue
    inputItems.push({
      path: inputPath(port.name),
      label: port.name,
      detail: portBase(port),
      group: 'inputs',
      kind: 'input',
      typeKey: candidateTypeKey(port),
      subtype: candidateSubtype(port),
    })
  }
  if (inputItems.length > 0) {
    groups.push({ key: 'inputs', group: 'inputs', items: inputItems })
  }

  for (const node of upstreamNodes ?? []) {
    if (!node?.id) continue
    const items: ReferenceCandidate[] = []
    for (const port of node.outputs ?? []) {
      if (!port?.name) continue
      items.push({
        path: nodeOutputPath(node.id, port.name),
        label: port.name,
        detail: port.type ? portTypeLabel(normalizeTypeRef(port.type)) : undefined,
        group: 'nodes',
        kind: 'output',
        nodeId: node.id,
        nodeLabel: node.label || node.id,
        typeKey: candidateTypeKey(port),
        subtype: candidateSubtype(port),
      })
    }
    for (const key of node.paramKeys ?? []) {
      if (!key) continue
      items.push({
        path: nodeParamPath(node.id, key),
        label: key,
        group: 'nodes',
        kind: 'param',
        nodeId: node.id,
        nodeLabel: node.label || node.id,
      })
    }
    if (items.length > 0) {
      groups.push({
        key: `node:${node.id}`,
        group: 'nodes',
        nodeId: node.id,
        nodeLabel: node.label || node.id,
        nodeTool: node.tool,
        items,
      })
    }
  }

  groups.push({
    key: 'runtime',
    group: 'runtime',
    items: [
      { path: 'workdir', label: 'workdir', group: 'runtime', kind: 'runtime', runtimeKey: 'workdir' },
      { path: 'rundir', label: 'rundir', group: 'runtime', kind: 'runtime', runtimeKey: 'rundir' },
      // 环境变量名无法枚举，用一个"点开输入变量名"的条目占位。
      { path: '', label: 'env', group: 'runtime', kind: 'env' },
    ],
  })

  return groups
}

/** `portTypeLabel` 需要 `{base, subtype}`；裸字符串类型补齐成该形状。 */
function normalizeTypeRef(type: BindingPort['type']): { base: string; subtype: string | null } {
  if (typeof type === 'string') return { base: type, subtype: null }
  return { base: String(type?.base ?? ''), subtype: type?.subtype ?? null }
}

/**
 * 类型兼容的候选排前面，不兼容的排后面（组件把它们置灰）。
 *
 * `targetBase` 缺失时保持原顺序 —— 排序是"锦上添花"，不该改变没有目标类型的
 * 场景下的稳定顺序。
 */
export function sortByCompatibility(
  items: readonly ReferenceCandidate[],
  targetBase?: string | null,
): ReferenceCandidate[] {
  if (!targetBase) return [...items]
  const score = (item: ReferenceCandidate) => {
    if (!item.typeKey || item.kind === 'param' || item.kind === 'runtime' || item.kind === 'env') {
      return 0 // 未知类型：既不优先也不置灰
    }
    const base = baseOfTypeKey(item.typeKey)
    return isPortCompatible(base, targetBase) ? -1 : 1
  }
  return [...items].sort((a, b) => score(a) - score(b))
}

/** UI 类型键 → 后端基础类型（select 两种都骑在 text 上）。 */
export function baseOfTypeKey(typeKey: PortTypeKey): string {
  return typeKey === 'single_select' || typeKey === 'multi_select' ? 'text' : typeKey
}

// ---------------------------------------------------------------------------
// Friendly labels for already-inserted bindings (chips)
// ---------------------------------------------------------------------------

/** chip 友好名（i18n key + 参数），组件负责渲染。 */
export interface BindingLabel {
  /** `workflow.editor.binding.chip.*` 的 key；raw 时为空串。 */
  messageKey: string
  params: Record<string, string>
  /** 原始表达式（无匹配时的回落文本，也用作 title）。 */
  raw: string
}

/**
 * 把一个已插入的引用翻译成人能读的一句话。
 *
 * 用户面对的是 `$nodes.tool-apktool-1.outputs.apk_path` 这种字符串——"看不懂"
 * 的主要来源。这里把它变成 `解压 APK · apk_path` 之类的短语；节点名来自
 * upstreamNodes（面板已经持有），未知节点/端口则原样回落。
 */
export function describeBindingToken(
  token: Pick<BindingToken, 'path' | 'pipes'>,
  ctx: { nodes?: Record<string, BindingNodeInfo>; inputs?: readonly string[] } = {},
): BindingLabel {
  const path = String(token.path ?? '')
  const pipes = (token.pipes ?? []).filter((pipe) => pipe && pipe.length > 0)
  const tail = pipes.length > 0 ? ` · ${pipes.join(' | ')}` : ''
  const parts = path.split('.')
  const root = parts[0]

  const withPipes = (messageKey: string, params: Record<string, string>): BindingLabel => ({
    messageKey,
    params: { ...params, pipes: tail },
    raw: `$${path}${tail}`,
  })

  if (root === 'inputs' && parts.length === 2) {
    return withPipes('workflow.editor.binding.chip.input', { name: parts[1] })
  }
  if (root === 'env' && parts.length === 2) {
    return withPipes('workflow.editor.binding.chip.env', { name: parts[1] })
  }
  if (root === 'workdir' || root === 'rundir') {
    return withPipes(`workflow.editor.binding.chip.${root}`, {})
  }
  if (root === 'nodes' && parts.length === 4 && (parts[2] === 'outputs' || parts[2] === 'params')) {
    const nodeId = parts[1]
    const nodeLabel = ctx.nodes?.[nodeId]?.label || nodeId
    return withPipes(
      parts[2] === 'outputs'
        ? 'workflow.editor.binding.chip.output'
        : 'workflow.editor.binding.chip.param',
      { node: nodeLabel, name: parts[3] },
    )
  }

  return { messageKey: '', params: {}, raw: `$${path}${tail}` }
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

/** 文本控件里的一次选区（插入位置）。 */
export interface InsertSelection {
  start: number
  end: number
}

/**
 * 在光标处插入引用（"插入引用"按钮的主路径）。
 *
 * 与 :func:`insertBinding` 的区别：用户已经明确点了一个位置时，引用插在那里，
 * 而不是一律追加到末尾——在长命令模板中间补一个路径是常见操作。
 *
 * 规则：
 *  - 有选区 → 用引用替换选中文本（`${...}` 插值形式，因为它在文本中间）；
 *  - 光标在末尾且字段为空 → 整值引用 `$path`（引擎保留原类型）；
 *  - 光标处正在敲 `$` / `${` → 交给 `completeTrigger` 补全（与类型提示一致）；
 *  - 其余位置 → 在光标处插入 `${...}`。
 */
export function insertBindingAt(
  value: unknown,
  path: string,
  pipes?: readonly string[] | null,
  selection?: InsertSelection | null,
): { value: string; caret: number } {
  const current = typeof value === 'string' ? value : ''
  if (!selection) {
    const next = insertBinding(current, path, pipes)
    return { value: next, caret: next.length }
  }

  const start = Math.max(0, Math.min(selection.start, current.length))
  const end = Math.max(start, Math.min(selection.end, current.length))
  const before = current.slice(0, start)
  const after = current.slice(end)

  // 光标处正在输入的 `$fragment`：就地补全，并把光标放到成品的末尾。
  const tailTrigger = start > 0 ? findTrigger(before) : null
  if (tailTrigger) {
    const completed = completeTrigger(before, tailTrigger, path, pipes)
    const next = `${completed}${after}`
    return { value: next, caret: completed.length }
  }

  // 字段里只有空白 → 就是"空字段"，插整值引用（并丢掉无意义的空白，
  // 否则 `" $path"` 不再是整值表达式，引擎会当成字面量文本）。
  if (before.trim().length === 0 && after.trim().length === 0) {
    const whole = toWholeValueRef(path, pipes)
    return { value: whole, caret: whole.length }
  }
  const inserted = toInterpolationRef(path, pipes)
  return { value: `${before}${inserted}${after}`, caret: before.length + inserted.length }
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
