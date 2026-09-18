/**
 * python/paths — runtime path resolution.
 *
 * Two bugs pinned here, both of which made the settings page (and the spawn
 * path) disagree with reality:
 *
 *  1. `runtimeExecutable` is relative to `runtime/`, but the settings view
 *     model resolved it against the app base → `<app>/python/python.exe`, a
 *     path that cannot exist. The page displayed that phantom path (and, with
 *     the new existence marker, flagged it as missing).
 *  2. An ABSOLUTE override (the user picked a system interpreter with the file
 *     dialog) was joined onto the runtime dir → `<runtime>/D:\x\python.exe`,
 *     so `fs.access` always failed and the user's choice was silently ignored.
 *
 * electron / electron-log are mocked: only the pure resolution + the fs probe
 * are under test.
 */
import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest'
import path from 'node:path'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'

vi.mock('electron', () => ({ app: { isPackaged: false } }))
vi.mock('electron-log', () => ({
  default: { info: () => undefined, warn: () => undefined, error: () => undefined },
}))

import {
  resolvePathFromBase,
  resolveRuntimeExecutablePath,
  resolvePythonExecutable,
} from '@/main/python/paths'

let base = ''

beforeAll(() => {
  base = mkdtempSync(path.join(tmpdir(), 'bt-paths-'))
})

afterAll(() => {
  try { rmSync(base, { recursive: true, force: true }) } catch { /* windows lock */ }
})

function makeRuntimePython(rel = path.join('python', 'python.exe')): string {
  const target = path.join(base, 'runtime', rel)
  mkdirSync(path.dirname(target), { recursive: true })
  writeFileSync(target, 'stub')
  return target
}

describe('resolveRuntimeExecutablePath', () => {
  it('把 runtimeExecutable 解析到 runtime/ 下（与实际 spawn 的解释器一致）', () => {
    const out = resolveRuntimeExecutablePath(base, path.join('python', 'python.exe'))
    expect(out).toBe(path.join(base, 'runtime', 'python', 'python.exe'))
    // 绝不是「相对 app base」的那个假路径
    expect(out).not.toBe(path.join(base, 'python', 'python.exe'))
  })

  it('绝对路径原样返回（用户用文件选择器挑的系统解释器）', () => {
    const abs = path.join(base, 'sys-python', 'python.exe')
    expect(resolveRuntimeExecutablePath(base, abs)).toBe(abs)
    expect(resolveRuntimeExecutablePath(base, 'C:\\Python312\\python.exe'))
      .toBe('C:\\Python312\\python.exe')
  })

  it('空值返回空串（「未配置」与「解析成 baseDir」必须可区分）', () => {
    expect(resolveRuntimeExecutablePath(base, '')).toBe('')
  })

  it('去掉开头的 ./ 或 .\\', () => {
    expect(resolveRuntimeExecutablePath(base, '.\\python\\python.exe'))
      .toBe(path.join(base, 'runtime', 'python', 'python.exe'))
  })

  it('resolvePathFromBase 保持原语义（绝对路径不动）', () => {
    expect(resolvePathFromBase(base, 'C:\\x\\y')).toBe('C:\\x\\y')
    expect(resolvePathFromBase(base, '.\\backend')).toBe(path.join(base, 'backend'))
  })
})

describe('resolvePythonExecutable', () => {
  it('内置运行时存在时使用它', async () => {
    const expected = makeRuntimePython()
    const { pythonExecutable, absRuntimeDir } = await resolvePythonExecutable(
      { get: () => 'python\\python.exe' }, base,
    )
    expect(pythonExecutable).toBe(expected)
    expect(absRuntimeDir).toBe(path.join(base, 'runtime'))
  })

  it('配置的绝对覆盖存在时使用它（以前会被拼坏而静默忽略）', async () => {
    const abs = path.join(base, 'sys-python', 'python.exe')
    mkdirSync(path.dirname(abs), { recursive: true })
    writeFileSync(abs, 'stub')
    const { pythonExecutable } = await resolvePythonExecutable({ get: () => abs }, base)
    expect(pythonExecutable).toBe(abs)
  })

  it('配置无效时回退到内置默认路径', async () => {
    const expected = makeRuntimePython()
    const { pythonExecutable } = await resolvePythonExecutable(
      { get: () => path.join('python', 'missing.exe') }, base,
    )
    expect(pythonExecutable).toBe(expected)
  })

  it('两者都不存在时回退到系统 python（裸 `python`，由 PATH 解析）', async () => {
    const empty = mkdtempSync(path.join(tmpdir(), 'bt-paths-empty-'))
    try {
      const { pythonExecutable } = await resolvePythonExecutable(
        { get: () => path.join('python', 'python.exe') }, empty,
      )
      expect(pythonExecutable).toBe('python')
    } finally {
      rmSync(empty, { recursive: true, force: true })
    }
  })
})
