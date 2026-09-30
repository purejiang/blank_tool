/**
 * 节点行为默认值（设置 → 节点）的读写与归一化。
 *
 * 语义：节点在「行为」里选择 **跟随系统** 时，它不把自己的失败策略 / 重试次数
 * 写进工作流 JSON（wire 上就是字段缺省），运行时由这里读出的默认值决定；选择
 * **自定义** 时字段被写死，永远覆盖默认值（包括显式的 `fail` / `0`）。
 *
 * 两处消费：
 *  - `NodeConfigPanel` 用它展示「跟随系统」当前生效的值；
 *  - 运行入口（`useWorkflowRun` / 编辑器 / 任务页 / 运行记录复跑）用
 *    `toWireNodeDefaults()` 把值放进 execute 请求的 `node_defaults` 参数。
 *
 * 存储形态是 appConfig 的 `nodes` 组（camelCase，见 src/main/stores/appStore.ts）；
 * wire 形态是后端的 `{ on_failure, retry }`（snake_case）。两者在这里转换，
 * 其它地方一律不拼字段名。
 *
 * 读失败 / 缺字段 / 非法值一律回落到内置默认（fail / 0），因为这是一份 UI 配置，
 * 不该让工作流跑不起来。
 */
import serviceManager from '@services/ServiceManager'
import { log } from '@utils/logger'

/** 失败策略字面量（与后端 `_VALID_FAILURE_MODES` 一致）。 */
export type NodeFailureMode = 'fail' | 'skip'

/** 归一化后的节点行为默认值（设置页与面板展示用的形态）。 */
export interface NodeBehaviorDefaults {
  onFailure: NodeFailureMode
  retry: number
}

/** wire 形态：后端 `node_defaults` 参数的键名。 */
export interface WireNodeDefaults {
  on_failure: NodeFailureMode
  retry: number
}

/** 内置默认值（= 后端在没有 node_defaults 时的行为）。 */
export const NODE_BEHAVIOR_FALLBACK: NodeBehaviorDefaults = { onFailure: 'fail', retry: 0 }

/** appConfig 里存这组默认值的键。 */
export const NODE_DEFAULTS_CONFIG_KEY = 'nodes'

export function isFailureMode(value: unknown): value is NodeFailureMode {
  return value === 'fail' || value === 'skip'
}

/**
 * 把 appConfig `nodes` 的原始值归一化成一份可用的默认值。
 *
 * 容忍 snake_case（`on_failure`）与字符串数字，方便手工编辑过的配置文件与
 * 后端形态的载荷都能被接受；其余非法输入静默丢弃。
 */
export function normalizeNodeDefaults(raw: unknown): NodeBehaviorDefaults {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return { ...NODE_BEHAVIOR_FALLBACK }
  const source = raw as Record<string, unknown>
  const mode = source.onFailure ?? source.on_failure
  const retryRaw = source.retry

  let retry = NODE_BEHAVIOR_FALLBACK.retry
  if (typeof retryRaw === 'number' && Number.isFinite(retryRaw)) {
    retry = Math.max(0, Math.trunc(retryRaw))
  } else if (typeof retryRaw === 'string' && retryRaw.trim() !== '') {
    const parsed = Number(retryRaw)
    if (Number.isFinite(parsed)) retry = Math.max(0, Math.trunc(parsed))
  }

  return {
    onFailure: isFailureMode(mode) ? mode : NODE_BEHAVIOR_FALLBACK.onFailure,
    retry,
  }
}

/** 归一化后的默认值 → execute 请求里的 `node_defaults`。 */
export function toWireNodeDefaults(defaults: NodeBehaviorDefaults): WireNodeDefaults {
  return { on_failure: defaults.onFailure, retry: defaults.retry }
}

/**
 * 读取设置里的节点默认值。任何失败（后端未就绪 / 没有 config 服务 / 缺键）都
 * 回落到内置默认，绝不抛错——运行路径不该因为一份 UI 配置而失败。
 */
export async function loadNodeDefaults(): Promise<NodeBehaviorDefaults> {
  try {
    const config = (await serviceManager.getService('config')) as
      | { getAppConfig?: (key?: string) => Promise<unknown> }
      | null
    if (!config || typeof config.getAppConfig !== 'function') {
      return { ...NODE_BEHAVIOR_FALLBACK }
    }
    return normalizeNodeDefaults(await config.getAppConfig(NODE_DEFAULTS_CONFIG_KEY))
  } catch (error) {
    log.warn('[nodeDefaults] falling back to built-in node defaults', error)
    return { ...NODE_BEHAVIOR_FALLBACK }
  }
}

/**
 * 运行参数里附加 `node_defaults` 的公共入口：所有 execute 调用点都走这里，
 * 「跟随系统」的节点在每个入口行为一致。
 */
export async function withNodeDefaults(
  params: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return { ...params, node_defaults: toWireNodeDefaults(await loadNodeDefaults()) }
}

/**
 * 只想往已有载荷里"补一个字段"时用这个（`...await nodeDefaultsParams()`），
 * 不必先展开再合并。
 */
export async function nodeDefaultsParams(): Promise<{ node_defaults: WireNodeDefaults }> {
  return { node_defaults: toWireNodeDefaults(await loadNodeDefaults()) }
}
