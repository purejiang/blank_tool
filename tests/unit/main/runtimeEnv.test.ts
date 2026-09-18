import { describe, it, expect } from 'vitest'

import {
  buildBackendEnv,
  RUNTIME_OVERRIDE_KEYS,
  NODE_PATH_DEFAULT,
} from '@/main/python/backendEnv'

const BASE = {
  BT_RUNTIME_DIR: 'D:/app/runtime',
  BT_CACHE_DIR: 'D:/app/cache',
  BT_TASKS_DIR: 'D:/app/tasks',
  BT_AUTO_TASKS_DIR: 'D:/app/auto_tasks',
  BT_PLUGINS_DIR: 'D:/app/plugins',
  BT_OUTPUT_DIR: 'D:/app/output',
  BT_LOG_DIR: 'D:/app/logs',
  BT_LOG_LEVEL: 'info',
} as Record<string, string | undefined>

describe('buildBackendEnv', () => {
  it('keeps every pre-existing variable untouched when nothing is overridden', () => {
    const env = buildBackendEnv({ ...BASE })
    expect(env).toEqual({ ...BASE })
  })

  it('injects BT_JAVA_BIN only when a java path is configured', () => {
    const env = buildBackendEnv({ ...BASE }, { javaBin: 'C:/jdk/bin/java.exe' })
    expect(env.BT_JAVA_BIN).toBe('C:/jdk/bin/java.exe')
    expect(env.BT_NODE_BIN).toBeUndefined()
  })

  it('injects BT_NODE_BIN only when a node path is configured', () => {
    const env = buildBackendEnv({ ...BASE }, { nodeBin: 'C:/node/node.exe' })
    expect(env.BT_NODE_BIN).toBe('C:/node/node.exe')
    expect(env.BT_JAVA_BIN).toBeUndefined()
  })

  it('does not emit the keys for empty / whitespace overrides', () => {
    for (const javaBin of ['', '   ', undefined]) {
      const env = buildBackendEnv({ ...BASE }, { javaBin, nodeBin: '  ' })
      expect(env.BT_JAVA_BIN, `javaBin=${JSON.stringify(javaBin)}`).toBeUndefined()
      expect(env.BT_NODE_BIN).toBeUndefined()
      expect(Object.keys(env).sort()).toEqual(Object.keys(BASE).sort())
    }
  })

  it('trims whitespace around a configured path', () => {
    const env = buildBackendEnv({ ...BASE }, { javaBin: '  D:/jre/bin/java.exe  ' })
    expect(env.BT_JAVA_BIN).toBe('D:/jre/bin/java.exe')
  })

  it('never injects BT_PYTHON_BIN (the spawned interpreter already is the python runtime)', () => {
    const env = buildBackendEnv({ ...BASE }, { javaBin: 'x', nodeBin: 'y' })
    expect(env.BT_PYTHON_BIN).toBeUndefined()
  })

  it('does not mutate the caller base object', () => {
    const base = { ...BASE }
    buildBackendEnv(base, { javaBin: 'C:/java.exe' })
    expect(base.BT_JAVA_BIN).toBeUndefined()
  })

  it('maps runtime override keys to the app config store keys', () => {
    // 没有 python 项：spawn 的 Python 解释器是 `runtimeExecutable`（相对 runtime/），
    // 不是 `pythonPath` 覆盖键（那个键已删除，改它没有任何效果）。
    expect(RUNTIME_OVERRIDE_KEYS).toEqual({
      java: 'javaPath',
      node: 'nodePath',
    })
    // Empty default = "follow the Node this app runs on"
    expect(NODE_PATH_DEFAULT).toBe('')
  })
})
