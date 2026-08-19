import { describe, it, expect } from 'vitest'
import {
  groupWorkflowTools,
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

describe('groupWorkflowTools (WorkflowNodePalette grouping)', () => {
  it('groups shipped-native into Built-in', () => {
    const groups = groupWorkflowTools([
      makeTool({ name: 'flow.assert', kind: 'shipped-native', builtin: true }),
      makeTool({ name: 'my.plugin', kind: 'native', builtin: false }),
    ])
    expect(groups).toHaveLength(2)
    expect(groups[0].label).toBe('Built-in')
    expect(groups[0].tools.map((t) => t.name)).toEqual(['flow.assert'])
    expect(groups[1].label).toBe('Plugins')
    expect(groups[1].tools.map((t) => t.name)).toEqual(['my.plugin'])
  })

  it('groups native into Plugins (even when legacy builtin flag is true)', () => {
    const groups = groupWorkflowTools([
      makeTool({ name: 'native.a', kind: 'native' }),
      makeTool({ name: 'native.b', kind: 'native', builtin: true }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('Plugins')
    expect(groups[0].tools.map((t) => t.name)).toEqual(['native.a', 'native.b'])
  })

  it('groups descriptor into Plugins', () => {
    const groups = groupWorkflowTools([
      makeTool({ name: 'adb.install', kind: 'descriptor', builtin: false }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('Plugins')
    expect(groups[0].tools.map((t) => t.name)).toEqual(['adb.install'])
  })

  it('falls back to legacy builtin boolean when kind is absent', () => {
    const groups = groupWorkflowTools([
      makeTool({ name: 'file.read', builtin: true }),
      makeTool({ name: 'legacy.tool', builtin: false }),
      makeTool({ name: 'legacy.other' }),
    ])
    expect(groups).toHaveLength(2)
    expect(groups[0].label).toBe('Built-in')
    expect(groups[0].tools.map((t) => t.name)).toEqual(['file.read'])
    expect(groups[1].label).toBe('Plugins')
    expect(groups[1].tools.map((t) => t.name)).toEqual(['legacy.other', 'legacy.tool'])
  })

  it('sorts tools by name within each group and drops empty groups', () => {
    const groups = groupWorkflowTools([
      makeTool({ name: 'z.shipped', kind: 'shipped-native' }),
      makeTool({ name: 'a.shipped', kind: 'shipped-native' }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('Built-in')
    expect(groups[0].tools.map((t) => t.name)).toEqual(['a.shipped', 'z.shipped'])
  })

  it('returns no groups for an empty tool list', () => {
    expect(groupWorkflowTools([])).toEqual([])
  })
})
