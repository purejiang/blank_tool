import { describe, it, expect } from 'vitest'
import {
  CATEGORY_ORDER,
  groupWorkflowTools,
  isBuiltinTool,
  type WorkflowToolInfo,
} from '@/renderer/components/workflow/toolMeta'

function makeTool(overrides: Partial<WorkflowToolInfo>): WorkflowToolInfo {
  return {
    name: 'tool.example',
    is_valid: true,
    version: '1.0.0',
    tool_path: '/tmp/tool',
    ...overrides,
  }
}

/**
 * Palette grouping contract (09-28 改版).
 *
 * The palette no longer splits into 内置 / 插件 — that put every builtin
 * primitive in one flat 10-row list. It now groups by DOMAIN (file / net /
 * exec / flow / tool), so each bucket is short and collapsible; plugin
 * provenance is a per-item mark instead of a bucket. Order is fixed by
 * CATEGORY_ORDER so the list never reshuffles between renders.
 */
describe('groupWorkflowTools (WorkflowNodePalette grouping)', () => {
  it('buckets dotted name prefixes into their domain', () => {
    const groups = groupWorkflowTools([
      makeTool({ name: 'file.read' }),
      makeTool({ name: 'dir.list' }),
      makeTool({ name: 'text.replace' }),
      makeTool({ name: 'archive.extract' }),
      makeTool({ name: 'net.download' }),
      makeTool({ name: 'exec.shell' }),
      makeTool({ name: 'flow.assert' }),
    ])
    expect(groups.map((g) => g.key)).toEqual(['file', 'net', 'exec', 'flow'])
    expect(groups[0].tools.map((t) => t.name)).toEqual([
      'archive.extract',
      'dir.list',
      'file.read',
      'text.replace',
    ])
    expect(groups[1].tools.map((t) => t.name)).toEqual(['net.download'])
    expect(groups[2].tools.map((t) => t.name)).toEqual(['exec.shell'])
    expect(groups[3].tools.map((t) => t.name)).toEqual(['flow.assert'])
  })

  it('puts unknown prefixes (plugins, third-party tools) into the tool group', () => {
    const groups = groupWorkflowTools([
      makeTool({ name: 'adb.install', kind: 'descriptor' }),
      makeTool({ name: 'bundletool', kind: 'native' }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].key).toBe('tool')
    expect(groups[0].tools.map((t) => t.name)).toEqual(['adb.install', 'bundletool'])
  })

  it('keeps a plugin next to the builtins of the same domain', () => {
    const groups = groupWorkflowTools([
      makeTool({ name: 'file.read', kind: 'shipped-native' }),
      makeTool({ name: 'file.pack', kind: 'descriptor' }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].key).toBe('file')
    expect(groups[0].tools.map((t) => t.name)).toEqual(['file.pack', 'file.read'])
  })

  it('emits groups in CATEGORY_ORDER regardless of input order', () => {
    const groups = groupWorkflowTools([
      makeTool({ name: 'flow.assert' }),
      makeTool({ name: 'other.thing' }),
      makeTool({ name: 'exec.shell' }),
      makeTool({ name: 'file.read' }),
      makeTool({ name: 'net.download' }),
    ])
    expect(groups.map((g) => g.key)).toEqual(CATEGORY_ORDER)
  })

  it('sorts tools by name within each group and drops empty groups', () => {
    const groups = groupWorkflowTools([
      makeTool({ name: 'z.shipped' }),
      makeTool({ name: 'a.shipped' }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].key).toBe('tool')
    expect(groups[0].tools.map((t) => t.name)).toEqual(['a.shipped', 'z.shipped'])
  })

  it('skips entries without a usable name', () => {
    const groups = groupWorkflowTools([
      makeTool({ name: '' }),
      null as unknown as WorkflowToolInfo,
      makeTool({ name: 'file.read' }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].tools.map((t) => t.name)).toEqual(['file.read'])
  })

  it('returns no groups for an empty tool list', () => {
    expect(groupWorkflowTools([])).toEqual([])
  })
})

describe('isBuiltinTool (plugin mark on palette rows)', () => {
  it('treats shipped-native as builtin', () => {
    expect(isBuiltinTool(makeTool({ kind: 'shipped-native' }))).toBe(true)
  })

  it('treats native and descriptor as plugins', () => {
    expect(isBuiltinTool(makeTool({ kind: 'native' }))).toBe(false)
    expect(isBuiltinTool(makeTool({ kind: 'descriptor' }))).toBe(false)
  })

  it('falls back to the legacy builtin boolean when kind is absent', () => {
    expect(isBuiltinTool(makeTool({ builtin: true }))).toBe(true)
    expect(isBuiltinTool(makeTool({ builtin: false }))).toBe(false)
    expect(isBuiltinTool(makeTool({}))).toBe(false)
  })

  it('lets kind win over the legacy flag', () => {
    expect(isBuiltinTool(makeTool({ kind: 'native', builtin: true }))).toBe(false)
    expect(isBuiltinTool(makeTool({ kind: 'shipped-native', builtin: false }))).toBe(true)
  })
})
