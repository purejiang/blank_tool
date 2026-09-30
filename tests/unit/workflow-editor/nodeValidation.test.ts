/**
 * 节点可编辑性校验 + 生效端口解析（nodeValidation.ts）。
 *
 * 这一份实现同时驱动两处：节点面板的字段级提示与编辑器顶栏的保存门禁，所以
 * 这里锁住的是"什么算不能跑"的口径——与后端 `validate_workflow` 检查 2 一致：
 * 参数整个缺失才算缺，表达式值算已填，boolean 永远可满足。
 */
import { describe, expect, it } from 'vitest'

import {
  boundValues,
  effectivePorts,
  isEmptyValue,
  issueForField,
  portBaseOf,
  validateNodeEditable,
} from '@/renderer/components/workflow/nodeValidation'
import type { WorkflowToolInfo } from '@/renderer/components/workflow/toolMeta'

function port(name: string, base: string, overrides: Record<string, unknown> = {}) {
  return { name, type: { base, subtype: null }, required: true, description: '', options: [], multi: false, ...overrides }
}

const APKTOOL: WorkflowToolInfo = {
  name: 'apktool',
  is_valid: true,
  version: '',
  tool_path: '',
  ports: { inputs: [port('ignored', 'text')], outputs: [] },
  operations: [
    {
      name: 'decode',
      inputs: [
        port('apk_path', 'file'),
        port('output_dir', 'directory', { required: false }),
        port('force', 'boolean', { required: false }),
      ],
      outputs: [port('out_dir', 'directory')],
    },
  ],
} as unknown as WorkflowToolInfo

const SHELL: WorkflowToolInfo = {
  name: 'exec.shell',
  is_valid: true,
  version: '',
  tool_path: '',
  ports: {
    inputs: [
      port('command', 'text'),
      port('cwd', 'directory', { required: false }),
      port('timeout', 'number', { required: false }),
    ],
    outputs: [port('stdout', 'text')],
  },
} as unknown as WorkflowToolInfo

const SELECTOR: WorkflowToolInfo = {
  name: 'synth',
  is_valid: true,
  version: '',
  tool_path: '',
  ports: { inputs: [port('mode', 'text', { options: ['a', 'b'] })], outputs: [] },
} as unknown as WorkflowToolInfo

describe('effectivePorts', () => {
  it('uses the selected operation ports in operation mode', () => {
    const ports = effectivePorts({ operation: 'decode' }, APKTOOL)
    expect(ports.operationMode).toBe(true)
    expect(ports.operation).toBe('decode')
    expect(ports.inputs.map((p) => p.name)).toEqual(['apk_path', 'output_dir', 'force'])
    expect(ports.outputs.map((p) => p.name)).toEqual(['out_dir'])
  })

  it('reports no operation and no inputs when none is selected', () => {
    const ports = effectivePorts({}, APKTOOL)
    expect(ports.operationMode).toBe(true)
    expect(ports.operation).toBeNull()
    expect(ports.inputs).toEqual([])
  })

  it('treats a stale operation name as "not selected"', () => {
    const ports = effectivePorts({ operation: 'gone' }, APKTOOL)
    expect(ports.operation).toBeNull()
    expect(ports.inputs).toEqual([])
  })

  it('falls back to the tool ports for legacy tools', () => {
    const ports = effectivePorts({ ports: SHELL.ports }, SHELL)
    expect(ports.operationMode).toBe(false)
    expect(ports.inputs.map((p) => p.name)).toEqual(['command', 'cwd', 'timeout'])
  })

  it('tolerates missing tool metadata', () => {
    const ports = effectivePorts({ ports: SHELL.ports }, null)
    expect(ports.operationMode).toBe(false)
    // Without list_tools the panel still edits the ports stored on the node.
    expect(ports.inputs).toEqual([])
  })
})

describe('boundValues', () => {
  it('reads inputs in operation mode and params otherwise', () => {
    expect(boundValues({ operation: 'decode', inputs: { a: 1 }, params: { b: 2 } }, true)).toEqual({ a: 1 })
    expect(boundValues({ params: { b: 2 } }, false)).toEqual({ b: 2 })
    expect(boundValues({}, false)).toEqual({})
    expect(boundValues(null, true)).toEqual({})
  })
})

describe('isEmptyValue', () => {
  it('matches the panel/backend notion of empty', () => {
    expect(isEmptyValue(undefined)).toBe(true)
    expect(isEmptyValue(null)).toBe(true)
    expect(isEmptyValue('')).toBe(true)
    expect(isEmptyValue([])).toBe(true)
    expect(isEmptyValue(false)).toBe(false)
    expect(isEmptyValue(0)).toBe(false)
    expect(isEmptyValue('x')).toBe(false)
  })
})

describe('portBaseOf', () => {
  it('normalizes bare strings and wire objects', () => {
    expect(portBaseOf('FILE')).toBe('file')
    expect(portBaseOf({ base: 'Directory' })).toBe('directory')
    expect(portBaseOf(undefined)).toBe('')
  })
})

describe('validateNodeEditable', () => {
  it('requires an operation before anything else', () => {
    const issues = validateNodeEditable({}, APKTOOL)
    expect(issues.map((i) => i.code)).toEqual(['noOperation'])
    expect(issues[0].field).toBe('operation')
    expect(issues[0].messageKey).toBe('workflow.editor.config.errors.noOperation')
  })

  it('reports missing required operation inputs', () => {
    const issues = validateNodeEditable({ operation: 'decode', inputs: { force: false } }, APKTOOL)
    expect(issues.map((i) => i.code)).toEqual(['missingRequired'])
    expect(issues[0].params).toEqual({ names: 'apk_path' })
  })

  it('accepts a boolean false and an expression value as filled', () => {
    expect(validateNodeEditable({ operation: 'decode', inputs: { apk_path: '$inputs.apk' } }, APKTOOL)).toEqual([])
  })

  it('requires select ports to be filled like any other required port', () => {
    const issues = validateNodeEditable({ ports: SELECTOR.ports, params: {} }, SELECTOR)
    expect(issues.map((i) => i.code)).toEqual(['missingRequired'])
    expect(issues[0].params).toEqual({ names: 'mode' })
    expect(validateNodeEditable({ ports: SELECTOR.ports, params: { mode: 'a' } }, SELECTOR)).toEqual([])
  })

  it('reports missing required legacy params (same rule as the backend)', () => {
    const issues = validateNodeEditable({ ports: SHELL.ports, params: {} }, SHELL)
    expect(issues.map((i) => i.code)).toEqual(['missingRequired'])
    expect(issueForField(issues, 'command')?.code).toBe('missingRequired')
  })

  it('is happy with a complete node', () => {
    expect(
      validateNodeEditable({ ports: SHELL.ports, params: { command: 'echo hi' } }, SHELL),
    ).toEqual([])
  })

  it('does not check legacy params when the tool declares no ports', () => {
    expect(validateNodeEditable({ params: {} }, APKTOOL)).toEqual([
      expect.objectContaining({ code: 'noOperation' }),
    ])
    expect(validateNodeEditable({ tool: 'unknown.tool', params: {} }, null)).toEqual([])
  })
})
