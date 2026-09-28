/**
 * 工具 ↔ 环境依赖的本地聚合（docs/08 §3-S6.1 / S6.2）。
 *
 * 后端只在一处给出依赖关系：`workflow.list_tools[].env_deps`（**仅描述符工具**
 * 有该字段，WP3 #14）。环境就绪状态来自 `env.list[]`。两边都是既有接口，
 * 渲染层本地 join 即可，不需要新后端方法。
 *
 * 关键约束（docs/08 §3-S6.1 / §5-7，缺口 #18）：`env_deps` 缺失与空数组在界面上
 * **都表现为"不显示依赖行"** —— 内置工具与插件工具目前没有该字段，不能画成
 * "无依赖"，也不能替它们猜依赖。
 *
 * 纯函数、无 Vue 依赖（见 tests/unit/tools/toolEnvDeps.test.ts）。
 */

/** 环境条目里本模块用到的字段（与 `EnvEntry` 结构兼容）。 */
export interface EnvLike {
  name: string
  display_name?: string
  is_valid: boolean
  binary_path?: string
  version?: string
}

/** 工具条目里本模块用到的字段（与 `ToolEntry` 结构兼容）。 */
export interface ToolLike {
  name: string
  env_deps?: string[]
}

/** 一条工具依赖的展示信息。 */
export interface ToolEnvDep {
  /** 环境键（`env.list[].name`），用于跳转/计数。 */
  name: string
  /** 环境的显示名（缺失时回退到 name）。 */
  label: string
  /** 该环境是否已就绪（`is_valid`）。 */
  ready: boolean
}

/**
 * 某个工具需要点名的环境依赖。
 *
 * 只返回**确实声明过**的依赖：`env_deps` 缺失或为空 → 空数组（界面据此不显示
 * 依赖行）。声明了但环境列表里查不到的环境仍然返回（`ready: false`），因为那
 * 正是"缺依赖"的真实情况。
 */
export function toolEnvDeps(tool: ToolLike | null | undefined, envs: readonly EnvLike[] | null | undefined): ToolEnvDep[] {
  const deps = Array.isArray(tool?.env_deps) ? tool!.env_deps! : []
  if (deps.length === 0) return []

  const index = new Map<string, EnvLike>()
  for (const env of envs ?? []) {
    if (env?.name) index.set(env.name, env)
  }

  const seen = new Set<string>()
  const result: ToolEnvDep[] = []
  for (const raw of deps) {
    const name = String(raw ?? '').trim()
    if (!name || seen.has(name)) continue
    seen.add(name)
    const env = index.get(name)
    result.push({
      name,
      label: env?.display_name || env?.name || name,
      ready: env?.is_valid === true,
    })
  }
  return result
}

/** 环境名 → 依赖它的工具数（S6.2 的「被 N 个工具依赖」）。 */
export function envDependents(tools: readonly ToolLike[] | null | undefined): Map<string, number> {
  const counts = new Map<string, number>()
  for (const tool of tools ?? []) {
    const deps = new Set((Array.isArray(tool?.env_deps) ? tool!.env_deps! : []).map((d) => String(d ?? '').trim()))
    for (const dep of deps) {
      if (!dep) continue
      counts.set(dep, (counts.get(dep) ?? 0) + 1)
    }
  }
  return counts
}

/** 依赖某个环境、且该环境不可用的工具名（告警带的「查看受影响的工具」）。 */
export function toolsBlockedByEnv(
  tools: readonly ToolLike[] | null | undefined,
  env: EnvLike | null | undefined,
): string[] {
  if (!env || env.is_valid) return []
  return (tools ?? [])
    .filter((tool) => (Array.isArray(tool?.env_deps) ? tool!.env_deps! : []).includes(env.name))
    .map((tool) => tool.name)
}

/** 环境显示名（S6.2 行首）。 */
export function envLabel(env: EnvLike | null | undefined): string {
  if (!env) return ''
  return env.display_name || env.name
}

/** 工具来源徽章语义（内置 / 已导入 / 插件）。 */
export type ToolSourceKey = 'builtin' | 'descriptor' | 'plugin' | 'unknown'

/** 由 `workflow.list_tools[].kind` 得出来源徽章语义。 */
export function toolSourceOf(kind: unknown): ToolSourceKey {
  if (kind === 'shipped-native') return 'builtin'
  if (kind === 'descriptor') return 'descriptor'
  if (kind === 'native') return 'plugin'
  return 'unknown'
}

/** 只有描述符工具可以删除（内置与插件工具由后端保护，删除会抛错）。 */
export function canDeleteTool(kind: unknown): boolean {
  return kind === 'descriptor'
}
