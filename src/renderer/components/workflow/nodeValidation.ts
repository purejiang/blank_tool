/**
 * 节点可编辑性校验 + 生效端口解析（纯函数，面板与页面共用一份实现）。
 *
 * 为什么单独成模块：同一个判断（这个节点要编辑哪套端口？哪些必填还没填？）
 * 过去散在三个地方——`NodeConfigPanel` 的保存逻辑、`WorkflowEditorPage` 的
 * `upstreamNodes`、后端 `validate_workflow` 的检查 2——改一处就会漂移。现在面板
 * 用它做**字段级即时提示**，页面用它做**顶栏保存门禁**，两边永远一致。
 *
 * 口径与后端对齐（cli/app/workflow/validation.py 检查 2）：
 *  - 「缺必填」只在参数**整个缺失**时报；表达式值 `$inputs.x` 视为已填（运行时
 *    才解析）；
 *  - boolean 端口永远可满足（`false` 是合法值）；
 *  - 工具没声明端口时不做检查（无从判断）。
 *
 * 「选择端口没有选项」这种态由 `portJsonToTypeKey` 的结构决定不可能出现
 * （没有 options 就不是选择端口），所以这里不设那一条规则。
 *
 * 这里只报 error；warning 类的问题（类型不匹配、未知端口引用）留在
 * expressionBinding 的 `validateValue` 与后端的 `workflow.validate` 里。
 */
import { portJsonToTypeKey } from './ioAuthoring'
import type { ToolOperation, WorkflowToolInfo } from './toolMeta'

/** 端口形状（容忍 TypeScript 侧的松散数据与后端 PortSet 的完整形态）。 */
export interface EffectivePortShape {
  name: string
  type?: string | { base?: string; subtype?: string | null }
  required?: boolean
  description?: string
  options?: unknown
  multi?: unknown
}

/** 节点生效的输入/输出端口。 */
export interface EffectivePorts {
  /** 面板要展示/编辑的输入端口（operation 模式取该操作的，否则取工具的）。 */
  inputs: EffectivePortShape[]
  /** 只读展示的输出端口。 */
  outputs: EffectivePortShape[]
  /** 工具是否走 operation 模式（声明了操作）。 */
  operationMode: boolean
  /** 当前选中的操作名（未选 / 非法 → null）。 */
  operation: string | null
  /** 当前选中的操作声明（无则 null）。 */
  currentOperation: ToolOperation | null
}

/** 一条阻塞性问题；`field` 用于把提示挂到对应控件上。 */
export interface NodeIssue {
  /** `'operation'` 或端口名。 */
  field: string
  /** vue-i18n key：`workflow.editor.config.errors.<code>`。 */
  messageKey: string
  /** 稳定机器码（测试断言用）。 */
  code: 'noOperation' | 'missingRequired'
  params?: Record<string, string>
}

/** 宽松读取节点 data（NodeConfigPanel / 页面都持有未严格类型的 data）。 */
export interface NodeEditableData {
  tool?: unknown
  ports?: { inputs?: unknown; outputs?: unknown } | null
  operation?: unknown
  inputs?: Record<string, unknown> | null
  params?: Record<string, unknown> | null
  [key: string]: unknown
}

function toPorts(raw: unknown): EffectivePortShape[] {
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (port): port is EffectivePortShape =>
      !!port && typeof port === 'object' && typeof (port as EffectivePortShape).name === 'string',
  )
}

/** 端口类型的基础名（容忍裸字符串与 `{base}` 两种形态）。 */
export function portBaseOf(type: EffectivePortShape['type']): string {
  if (typeof type === 'string') return type.toLowerCase()
  if (type && typeof type === 'object' && typeof type.base === 'string') return type.base.toLowerCase()
  return ''
}

/** 该工具声明的操作（非数组 / 缺字段一律视为「没有操作」）。 */
export function toolOperations(toolInfo: WorkflowToolInfo | null | undefined): ToolOperation[] {
  const operations = toolInfo?.operations
  return Array.isArray(operations) ? operations : []
}

/**
 * 解析节点实际生效的端口与操作。
 *
 * operation 模式下，一个**已失效**的操作名（工具已不再声明它）按「未选」处理：
 * 面板会提示重选，而不是拿着上一版的端口集去编辑。
 */
export function effectivePorts(
  data: NodeEditableData | null | undefined,
  toolInfo: WorkflowToolInfo | null | undefined,
): EffectivePorts {
  const operations = toolOperations(toolInfo)
  const operationMode = operations.length > 0
  const requested = typeof data?.operation === 'string' && data.operation ? data.operation : null
  const currentOperation = requested
    ? operations.find((operation) => operation?.name === requested) ?? null
    : null

  const toolInputs = toPorts(toolInfo?.ports?.inputs)
  const toolOutputs = toPorts(toolInfo?.ports?.outputs)

  if (!operationMode) {
    return {
      inputs: toolInputs,
      outputs: toolOutputs,
      operationMode: false,
      operation: null,
      currentOperation: null,
    }
  }

  return {
    inputs: currentOperation ? toPorts(currentOperation.inputs) : [],
    outputs: currentOperation ? toPorts(currentOperation.outputs) : toolOutputs,
    operationMode: true,
    operation: currentOperation ? currentOperation.name : null,
    currentOperation,
  }
}

/** 节点当前存值的容器：operation 模式看 `inputs`，否则看 `params`。 */
export function boundValues(data: NodeEditableData | null | undefined, operationMode: boolean) {
  const source = operationMode ? data?.inputs : data?.params
  return source && typeof source === 'object' ? (source as Record<string, unknown>) : {}
}

/** 与面板/后端一致的「空值」判定（缺键、null、空串、空数组）。 */
export function isEmptyValue(value: unknown): boolean {
  if (value === undefined || value === null || value === '') return true
  return Array.isArray(value) && value.length === 0
}

/** 后端 Port 的 required 缺省为 true。 */
export function isRequiredPort(port: EffectivePortShape): boolean {
  return port.required !== false
}

function selectOptions(port: EffectivePortShape): unknown[] {
  return Array.isArray(port.options) ? port.options : []
}

/**
 * 这个节点现在有没有「不填就跑不了」的问题。
 *
 * 页面用它决定顶栏「保存」是否被挡住（并给出是哪个节点），面板用它做字段级
 * 提示——同一份结果，两种呈现。
 */
export function validateNodeEditable(
  data: NodeEditableData | null | undefined,
  toolInfo: WorkflowToolInfo | null | undefined,
): NodeIssue[] {
  const ports = effectivePorts(data, toolInfo)
  const issues: NodeIssue[] = []

  if (ports.operationMode && !ports.operation) {
    issues.push({
      field: 'operation',
      code: 'noOperation',
      messageKey: 'workflow.editor.config.errors.noOperation',
    })
    // 未选操作时端口集是空的，再报别的只会是噪音。
    return issues
  }

  const values = boundValues(data, ports.operationMode)
  const missing: string[] = []

  for (const port of ports.inputs) {
    const kind = portJsonToTypeKey({
      name: port.name,
      type: { base: portBaseOf(port.type) },
      options: selectOptions(port) as string[],
      multi: port.multi === true,
    })
    if (!isRequiredPort(port)) continue
    // boolean 永远可满足（false 是合法的已绑定值）。
    if (kind === 'boolean') continue
    if (isEmptyValue(values[port.name])) missing.push(port.name)
  }

  if (missing.length > 0) {
    issues.push({
      field: missing[0],
      code: 'missingRequired',
      messageKey: 'workflow.editor.config.errors.missingRequired',
      params: { names: missing.join(', ') },
    })
  }

  return issues
}

/** 该节点上第一条问题（面板把它显示在字段下方）。 */
export function issueForField(issues: readonly NodeIssue[], field: string): NodeIssue | null {
  return issues.find((issue) => issue.field === field) ?? null
}
