/**
 * T7 — Node config driven by operation typed inputs.
 *
 * Covers the NodeConfigPanel operation mode (descriptor tools that expose
 * operations via workflow.list_tools), the legacy free-form params fallback
 * (builtin tools / descriptors without operations), native plugin tools
 * (kind "native", todo 20: ports render like builtins, operations trigger
 * operation mode), and the serializer mapping between
 * node.data.{operation, inputs} and the engine wire params
 * `{operation, <input_name>: value}` (T4 contract), including the T5
 * round-trip shape of examples/workflows/android/decompile.json.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { h, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import type { Node } from '@vue-flow/core'
import {
  deserializeWorkflow,
  serializeWorkflow,
} from '@/renderer/components/workflow/serializer'
import decompileExample from '../../../examples/workflows/android/decompile.json'

// ---------------------------------------------------------------------------
// Mocks (hoisted): ServiceManager (path pickers) + unifiedApi (tool metadata)
// ---------------------------------------------------------------------------

vi.mock('@services/ServiceManager', () => ({
  default: {
    register: vi.fn(),
    getService: vi.fn().mockResolvedValue({
      selectFile: vi.fn(),
      selectDirectory: vi.fn(),
    }),
    getServiceSync: vi.fn(),
  },
}))

vi.mock('@/renderer/api/unifiedApi', () => ({
  default: { call: vi.fn() },
}))

import unifiedApi from '@/renderer/api/unifiedApi'
import NodeConfigPanel from '@/renderer/components/workflow/NodeConfigPanel.vue'

// ---------------------------------------------------------------------------
// Fixtures — mirror the additive `operations` field of workflow.list_tools
// ---------------------------------------------------------------------------

/** Port fixture builder (backend Port.to_dict always emits options/multi). */
function port(
  name: string,
  base: string,
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    name,
    type: { base, subtype: null },
    required: true,
    description: '',
    options: [],
    multi: false,
    ...overrides,
  }
}

const APKTOOL = {
  name: 'apktool',
  is_valid: true,
  version: '2.9.3',
  tool_path: '/runtime/apktool/apktool.jar',
  operations: [
    {
      name: 'decode',
      description: 'Decode an APK into resources and smali.',
      inputs: [
        port('apk_path', 'file', { type: { base: 'file', subtype: 'apk' } }),
        port('output_dir', 'directory', { required: false }),
        port('force', 'boolean', { required: false }),
      ],
      outputs: [port('output_dir', 'directory')],
    },
    {
      name: 'build',
      description: 'Rebuild a decoded tree into an APK.',
      inputs: [port('source_dir', 'directory'), port('output_apk', 'file')],
      outputs: [port('output_apk', 'file')],
    },
  ],
}

const SYNTHTOOL = {
  name: 'synthtool',
  is_valid: true,
  version: '',
  tool_path: '/runtime/synth/synth',
  operations: [
    {
      name: 'configure',
      description: 'Configure with select inputs.',
      inputs: [
        port('mode', 'text', { options: ['alpha', 'beta', 'gamma'] }),
        port('tags', 'text', { options: ['x', 'y'], multi: true, required: false }),
      ],
      outputs: [],
    },
  ],
}

/** Builtin tool — never carries operations (legacy free-form config). */
const FILEREAD = {
  name: 'file.read',
  is_valid: true,
  version: '',
  tool_path: '',
  builtin: true,
  ports: {
    inputs: [port('path', 'file')],
    outputs: [port('content', 'text')],
  },
}

/**
 * Native plugin tool (kind "native", legacy builtin flag false) with plain
 * ports and no operations — must render exactly like a builtin (todo 20).
 */
const NATIVEPLUGIN = {
  name: 'my.native',
  is_valid: true,
  version: '0.1.0',
  tool_path: '',
  kind: 'native',
  builtin: false,
  ports: {
    inputs: [port('input_text', 'text'), port('count', 'number', { required: false })],
    outputs: [port('result', 'text')],
  },
}

/** Native plugin tool that declares operations — must use operation mode. */
const NATIVEOP = {
  name: 'my.nativeop',
  is_valid: true,
  version: '0.1.0',
  tool_path: '',
  kind: 'native',
  builtin: false,
  ports: { inputs: [port('ignored', 'text')], outputs: [] },
  operations: [
    {
      name: 'transform',
      description: 'Transform a value.',
      inputs: [port('value', 'text')],
      outputs: [port('value', 'text')],
    },
  ],
}

const TOOL_LIST = { tools: [APKTOOL, SYNTHTOOL, FILEREAD, NATIVEPLUGIN, NATIVEOP] }

// ---------------------------------------------------------------------------
// Naive-ui stubs — plain render functions (no runtime template compilation).
// v-model:value is honored via `value` prop + `update:value` emits.
// NOTE: naive-ui registers its components under unprefixed names
// (NSelect.name === 'Select', etc.), so stub keys use those names.
// ---------------------------------------------------------------------------

const NAIVE_STUBS: Record<string, unknown> = {
  Form: {
    name: 'Form',
    setup(_props: unknown, { slots }: any) {
      return () => h('form', { class: 'n-form-stub' }, slots.default?.())
    },
  },
  FormItem: {
    name: 'FormItem',
    props: { label: String, required: Boolean },
    setup(props: any, { slots }: any) {
      return () =>
        h(
          'div',
          {
            class: 'form-item-stub',
            'data-label': props.label,
            'data-required': props.required ? 'true' : 'false',
          },
          [...(slots.default?.() ?? []), ...(slots.feedback?.() ?? [])],
        )
    },
  },
  Input: {
    name: 'Input',
    props: { value: null, type: String },
    emits: ['update:value'],
    setup(props: any, { emit }: any) {
      return () =>
        h(props.type === 'textarea' ? 'textarea' : 'input', {
          class: 'n-input-stub',
          value: props.value ?? '',
          onInput: (e: Event) => emit('update:value', (e.target as HTMLInputElement).value),
        })
    },
  },
  InputNumber: {
    name: 'InputNumber',
    props: { value: null },
    emits: ['update:value'],
    setup(props: any, { emit }: any) {
      return () =>
        h('input', {
          type: 'number',
          class: 'n-number-stub',
          value: props.value ?? '',
          onInput: (e: Event) => {
            const raw = (e.target as HTMLInputElement).value
            emit('update:value', raw === '' ? null : Number(raw))
          },
        })
    },
  },
  Switch: {
    name: 'Switch',
    props: { value: Boolean },
    emits: ['update:value'],
    setup(props: any, { emit }: any) {
      return () =>
        h('input', {
          type: 'checkbox',
          class: 'n-switch-stub',
          checked: !!props.value,
          onChange: (e: Event) => emit('update:value', (e.target as HTMLInputElement).checked),
        })
    },
  },
  Button: {
    name: 'Button',
    props: { disabled: Boolean },
    setup(props: any, { slots }: any) {
      return () =>
        h('button', { class: 'n-button-stub', disabled: props.disabled || undefined }, slots.default?.())
    },
  },
  Select: {
    name: 'Select',
    props: { value: null, options: Array, multiple: Boolean },
    emits: ['update:value'],
    setup(props: any, { emit }: any) {
      return () =>
        h(
          'select',
          {
            class: 'n-select-stub',
            multiple: props.multiple || undefined,
            onChange: (e: Event) => {
              const el = e.target as HTMLSelectElement
              if (props.multiple) {
                emit('update:value', Array.from(el.selectedOptions).map((o) => o.value))
              } else {
                emit('update:value', el.value === '' ? null : el.value)
              }
            },
          },
          (props.options ?? []).map((o: any) => h('option', { value: o.value }, o.label)),
        )
    },
  },
}

// i18n with empty messages: t() returns the key itself, so tests assert on
// stable i18n keys (same pattern as ioAuthoring's IO_ERRORS).
const i18n = createI18n({
  legacy: false,
  locale: 'en-US',
  messages: { 'en-US': {} },
  missingWarn: false,
  fallbackWarn: false,
})

function makeNode(data: Record<string, unknown>, id = 'node-1'): Node {
  return { id, type: 'tool', position: { x: 0, y: 0 }, data, selected: true } as unknown as Node
}

function mountPanel(node: Node | null) {
  return mount(NodeConfigPanel, {
    props: { node },
    global: { plugins: [i18n], stubs: NAIVE_STUBS },
  })
}

/** Flush the panel's workflow.list_tools fetch + reactivity. */
async function settled() {
  await flushPromises()
  await nextTick()
  await nextTick()
}

function labels(wrapper: ReturnType<typeof mountPanel>): string[] {
  return wrapper.findAll('.form-item-stub').map((fi) => fi.attributes('data-label') ?? '')
}

async function clickSave(wrapper: ReturnType<typeof mountPanel>) {
  // Browse buttons (path ports) are also n-buttons — pick the Save button.
  const buttons = wrapper.findAll('.n-button-stub')
  const save = buttons.find((b) => b.text().includes('Save'))
  expect(save, 'Save button must be rendered').toBeTruthy()
  await save!.trigger('click')
  await nextTick()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NodeConfigPanel operation mode (T7)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(unifiedApi.call).mockResolvedValue(TOOL_LIST)
  })

  it('(a) tool with operations → operation selector lists them, no legacy form', async () => {
    const wrapper = mountPanel(makeNode({ tool: 'apktool' }))
    await settled()

    const selects = wrapper.findAll('.n-select-stub')
    expect(selects.length).toBe(1) // the operation selector only
    const optionLabels = selects[0].findAll('option').map((o) => o.text())
    expect(optionLabels).toEqual(['decode', 'build'])
    // No operation selected yet → no parameter form rendered.
    expect(wrapper.findAll('.form-item-stub').length).toBe(0)
  })

  it('(b) selecting an operation renders exactly its input ports', async () => {
    const wrapper = mountPanel(makeNode({ tool: 'apktool' }))
    await settled()

    await wrapper.find('.n-select-stub').setValue('decode')
    await nextTick()
    expect(labels(wrapper)).toEqual(['apk_path', 'output_dir', 'force'])
    // Required-ness comes from the operation's port declaration.
    const items = wrapper.findAll('.form-item-stub')
    expect(items[0].attributes('data-required')).toBe('true')
    expect(items[1].attributes('data-required')).toBe('false')
    expect(items[2].attributes('data-required')).toBe('false')

    // Switching operations swaps the port set.
    await wrapper.find('.n-select-stub').setValue('build')
    await nextTick()
    expect(labels(wrapper)).toEqual(['source_dir', 'output_apk'])
  })

  it('(c) save writes node.data.operation/inputs and serializes to exact engine params', async () => {
    const node = makeNode({ tool: 'apktool' })
    const wrapper = mountPanel(node)
    await settled()

    await wrapper.find('.n-select-stub').setValue('decode')
    await nextTick()
    const items = wrapper.findAll('.form-item-stub')
    await items[0].find('.n-input-stub').setValue('app.apk')
    await items[1].find('.n-input-stub').setValue('out')
    await items[2].find('.n-switch-stub').setValue(true)
    await clickSave(wrapper)

    const data = node.data as Record<string, any>
    expect(data.operation).toBe('decode')
    expect(data.inputs).toEqual({ apk_path: 'app.apk', output_dir: 'out', force: true })

    const doc = serializeWorkflow([node], [], { name: 'wf' })
    const params = doc.nodes[0].params
    expect(params).toEqual({ operation: 'decode', apk_path: 'app.apk', output_dir: 'out', force: true })
    // EXACT shape including key order — `operation` first (T4 engine contract).
    expect(JSON.stringify(params)).toBe(
      JSON.stringify({ operation: 'decode', apk_path: 'app.apk', output_dir: 'out', force: true }),
    )
  })

  it('(d) missing required operation input blocks save with an error message', async () => {
    const node = makeNode({ tool: 'apktool' })
    const wrapper = mountPanel(node)
    await settled()

    await wrapper.find('.n-select-stub').setValue('decode')
    await nextTick()
    // fill only the optional ports; required apk_path stays empty
    await clickSave(wrapper)

    expect(wrapper.text()).toContain('workflow.editor.config.errors.missingRequired')
    const data = node.data as Record<string, any>
    expect(data.operation).toBeUndefined()
    expect(data.inputs).toBeUndefined()
    const doc = serializeWorkflow([node], [], { name: 'wf' })
    expect(doc.nodes[0].params).toEqual({})
  })

  it('(d2) clearing a saved operation blocks save with noOperation error', async () => {
    // Node carries a previously saved operation (hydrate path, as after a
    // template load); the user clears the selector → save must be blocked.
    const node = makeNode({
      tool: 'apktool',
      operation: 'decode',
      inputs: { apk_path: 'app.apk' },
    })
    const wrapper = mountPanel(node)
    await settled()

    expect(wrapper.find('.n-select-stub').exists()).toBe(true)
    await wrapper.find('.n-select-stub').setValue('')
    await nextTick()
    await clickSave(wrapper)

    expect(wrapper.text()).toContain('workflow.editor.config.errors.noOperation')
    const data = node.data as Record<string, any>
    expect(data.operation).toBe('decode') // blocked: previous state untouched
  })

  it('(e) builtin tool keeps the legacy free-form params path and serialization', async () => {
    const node = makeNode({
      tool: 'file.read',
      ports: FILEREAD.ports,
    })
    const wrapper = mountPanel(node)
    await settled()

    // No operation selector for builtin/legacy tools.
    expect(wrapper.findAll('.n-select-stub').length).toBe(0)
    expect(labels(wrapper)).toEqual(['path'])

    await wrapper.find('.n-input-stub').setValue('/tmp/x.txt')
    await clickSave(wrapper)

    const data = node.data as Record<string, any>
    expect(data.params).toEqual({ path: '/tmp/x.txt' })
    expect(data.operation).toBeUndefined()
    expect(data.inputs).toBeUndefined()

    const doc = serializeWorkflow([node], [], { name: 'wf' })
    expect(doc.nodes[0].params).toEqual({ path: '/tmp/x.txt' })
  })

  it('(f) T5 raw operation params hydrate the operation UI and round-trip exactly', async () => {
    const doc = deserializeWorkflow(decompileExample as any)
    const node = doc.nodes[0]

    const data = node.data as Record<string, any>
    expect(data.operation).toBe('decode')
    expect(data.inputs).toEqual({
      apk_path: '$inputs.apk_path',
      output_dir: '$inputs.output_dir',
      force: true,
    })

    const wrapper = mountPanel(node as unknown as Node)
    await settled()

    // Operation selector shows the hydrated operation; bindings are visible.
    expect(wrapper.find('.n-select-stub').exists()).toBe(true)
    expect(labels(wrapper)).toEqual(['apk_path', 'output_dir', 'force'])
    const items = wrapper.findAll('.form-item-stub')
    expect((items[0].find('.n-input-stub').element as HTMLInputElement).value).toBe('$inputs.apk_path')
    expect((items[1].find('.n-input-stub').element as HTMLInputElement).value).toBe('$inputs.output_dir')
    expect((items[2].find('.n-switch-stub').element as HTMLInputElement).checked).toBe(true)

    // Re-serialize: byte-identical params shape (key order included).
    const reserialized = serializeWorkflow(doc.nodes, doc.edges, { name: decompileExample.name })
    const rawParams = (decompileExample as any).nodes[0].params
    expect(reserialized.nodes[0].params).toEqual(rawParams)
    expect(JSON.stringify(reserialized.nodes[0].params)).toBe(JSON.stringify(rawParams))
  })

  it('(g) select ports: single stores the chosen string, multi stores an array', async () => {
    const node = makeNode({ tool: 'synthtool' })
    const wrapper = mountPanel(node)
    await settled()

    await wrapper.find('.n-select-stub').setValue('configure')
    await nextTick()

    const selects = wrapper.findAll('.n-select-stub')
    expect(selects.length).toBe(3) // operation selector + mode + tags
    expect(selects[1].findAll('option').map((o) => o.text())).toEqual(['alpha', 'beta', 'gamma'])
    expect(selects[2].findAll('option').map((o) => o.text())).toEqual(['x', 'y'])

    await selects[1].setValue('beta')
    await selects[2].setValue(['x', 'y'])
    await nextTick()
    await clickSave(wrapper)

    const data = node.data as Record<string, any>
    expect(data.operation).toBe('configure')
    expect(data.inputs).toEqual({ mode: 'beta', tags: ['x', 'y'] })

    const doc = serializeWorkflow([node], [], { name: 'wf' })
    expect(doc.nodes[0].params).toEqual({ operation: 'configure', mode: 'beta', tags: ['x', 'y'] })
  })

  it('(g2) empty multi-select stays absent from serialized params', async () => {
    const node = makeNode({ tool: 'synthtool' })
    const wrapper = mountPanel(node)
    await settled()

    await wrapper.find('.n-select-stub').setValue('configure')
    await nextTick()
    const selects = wrapper.findAll('.n-select-stub')
    await selects[1].setValue('alpha') // required single-select filled
    await clickSave(wrapper)

    const doc = serializeWorkflow([node], [], { name: 'wf' })
    expect(doc.nodes[0].params).toEqual({ operation: 'configure', mode: 'alpha' })
    expect(doc.nodes[0].params).not.toHaveProperty('tags')
  })

  it('(h) native plugin tool (kind "native") with ports renders the legacy port form like builtins', async () => {
    // Palette grouping puts kind "native" under Plugins, but the panel's
    // config mode is operations-driven, not kind/builtin-driven: a native
    // plugin without operations gets the same free-form params UI as a
    // shipped-native builtin.
    const node = makeNode({ tool: 'my.native', ports: NATIVEPLUGIN.ports })
    const wrapper = mountPanel(node)
    await settled()

    expect(wrapper.findAll('.n-select-stub').length).toBe(0) // no operation selector
    expect(labels(wrapper)).toEqual(['input_text', 'count'])

    await wrapper.find('.n-input-stub').setValue('hello')
    await clickSave(wrapper)

    const data = node.data as Record<string, any>
    expect(data.params).toEqual({ input_text: 'hello' })
    expect(data.operation).toBeUndefined()
    expect(data.inputs).toBeUndefined()

    const doc = serializeWorkflow([node], [], { name: 'wf' })
    expect(doc.nodes[0].params).toEqual({ input_text: 'hello' })
  })

  it('(i) native plugin tool declaring operations uses operation mode', async () => {
    const node = makeNode({ tool: 'my.nativeop', ports: NATIVEOP.ports })
    const wrapper = mountPanel(node)
    await settled()

    const selects = wrapper.findAll('.n-select-stub')
    expect(selects.length).toBe(1) // operation selector only
    expect(selects[0].findAll('option').map((o) => o.text())).toEqual(['transform'])
    expect(wrapper.findAll('.form-item-stub').length).toBe(0) // no op selected yet

    await selects[0].setValue('transform')
    await nextTick()
    expect(labels(wrapper)).toEqual(['value'])

    await wrapper.find('.n-input-stub').setValue('abc')
    await clickSave(wrapper)

    const data = node.data as Record<string, any>
    expect(data.operation).toBe('transform')
    expect(data.inputs).toEqual({ value: 'abc' })
    expect(data.params).toBeUndefined()
  })
})
