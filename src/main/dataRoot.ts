import { app } from 'electron'
import { mkdirSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

/**
 * dev 模式的数据目录回退。
 *
 * 背景（2026-10-08 实测）：这台机器上 `electron.exe` 被限制为**不能往 C: 用户区域写**
 * —— `%APPDATA%\blanks`、同父目录换个名字、`%APPDATA%` 根、`%LOCALAPPDATA%\blanks`、
 * `%TEMP%`、`C:\Users\<user>` 全部 `EPERM`（新建目录/写 tmp/rename 都拒），
 * 而 `node.exe` 对同样这些路径全部可写；`F:\<仓库>` 在 Electron 进程内可写。
 * 因此 `electron-store` 在模块加载期写 `app-config.json` 必挂，App 起不来，
 * 终端里只有一个截断的 "A JavaScript error occurred in the main process" 弹窗。
 *
 * 本模块在 `electron-store` 构造**之前**（`src/main/appIdentity.ts` 里）探测默认
 * userData 是否真的能完成一次「写 tmp + rename」——不能就整体挪到候选目录，
 * 并让 `getAppLocalDataPath()` 跟着挪（见 `src/main/utils/appPaths.ts`）。
 *
 * 边界：
 *   - 只在 dev 生效（`app.isPackaged` 为真直接跳过；打包版路径语义不变）。打包版在这台
 *     机器上会遇到同一堵墙，但那属于机器侧/产品决策，不在本模块的职责内。
 *   - 默认目录可写时**什么都不做**：不建目录、不改路径，行为与加这个模块之前完全一致。
 *   - 显式指定 `BLANKS_DEV_DATA_DIR` 时不静默降级：写不进去就报错退出（尊重显式意图）。
 */

export interface ProbeResult {
  ok: boolean
  code?: string
  message?: string
}

export interface ProbeAttempt extends ProbeResult {
  /** 给人看的候选名（如"默认 userData"/"工作区回退"）。 */
  label: string
  dir: string
}

export type WriteProbe = (dir: string) => ProbeResult

export interface DataRootPlan {
  /** 新的 userData（放 app-config.json 与渲染层 localStorage）。 */
  userData: string
  /** 新的本地数据目录（cache/output/tasks/logs/updates 的父目录）。 */
  localData: string
  source: 'explicit' | 'workspace' | 'temp'
  attempts: ProbeAttempt[]
}

/**
 * 一次「写 tmp 再 rename」——`electron-store`（`write-file-atomic`）的写法。
 * 只测写权限相关的能力，刻意**不**用真实文件名，避免污染或覆盖已有配置。
 */
export function probeWritableForAtomicWrite(dir: string): ProbeResult {
  const suffix = `${process.pid}-${Math.random().toString(36).slice(2, 10)}`
  const tmpFile = join(dir, `.blanks-probe-${suffix}.tmp`)
  const finalFile = join(dir, `.blanks-probe-${suffix}`)
  try {
    mkdirSync(dir, { recursive: true })
    writeFileSync(tmpFile, '{"ok":true}')
    renameSync(tmpFile, finalFile)
    rmSync(finalFile, { force: true })
    return { ok: true }
  } catch (err) {
    // 清理放在这里而不是 finally：成功路径刚刚删过，失败路径尽力而为即可，
    // 清理本身的失败绝不能掩盖真正的失败原因。
    try { rmSync(tmpFile, { force: true }) } catch { /* 忽略 */ }
    try { rmSync(finalFile, { force: true }) } catch { /* 忽略 */ }
    const e = err as NodeJS.ErrnoException
    return { ok: false, code: e?.code, message: e?.message }
  }
}

export interface ResolveDataRootContext {
  defaultUserData: string
  /** 仓库/应用根目录；dev 回退目录建在它下面（`<appPath>/.dev-data`）。 */
  appPath: string
  /** 系统临时目录；通用兜底（本机实测同样会被拒，但有总比没有好）。 */
  tempDir?: string
  /** `BLANKS_DEV_DATA_DIR` 的值（去空白后非空才算显式指定）。 */
  explicitDir?: string
  probe?: WriteProbe
}

export type DataRootResolution =
  | { kind: 'default'; attempts: ProbeAttempt[] }
  | { kind: 'override'; plan: DataRootPlan }
  /** 显式指定了目录但写不进去——报错退出，不回退。 */
  | { kind: 'explicit-failed'; plan: DataRootPlan }
  /** 所有候选都写不进去：这个进程在当前环境下无法运行 Electron。 */
  | { kind: 'all-failed'; plan: DataRootPlan }

/**
 * 纯函数（`probe` 可注入），便于单测在**不落盘**的前提下覆盖全部分支。
 *
 * 候选顺序：显式指定 → 默认 userData → 工作区 `<appPath>/.dev-data` → `<tmpdir>/blanks-dev-data`。
 * 工作区排第一顺位回退，因为它正是本机实测唯一可写的位置；`%LOCALAPPDATA%` 不再单列，
 * Windows 上它被 `%TEMP%`（= `%LOCALAPPDATA%\Temp`）覆盖。
 */
export function resolveDataRoot(ctx: ResolveDataRootContext): DataRootResolution {
  const probe = ctx.probe ?? probeWritableForAtomicWrite
  const attempts: ProbeAttempt[] = []
  const tempDir = ctx.tempDir ?? tmpdir()

  const explicitDir = (ctx.explicitDir || '').trim()
  if (explicitDir) {
    // 探测的必须是**真正要用的那个目录**（`<root>/userData`），而不是它的父目录 ——
    // 否则"父目录可写但不能建子目录"的机器会探测通过、然后照样挂掉。
    const explicitUserData = join(explicitDir, 'userData')
    const result = probe(explicitUserData)
    attempts.push({ label: 'BLANKS_DEV_DATA_DIR', dir: explicitUserData, ...result })
    const plan = buildPlan(explicitDir, 'explicit', attempts)
    return result.ok
      ? { kind: 'override', plan }
      : { kind: 'explicit-failed', plan }
  }

  const defaultResult = probe(ctx.defaultUserData)
  attempts.push({ label: '默认 userData', dir: ctx.defaultUserData, ...defaultResult })
  if (defaultResult.ok) {
    return { kind: 'default', attempts }
  }

  const fallbacks: Array<{ label: string; root: string; source: DataRootPlan['source'] }> = [
    { label: '工作区回退', root: join(ctx.appPath, '.dev-data'), source: 'workspace' },
    { label: '系统临时目录回退', root: join(tempDir, 'blanks-dev-data'), source: 'temp' },
  ]
  for (const candidate of fallbacks) {
    const candidateUserData = join(candidate.root, 'userData')
    const result = probe(candidateUserData)
    attempts.push({ label: candidate.label, dir: candidateUserData, ...result })
    if (result.ok) {
      return { kind: 'override', plan: buildPlan(candidate.root, candidate.source, attempts) }
    }
  }

  return { kind: 'all-failed', plan: buildPlan(fallbacks[0].root, fallbacks[0].source, attempts) }
}

function buildPlan(root: string, source: DataRootPlan['source'], attempts: ProbeAttempt[]): DataRootPlan {
  return {
    userData: join(root, 'userData'),
    localData: join(root, 'local'),
    source,
    attempts: [...attempts]
  }
}

/** 候选探测报告：失败分支打印给开发者看的那份东西。 */
export function formatDataRootReport(plan: DataRootPlan): string {
  const lines = ['[blanks] 数据目录探测结果（每项都做了一次「写 tmp + rename」）：']
  for (const attempt of plan.attempts) {
    lines.push(
      `[blanks]   ${attempt.ok ? 'OK  ' : 'FAIL'} ${attempt.label} :: ${attempt.dir}` +
      (attempt.ok ? '' : ` :: ${attempt.code || '未知错误'} :: ${attempt.message || ''}`)
    )
  }
  return lines.join('\n')
}

let activePlan: DataRootPlan | null = null
let guardHandler: ((err: unknown) => void) | null = null

/** 非 null 表示本次运行的数据目录被整体挪走了（`appPaths.getAppLocalDataPath()` 用它）。 */
export function getLocalDataOverride(): string | null {
  return activePlan ? activePlan.localData : null
}

export function getActiveDataRoot(): DataRootPlan | null {
  return activePlan
}

/** dev 门：只在 `npm run dev`（vite 注入 `VITE_DEV_SERVER_URL`）或显式指定目录时启用。 */
function devGateOpen(): boolean {
  return Boolean(process.env.VITE_DEV_SERVER_URL) || Boolean((process.env.BLANKS_DEV_DATA_DIR || '').trim())
}

/**
 * dev 启动期的未捕获异常改成「打印完整堆栈 + 退出」，而不是 Electron 那个截断的模态框。
 * 只在启动期生效：`main.ts` 在 `app.whenReady()` 里调 `releaseDevStartupGuard()` 交还给
 * Electron 默认行为，运行期的偶发异常不会因此变成"悄悄退出"。
 */
function installDevStartupGuard(): void {
  if (guardHandler) return
  guardHandler = (err: unknown) => {
    console.error('[blanks] dev 启动期主进程未捕获异常（完整堆栈见下）：')
    if (err instanceof Error) {
      console.error(err.stack || err.message)
    } else {
      console.error(String(err))
    }
    console.error('[blanks] 若是数据目录写不进去，见 docs/04-开发指南.md「Electron 起不来时怎么判断」。')
    process.exit(2)
  }
  process.on('uncaughtException', guardHandler)
}

export function releaseDevStartupGuard(): void {
  if (!guardHandler) return
  process.off('uncaughtException', guardHandler)
  guardHandler = null
}

/**
 * `src/main/appIdentity.ts` 在 `app.setName(APP_NAME)` 之后调用本函数——必须早于
 * `electron-store` 构造（`src/main/stores/appStore.ts` 顶层 `new Store()`）。
 */
export function installDevDataRoot(): DataRootResolution {
  if (app.isPackaged) {
    return { kind: 'default', attempts: [] }
  }
  if (!devGateOpen()) {
    return { kind: 'default', attempts: [] }
  }

  installDevStartupGuard()

  const resolution = resolveDataRoot({
    defaultUserData: app.getPath('userData'),
    appPath: app.getAppPath(),
    explicitDir: process.env.BLANKS_DEV_DATA_DIR
  })

  if (resolution.kind === 'default') {
    return resolution
  }

  const { plan } = resolution
  if (resolution.kind === 'explicit-failed' || resolution.kind === 'all-failed') {
    console.error(formatDataRootReport(plan))
    if (resolution.kind === 'explicit-failed') {
      console.error(`[blanks] BLANKS_DEV_DATA_DIR 指向的 ${plan.userData} 不可写；显式指定的目录不会静默回退，请换一个位置。`)
    } else {
      console.error('[blanks] 所有候选数据目录都写不进去 —— 当前环境不允许 Electron 写文件，App 无法启动。')
      console.error('[blanks] 这不是仓库代码的问题：请让安全产品放行 node_modules\\electron\\dist\\electron.exe，或换机器。')
    }
    process.exit(2)
  }

  activePlan = plan
  mkdirSync(plan.userData, { recursive: true })
  app.setPath('userData', plan.userData)
  try {
    // Electron 28+ 才有 sessionData；旧版没有该键时保持"跟随 userData"的默认行为。
    app.setPath('sessionData', plan.userData)
  } catch { /* 旧版 Electron：忽略 */ }

  const rejected = plan.attempts.filter((attempt) => !attempt.ok)
  const firstRejected = rejected[0]
  console.warn(
    `[blanks] 默认数据目录写不进去（${firstRejected?.dir || '未知'} :: ${firstRejected?.code || '未知错误'}），` +
    `已改用到：${plan.userData}`
  )
  console.warn('[blanks] 原因通常是安全软件/系统策略拦了 electron.exe 往 C: 用户区域写（详见 docs/04-开发指南.md）。')
  console.warn(`[blanks] 想换位置：设 BLANKS_DEV_DATA_DIR=<目录>（数据落在 <目录>\\userData 与 <目录>\\local）。`)

  return resolution
}
