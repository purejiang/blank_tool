import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import path from 'node:path'

/**
 * dev 数据目录回退（`src/main/dataRoot.ts`）的单元测试。
 *
 * 这里守的是三条容易漂的约定：
 *   1. 默认目录可写时**什么都不做**（不 setPath、不建目录）——这是"加了这个模块但正常机器上
 *      行为零变化"的保证；
 *   2. 回退顺序（工作区 → 系统临时目录）与落点路径（`<root>/userData`、`<root>/local`）；
 *   3. 显式 `BLANKS_DEV_DATA_DIR` 写不进去时**不回退**，而是明确失败。
 *
 * 探针在单测里一律注入假实现（不落盘）；只有专门验证探针本身的用例才碰真实文件系统，
 * 而且落在仓库内的 `.tmp/`（gitignored，fileChannels.test.ts 同款做法）。
 */

const appStub = {
  isPackaged: false,
  getPath: vi.fn(),
  getAppPath: vi.fn(),
  setPath: vi.fn(),
}

vi.mock('electron', () => ({ app: appStub }))

const scratch = path.join(process.cwd(), '.tmp', 'dataroot-test')

function makeDir(...segments: string[]): string {
  const dir = path.join(scratch, ...segments)
  mkdirSync(dir, { recursive: true })
  return dir
}

/** 假探针：只有列在 `writable` 里的目录可写，其余按 EPERM 失败。 */
function probeStub(writable: string[]) {
  return vi.fn((dir: string) => (writable.includes(dir) ? { ok: true } : { ok: false, code: 'EPERM', message: `denied ${dir}` }))
}

beforeEach(() => {
  rmSync(scratch, { recursive: true, force: true })
  mkdirSync(scratch, { recursive: true })
  delete process.env.VITE_DEV_SERVER_URL
  delete process.env.BLANKS_DEV_DATA_DIR
  appStub.isPackaged = false
  appStub.getPath.mockReset()
  appStub.getAppPath.mockReset()
  appStub.setPath.mockReset()
  vi.resetModules()
})

afterEach(() => {
  rmSync(scratch, { recursive: true, force: true })
  delete process.env.VITE_DEV_SERVER_URL
  delete process.env.BLANKS_DEV_DATA_DIR
  vi.resetModules()
})

describe('resolveDataRoot 候选链', () => {
  it('默认目录可写 → default，且只探测了默认目录', async () => {
    const { resolveDataRoot } = await import('@/main/dataRoot')
    const def = path.join(scratch, 'appdata')
    const result = resolveDataRoot({
      defaultUserData: def,
      appPath: path.join(scratch, 'repo'),
      tempDir: path.join(scratch, 'temp'),
      probe: probeStub([def]),
    })

    expect(result.kind).toBe('default')
    expect(result.attempts).toHaveLength(1)
    expect(result.attempts[0]).toMatchObject({ ok: true, dir: def })
  })

  it('默认目录不可写、工作区可写 → 回退到 <appPath>/.dev-data', async () => {
    const { resolveDataRoot } = await import('@/main/dataRoot')
    const def = path.join(scratch, 'appdata')
    const appPath = path.join(scratch, 'repo')
    const workspaceUserData = path.join(appPath, '.dev-data', 'userData')
    const result = resolveDataRoot({
      defaultUserData: def,
      appPath,
      tempDir: path.join(scratch, 'temp'),
      probe: probeStub([workspaceUserData]),
    })

    expect(result.kind).toBe('override')
    if (result.kind !== 'override') return
    expect(result.plan.source).toBe('workspace')
    expect(result.plan.userData).toBe(workspaceUserData)
    expect(result.plan.localData).toBe(path.join(appPath, '.dev-data', 'local'))
    // 失败的那一项也要留在报告里（否则应用那行告警说不出"哪里被拒"）
    expect(result.plan.attempts[0]).toMatchObject({ ok: false, dir: def, code: 'EPERM' })
    expect(result.plan.attempts[1]).toMatchObject({ ok: true, dir: workspaceUserData })
  })

  it('默认与工作区都不可写、系统临时目录可写 → 回退到临时目录', async () => {
    const { resolveDataRoot } = await import('@/main/dataRoot')
    const def = path.join(scratch, 'appdata')
    const appPath = path.join(scratch, 'repo')
    const tempDir = path.join(scratch, 'temp')
    const tempUserData = path.join(tempDir, 'blanks-dev-data', 'userData')
    const result = resolveDataRoot({
      defaultUserData: def,
      appPath,
      tempDir,
      probe: probeStub([tempUserData]),
    })

    expect(result.kind).toBe('override')
    if (result.kind !== 'override') return
    expect(result.plan.source).toBe('temp')
    expect(result.plan.userData).toBe(tempUserData)
    expect(result.plan.localData).toBe(path.join(tempDir, 'blanks-dev-data', 'local'))
  })

  it('显式 BLANKS_DEV_DATA_DIR 可写 → 直接采用，不探测默认目录', async () => {
    const { resolveDataRoot } = await import('@/main/dataRoot')
    const explicit = path.join(scratch, 'explicit')
    const probe = probeStub([path.join(explicit, 'userData')])
    const result = resolveDataRoot({
      defaultUserData: path.join(scratch, 'appdata'),
      appPath: path.join(scratch, 'repo'),
      explicitDir: explicit,
      probe,
    })

    expect(result.kind).toBe('override')
    if (result.kind !== 'override') return
    expect(result.plan.source).toBe('explicit')
    expect(result.plan.userData).toBe(path.join(explicit, 'userData'))
    expect(probe).toHaveBeenCalledTimes(1)
  })

  it('显式 BLANKS_DEV_DATA_DIR 不可写 → explicit-failed，绝不静默回退', async () => {
    const { resolveDataRoot } = await import('@/main/dataRoot')
    const explicit = path.join(scratch, 'explicit-blocked')
    const result = resolveDataRoot({
      defaultUserData: path.join(scratch, 'appdata'),
      appPath: path.join(scratch, 'repo'),
      tempDir: path.join(scratch, 'temp'),
      explicitDir: explicit,
      probe: probeStub([]),
    })

    expect(result.kind).toBe('explicit-failed')
    if (result.kind !== 'explicit-failed') return
    expect(result.plan.attempts).toHaveLength(1)
    expect(result.plan.attempts[0].dir).toBe(path.join(explicit, 'userData'))
  })

  it('所有候选都不可写 → all-failed，报告里三个候选都在', async () => {
    const { resolveDataRoot } = await import('@/main/dataRoot')
    const result = resolveDataRoot({
      defaultUserData: path.join(scratch, 'appdata'),
      appPath: path.join(scratch, 'repo'),
      tempDir: path.join(scratch, 'temp'),
      probe: probeStub([]),
    })

    expect(result.kind).toBe('all-failed')
    expect(result.plan.attempts).toHaveLength(3)
    expect(result.plan.attempts.every((attempt) => !attempt.ok)).toBe(true)
  })

  it('formatDataRootReport 把每个候选、errno 都写出来', async () => {
    const { resolveDataRoot, formatDataRootReport } = await import('@/main/dataRoot')
    const def = path.join(scratch, 'appdata')
    const result = resolveDataRoot({
      defaultUserData: def,
      appPath: path.join(scratch, 'repo'),
      tempDir: path.join(scratch, 'temp'),
      probe: probeStub([]),
    })
    const report = formatDataRootReport(result.plan)

    expect(report).toContain('EPERM')
    expect(report).toContain(def)
    for (const attempt of result.plan.attempts) {
      expect(report).toContain(attempt.dir)
    }
  })
})

describe('probeWritableForAtomicWrite（真实文件系统）', () => {
  it('可写目录：成功且不留残留文件', async () => {
    const { probeWritableForAtomicWrite } = await import('@/main/dataRoot')
    const dir = makeDir('probe-ok')
    const result = probeWritableForAtomicWrite(dir)

    expect(result.ok).toBe(true)
    expect(readdirSync(dir)).toEqual([])
  })

  it('不可写目标（路径上是文件）：失败且不留残留文件', async () => {
    const { probeWritableForAtomicWrite } = await import('@/main/dataRoot')
    const dir = makeDir('probe-fail')
    const blocker = path.join(dir, 'blocker')
    writeFileSync(blocker, 'x')

    const result = probeWritableForAtomicWrite(blocker)

    expect(result.ok).toBe(false)
    expect(result.code).toBeTruthy()
    // 探测不该往父目录里丢东西
    expect(readdirSync(dir)).toEqual(['blocker'])
  })
})

describe('installDevDataRoot 的门与落点', () => {
  it('没有 dev 标记时完全不探测（默认目录不可写也不回退）', async () => {
    const { installDevDataRoot, getLocalDataOverride } = await import('@/main/dataRoot')
    const blocker = path.join(scratch, 'blocker')
    writeFileSync(blocker, 'x')
    appStub.getPath.mockReturnValue(blocker)
    appStub.getAppPath.mockReturnValue(makeDir('repo'))

    const resolution = installDevDataRoot()

    expect(resolution.kind).toBe('default')
    expect(appStub.setPath).not.toHaveBeenCalled()
    expect(getLocalDataOverride()).toBeNull()
  })

  it('打包版（isPackaged）直接跳过', async () => {
    process.env.VITE_DEV_SERVER_URL = 'http://localhost:3000'
    appStub.isPackaged = true
    appStub.getPath.mockReturnValue(path.join(scratch, 'appdata'))
    appStub.getAppPath.mockReturnValue(makeDir('repo'))

    const { installDevDataRoot } = await import('@/main/dataRoot')
    const resolution = installDevDataRoot()

    expect(resolution.kind).toBe('default')
    expect(appStub.setPath).not.toHaveBeenCalled()
  })

  it('dev 门开 + 默认可写 → 零变化：不 setPath、不建 .dev-data', async () => {
    process.env.VITE_DEV_SERVER_URL = 'http://localhost:3000'
    const defaultUserData = makeDir('appdata-writable')
    const appPath = makeDir('repo')
    appStub.getPath.mockReturnValue(defaultUserData)
    appStub.getAppPath.mockReturnValue(appPath)

    const { installDevDataRoot, getLocalDataOverride, releaseDevStartupGuard } = await import('@/main/dataRoot')
    const resolution = installDevDataRoot()

    expect(resolution.kind).toBe('default')
    expect(appStub.setPath).not.toHaveBeenCalled()
    expect(getLocalDataOverride()).toBeNull()
    expect(existsSync(path.join(appPath, '.dev-data'))).toBe(false)
    releaseDevStartupGuard()
  })

  it('dev 门开 + 默认不可写 → 把 userData 挪到工作区，并暴露本地数据目录覆盖值', async () => {
    process.env.VITE_DEV_SERVER_URL = 'http://localhost:3000'
    const blocker = path.join(scratch, 'blocker')
    writeFileSync(blocker, 'x')
    const appPath = makeDir('repo')
    appStub.getPath.mockReturnValue(blocker)
    appStub.getAppPath.mockReturnValue(appPath)

    const { installDevDataRoot, getLocalDataOverride, releaseDevStartupGuard } = await import('@/main/dataRoot')
    const resolution = installDevDataRoot()

    const expectedUserData = path.join(appPath, '.dev-data', 'userData')
    expect(resolution.kind).toBe('override')
    expect(appStub.setPath).toHaveBeenCalledWith('userData', expectedUserData)
    expect(getLocalDataOverride()).toBe(path.join(appPath, '.dev-data', 'local'))
    // 目录必须真的建出来，否则 Chromium / electron-store 仍会失败
    expect(existsSync(expectedUserData)).toBe(true)
    // 测试里没有 main.ts 的 whenReady，手动摘掉启动期兜底，别影响同进程的其他用例
    releaseDevStartupGuard()
  })
})
