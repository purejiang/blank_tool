/**
 * 节点行为默认值（nodeDefaults.ts）——设置页与所有运行入口共用的一份读写。
 *
 * 关键不变式：任何异常 / 缺字段 / 非法值都回落到内置默认（fail / 0），
 * 因为"一份 UI 配置读不到"绝不该让工作流跑不起来。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getAppConfig = vi.fn()

vi.mock('@services/ServiceManager', () => ({
  default: {
    register: vi.fn(),
    getService: vi.fn(async (name: string) => {
      if (name !== 'config') return {}
      return { getAppConfig }
    }),
    getServiceSync: vi.fn(),
  },
}))

import {
  loadNodeDefaults,
  NODE_BEHAVIOR_FALLBACK,
  nodeDefaultsParams,
  normalizeNodeDefaults,
  toWireNodeDefaults,
  withNodeDefaults,
} from '@/renderer/components/workflow/nodeDefaults'

describe('normalizeNodeDefaults', () => {
  it('keeps valid camelCase values', () => {
    expect(normalizeNodeDefaults({ onFailure: 'skip', retry: 3 })).toEqual({
      onFailure: 'skip',
      retry: 3,
    })
  })

  it('accepts snake_case and string numbers (hand-edited config files)', () => {
    expect(normalizeNodeDefaults({ on_failure: 'skip', retry: '2' })).toEqual({
      onFailure: 'skip',
      retry: 2,
    })
  })

  it('falls back for malformed payloads', () => {
    for (const raw of [undefined, null, 'skip', 3, [], {}, { onFailure: 'explode' }, { retry: -1 }]) {
      expect(normalizeNodeDefaults(raw)).toEqual(NODE_BEHAVIOR_FALLBACK)
    }
  })

  it('clamps fractional and negative retries', () => {
    expect(normalizeNodeDefaults({ retry: 2.7 }).retry).toBe(2)
    expect(normalizeNodeDefaults({ retry: -5 }).retry).toBe(0)
    expect(normalizeNodeDefaults({ retry: Number.NaN }).retry).toBe(0)
  })
})

describe('toWireNodeDefaults', () => {
  it('maps to the backend parameter shape (snake_case)', () => {
    expect(toWireNodeDefaults({ onFailure: 'skip', retry: 4 })).toEqual({
      on_failure: 'skip',
      retry: 4,
    })
  })
})

describe('loadNodeDefaults', () => {
  beforeEach(() => {
    getAppConfig.mockReset()
  })

  it('reads the appConfig `nodes` group', async () => {
    getAppConfig.mockResolvedValue({ onFailure: 'skip', retry: 1 })
    await expect(loadNodeDefaults()).resolves.toEqual({ onFailure: 'skip', retry: 1 })
    expect(getAppConfig).toHaveBeenCalledWith('nodes')
  })

  it('falls back when the payload is missing or malformed', async () => {
    getAppConfig.mockResolvedValue(undefined)
    await expect(loadNodeDefaults()).resolves.toEqual(NODE_BEHAVIOR_FALLBACK)
  })

  it('falls back instead of throwing when the service fails', async () => {
    getAppConfig.mockRejectedValue(new Error('backend down'))
    await expect(loadNodeDefaults()).resolves.toEqual(NODE_BEHAVIOR_FALLBACK)
  })
})

describe('run-parameter helpers', () => {
  beforeEach(() => {
    getAppConfig.mockReset()
    getAppConfig.mockResolvedValue({ onFailure: 'skip', retry: 2 })
  })

  it('withNodeDefaults merges node_defaults into an existing payload', async () => {
    await expect(withNodeDefaults({ name: 'wf', inputs: { a: 1 } })).resolves.toEqual({
      name: 'wf',
      inputs: { a: 1 },
      node_defaults: { on_failure: 'skip', retry: 2 },
    })
  })

  it('nodeDefaultsParams returns just the field (spread-friendly)', async () => {
    await expect(nodeDefaultsParams()).resolves.toEqual({
      node_defaults: { on_failure: 'skip', retry: 2 },
    })
  })
})
