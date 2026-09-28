import { describe, expect, it } from 'vitest'

import {
  canDeleteTool,
  envDependents,
  envLabel,
  toolEnvDeps,
  toolSourceOf,
  toolsBlockedByEnv,
} from '@/renderer/components/tools/toolEnvDeps'

/**
 * 工具 ↔ 环境依赖聚合（docs/08 §3-S6.1/S6.2）。
 *
 * 这组测试钉住的核心约束：**没有 `env_deps` 的工具不显示依赖行**（缺口 #18 之前
 * 内置/插件工具都没有该字段，不能猜、不能画"无依赖"）。
 */

const ENVS = [
  { name: 'java', display_name: 'Java', is_valid: true },
  { name: 'python', display_name: 'Python', is_valid: false },
]

describe('toolEnvDeps', () => {
  it('resolves declared deps against env.list with readiness', () => {
    expect(toolEnvDeps({ name: 'a', env_deps: ['java', 'python'] }, ENVS)).toEqual([
      { name: 'java', label: 'Java', ready: true },
      { name: 'python', label: 'Python', ready: false },
    ])
  })

  it('shows nothing when the tool declares no deps (builtins / plugins)', () => {
    expect(toolEnvDeps({ name: 'file.read' }, ENVS)).toEqual([])
    expect(toolEnvDeps({ name: 'file.read', env_deps: [] }, ENVS)).toEqual([])
    expect(toolEnvDeps(null, ENVS)).toEqual([])
  })

  it('keeps an unknown env name as an unmet dependency instead of dropping it', () => {
    expect(toolEnvDeps({ name: 'a', env_deps: ['node'] }, ENVS)).toEqual([
      { name: 'node', label: 'node', ready: false },
    ])
  })

  it('dedupes and ignores empty names', () => {
    expect(toolEnvDeps({ name: 'a', env_deps: ['java', 'java', '', '  '] }, ENVS)).toEqual([
      { name: 'java', label: 'Java', ready: true },
    ])
  })

  it('falls back to the env name when env.list has no display_name', () => {
    expect(toolEnvDeps({ name: 'a', env_deps: ['java'] }, [{ name: 'java', is_valid: true }])).toEqual([
      { name: 'java', label: 'java', ready: true },
    ])
  })
})

describe('envDependents', () => {
  it('counts tools per env name, counting a tool once per env', () => {
    const counts = envDependents([
      { name: 'apktool', env_deps: ['java'] },
      { name: 'bundletool', env_deps: ['java', 'java'] },
      { name: 'exec.code', env_deps: undefined },
      { name: 'other', env_deps: ['python'] },
    ])
    expect(counts.get('java')).toBe(2)
    expect(counts.get('python')).toBe(1)
    expect(counts.has('node')).toBe(false)
  })

  it('returns an empty map for tools without deps', () => {
    expect(envDependents([{ name: 'file.read' }]).size).toBe(0)
    expect(envDependents(null).size).toBe(0)
  })
})

describe('toolsBlockedByEnv', () => {
  it('lists the tools depending on an UNMET env', () => {
    const tools = [
      { name: 'apktool', env_deps: ['java'] },
      { name: 'jadtool', env_deps: ['java'] },
      { name: 'pycode', env_deps: ['python'] },
    ]
    expect(toolsBlockedByEnv(tools, ENVS[1])).toEqual(['pycode'])
    expect(toolsBlockedByEnv(tools, ENVS[0])).toEqual([]) // java is valid
    expect(toolsBlockedByEnv(tools, undefined)).toEqual([])
  })
})

describe('labels and badges', () => {
  it('prefers display_name for env labels', () => {
    expect(envLabel(ENVS[1])).toBe('Python')
    expect(envLabel({ name: 'custom', is_valid: false })).toBe('custom')
    expect(envLabel(null)).toBe('')
  })

  it('maps tool kind to its source badge', () => {
    expect(toolSourceOf('shipped-native')).toBe('builtin')
    expect(toolSourceOf('descriptor')).toBe('descriptor')
    expect(toolSourceOf('native')).toBe('plugin')
    expect(toolSourceOf('weird')).toBe('unknown')
  })

  it('only descriptor tools may be deleted', () => {
    expect(canDeleteTool('descriptor')).toBe(true)
    expect(canDeleteTool('shipped-native')).toBe(false)
    expect(canDeleteTool('native')).toBe(false)
  })
})
