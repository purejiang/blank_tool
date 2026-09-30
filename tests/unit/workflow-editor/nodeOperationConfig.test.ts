/**
 * T7 — Node config driven by operation typed inputs.
 *
 * Covers the NodeConfigPanel: operation mode (descriptor tools that expose
 * operations via workflow.list_tools), the legacy free-form params fallback
 * (builtin tools / descriptors without operations), native plugin tools
 * (kind "native"), the read-only node id / editable node name, the typed
 * parameter badges, the optional-parameter disclosure, the 跟随系统 / 自定义
 * behaviour toggle, and the serializer mapping between node.data.{operation,
 * inputs} and the engine wire params `{operation, <input_name>: value}` (T4
 * contract), including the T5 round-trip shape of
 * examples/workflows/android/decompile.json.
 *
 * The panel applies edits IMMEDIATELY (there is no per-node Save button), so
 * every assertion checks `node.data` right after the interaction.
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
// Mocks (hoisted): ServiceManager (path pickers + node defaults) + unifiedApi
// ---------------------------------------------------------------------------

/** appConfig `nodes` payload the mocked config service returns. */
let nodeDefaultsConfig: Record<string, unknown> = { onFailure: 'fail', retry: 0 }

vi.mock('@services/ServiceManager', () => ({
  default: {
    register: vi.fn(),
    getService: vi.fn(async (name: string) => {
      if (name === 'config') {
        return { getAppConfig: async () => nodeDefaultsConfig }
      }
      return { selectFile: vi.fn(), selectDirectory: vi.fn() }
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
      // Shares `output_dir` with `decode` on purpose: switching operations must
      // carry a same-named value over instead of wiping the whole form.
      inputs: [port('source_dir', 'directory'), port('output_dir', 'file')],
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
  description: 'Read a text file.',
  ports: {
    inputs: [port('path', 'file')],
    outputs: [port('content', 'text')],
  },
}

/** Builtin tool with one required and four optional inputs (collapse case). */
const SHELLEXEC = {
  name: 'exec.shell',
  is_valid: true,
  version: '',
  tool_path: '',
  builtin: true,
  ports: {
    inputs: [
      port('command', 'text'),
      port('cwd', 'directory', { required: false }),
      port('timeout', 'number', { required: false }),
      port('env', 'json', { required: false }),
      port('shell', 'text', { required: false }),
    ],
    outputs: [port('stdout', 'text')],
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

const TOOL_LIST = { tools: [APKTOOL, SYNTHTOOL, FILEREAD, SHELLEXEC, NATIVEPLUGIN, NATIVEOP] }

// ---------------------------------------------------------------------------
// Naive-ui stubs — plain render functions (no runtime template compilation).
// v-model:value is honored via `value` prop + `update:value` emits.
// NOTE: naive-ui registers its components under unprefixed names
// (NSelect.name === 'Select', etc.), so stub keys use those names.
// ---------------------------------------------------------------------------

const NAIVE_STUBS: Record<string, unknown> = {
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
            value: props.value ?? '',
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
  RadioGroup: {
    name: 'RadioGroup',
    props: { value: null },
    emits: ['update:value'],
    setup(_props: any, { slots }: any) {
      return () => h('div', { class: 'n-radio-group-stub' }, slots.default?.())
    },
  },
  RadioButton: {
    name: 'RadioButton',
    props: { value: null },
    setup(props: any, { slots }: any) {
      return () =>
        h('button', { class: 'n-radio-stub', 'data-value': String(props.value) }, slots.default?.())
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

/** Flush the panel's workflow.list_tools + node-defaults fetches. */
async function settled() {
  await flushPromises()
  await nextTick()
  await nextTick()
}

/** Parameter rows in display order (AppField roots carrying `npc-param`). */
function paramRows(wrapper: ReturnType<typeof mountPanel>) {
  return wrapper.findAll('.npc-param')
}

/** Port names of the rendered parameter rows (the required star is stripped). */
function paramNames(wrapper: ReturnType<typeof mountPanel>): string[] {
  return paramRows(wrapper).map((row) => row.find('.npc-param-name').text().replace(/\*+$/, '').trim())
}

/** Type badge text of the rendered parameter rows (i18n keys here). */
function paramBadges(wrapper: ReturnType<typeof mountPanel>): string[] {
  return paramRows(wrapper).map((row) => row.find('[data-test="port-type-badge"]').text())
}

/** Selects owned by the panel (excludes the binding picker's pipe selector). */
function panelSelects(wrapper: ReturnType<typeof mountPanel>) {
  return wrapper.findAll('.n-select-stub:not(.ep-transform-select)')
}

/** Operation selector (`data-test="npc-operation"`). */
function operationSelect(wrapper: ReturnType<typeof mountPanel>) {
  return wrapper.find('[data-test="npc-operation"]')
}

/** Toggle 跟随系统 / 自定义 (radio group stub emits on the group). */
async function setBehaviorMode(wrapper: ReturnType<typeof mountPanel>, mode: 'inherit' | 'custom') {
  const group = wrapper.findComponent({ name: 'RadioGroup' })
  expect(group.exists(), 'behaviour radio group must be rendered').toBe(true)
  group.vm.$emit('update:value', mode)
  await nextTick()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NodeConfigPanel operation mode (T7)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    nodeDefaultsConfig = { onFailure: 'fail', retry: 0 }
    vi.mocked(unifiedApi.call).mockResolvedValue(TOOL_LIST)
  })

  it('(a) tool with operations → operation selector lists them, no parameter rows yet', async () => {
    const wrapper = mountPanel(makeNode({ tool: 'apktool' }))
    await settled()

    const selects = panelSelects(wrapper)
    expect(selects.length).toBe(1) // operation selector only (behaviour is a radio group)
    const optionLabels = selects[0].findAll('option').map((o) => o.text())
    expect(optionLabels).toEqual(['decode', 'build'])
    // No operation selected yet → no parameter form rendered.
    expect(paramRows(wrapper).length).toBe(0)
  })

  it('(b) selecting an operation renders exactly its input ports with type badges', async () => {
    const wrapper = mountPanel(makeNode({ tool: 'apktool' }))
    await settled()

    await operationSelect(wrapper).setValue('decode')
    await nextTick()
    expect(paramNames(wrapper)).toEqual(['apk_path', 'output_dir', 'force'])
    // Type badges reuse the shared widget-type vocabulary (file / directory / boolean),
    // and carry the advisory subtype when the port declares one.
    const badges = paramBadges(wrapper)
    expect(badges[0]).toContain('workflow.editor.io.types.file')
    expect(badges[0]).toContain('apk')
    expect(badges[1]).toContain('workflow.editor.io.types.directory')
    expect(badges[2]).toContain('workflow.editor.io.types.boolean')
    // Required-ness comes from the operation's port declaration.
    const rows = paramRows(wrapper)
    expect(rows[0].find('.npc-req').exists()).toBe(true)
    expect(rows[1].find('.npc-req').exists()).toBe(false)
    expect(rows[2].find('.npc-req').exists()).toBe(false)

    // Switching operations swaps the port set (and carries same-named values).
    await operationSelect(wrapper).setValue('build')
    await nextTick()
    expect(paramNames(wrapper)).toEqual(['source_dir', 'output_dir'])
  })

  it('(c) editing applies immediately and serializes to exact engine params', async () => {
    const node = makeNode({ tool: 'apktool' })
    const wrapper = mountPanel(node)
    await settled()

    await operationSelect(wrapper).setValue('decode')
    await nextTick()
    const rows = paramRows(wrapper)
    await rows[0].find('.n-input-stub').setValue('app.apk')
    await rows[1].find('.n-input-stub').setValue('out')
    await rows[2].find('.n-switch-stub').setValue(true)
    await nextTick()

    // No Save button exists: the edits are already in node.data.
    expect(wrapper.find('[data-test="npc-save"]').exists()).toBe(false)
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

  it('(c2) switching operations keeps same-named values and drops the rest', async () => {
    const node = makeNode({
      tool: 'apktool',
      operation: 'decode',
      inputs: { apk_path: 'app.apk', output_dir: 'out' },
    })
    const wrapper = mountPanel(node)
    await settled()

    expect(paramNames(wrapper)).toEqual(['apk_path', 'output_dir', 'force'])
    await operationSelect(wrapper).setValue('build')
    await nextTick()

    const data = node.data as Record<string, any>
    expect(data.operation).toBe('build')
    // `output_dir` exists in both operations → carried; `apk_path` does not.
    expect(data.inputs).toEqual({ output_dir: 'out' })
  })

  it('(d) missing required inputs are summarised, then flagged on the touched field', async () => {
    const node = makeNode({ tool: 'apktool' })
    const wrapper = mountPanel(node)
    await settled()

    await operationSelect(wrapper).setValue('decode')
    await nextTick()

    // Untouched empty form: a quiet summary instead of a wall of red.
    expect(wrapper.text()).toContain('workflow.editor.config.errors.pendingHint')
    expect(wrapper.text()).not.toContain('workflow.editor.config.errors.missingRequired')

    // Touching the required field and clearing it surfaces the field-level error.
    const row = paramRows(wrapper)[0]
    await row.find('.n-input-stub').setValue('app.apk')
    await nextTick()
    await row.find('.n-input-stub').setValue('')
    await nextTick()
    expect(wrapper.text()).toContain('workflow.editor.config.errors.missingRequired')
    expect((node.data as Record<string, any>).inputs).toEqual({})
  })

  it('(d2) clearing the operation drops the operation state', async () => {
    const node = makeNode({
      tool: 'apktool',
      operation: 'decode',
      inputs: { apk_path: 'app.apk' },
    })
    const wrapper = mountPanel(node)
    await settled()

    await operationSelect(wrapper).setValue('')
    await nextTick()

    const data = node.data as Record<string, any>
    expect(data.operation).toBeUndefined()
    expect(data.inputs).toBeUndefined()
    // The panel now asks for an operation again (and the page blocks saving).
    expect(wrapper.text()).toContain('workflow.editor.config.operationPlaceholder')
  })

  it('(e) builtin tool keeps the legacy free-form params path and serialization', async () => {
    const node = makeNode({
      tool: 'file.read',
      ports: FILEREAD.ports,
    })
    const wrapper = mountPanel(node)
    await settled()

    // No operation selector for builtin/legacy tools.
    expect(panelSelects(wrapper).length).toBe(0)
    expect(paramNames(wrapper)).toEqual(['path'])

    await paramRows(wrapper)[0].find('.n-input-stub').setValue('/tmp/x.txt')
    await nextTick()

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
    expect(operationSelect(wrapper).exists()).toBe(true)
    expect(paramNames(wrapper)).toEqual(['apk_path', 'output_dir', 'force'])
    const rows = paramRows(wrapper)
    expect((rows[0].find('.n-input-stub').element as HTMLInputElement).value).toBe('$inputs.apk_path')
    expect((rows[1].find('.n-input-stub').element as HTMLInputElement).value).toBe('$inputs.output_dir')
    expect((rows[2].find('.n-switch-stub').element as HTMLInputElement).checked).toBe(true)

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

    await operationSelect(wrapper).setValue('configure')
    await nextTick()

    const selects = panelSelects(wrapper)
    expect(selects.length).toBe(3) // operation selector + mode + tags
    expect(selects[1].findAll('option').map((o) => o.text())).toEqual(['alpha', 'beta', 'gamma'])
    expect(selects[2].findAll('option').map((o) => o.text())).toEqual(['x', 'y'])

    await selects[1].setValue('beta')
    await selects[2].setValue(['x', 'y'])
    await nextTick()

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

    await operationSelect(wrapper).setValue('configure')
    await nextTick()
    const selects = panelSelects(wrapper)
    await selects[1].setValue('alpha') // required single-select filled
    await nextTick()

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

    expect(panelSelects(wrapper).length).toBe(0) // no operation selector
    expect(paramNames(wrapper)).toEqual(['input_text', 'count'])

    await paramRows(wrapper)[0].find('.n-input-stub').setValue('hello')
    await nextTick()

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

    const selects = panelSelects(wrapper)
    expect(selects.length).toBe(1) // operation selector only
    expect(selects[0].findAll('option').map((o) => o.text())).toEqual(['transform'])
    expect(paramRows(wrapper).length).toBe(0) // no op selected yet

    await selects[0].setValue('transform')
    await nextTick()
    expect(paramNames(wrapper)).toEqual(['value'])

    await paramRows(wrapper)[0].find('.n-input-stub').setValue('abc')
    await nextTick()

    const data = node.data as Record<string, any>
    expect(data.operation).toBe('transform')
    expect(data.inputs).toEqual({ value: 'abc' })
    expect(data.params).toBeUndefined()
  })
})

describe('NodeConfigPanel identity + behaviour', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    nodeDefaultsConfig = { onFailure: 'fail', retry: 0 }
    vi.mocked(unifiedApi.call).mockResolvedValue(TOOL_LIST)
  })

  it('shows the auto-generated id read-only and edits the node name', async () => {
    const node = makeNode({ tool: 'file.read', ports: FILEREAD.ports }, 'tool-file-read-7')
    const wrapper = mountPanel(node)
    await settled()

    // The id is a read-only label, not an input.
    const id = wrapper.find('[data-test="npc-id"]')
    expect(id.exists()).toBe(true)
    expect(id.text()).toBe('tool-file-read-7')

    const name = wrapper.find('[data-test="npc-name"]')
    expect((name.element as HTMLInputElement).value).toBe('file.read')
    await name.setValue('读取配置')
    await nextTick()
    expect((node.data as Record<string, any>).label).toBe('读取配置')

    // Clearing the name falls back to the tool name (the key is dropped).
    await name.setValue('  ')
    await nextTick()
    expect((node.data as Record<string, any>).label).toBeUndefined()
  })

  it('defaults to 跟随系统: no behaviour fields, summary shows the settings defaults', async () => {
    nodeDefaultsConfig = { onFailure: 'skip', retry: 2 }
    const node = makeNode({ tool: 'file.read', ports: FILEREAD.ports })
    const wrapper = mountPanel(node)
    await settled()

    const data = node.data as Record<string, any>
    expect(data.on_failure).toBeUndefined()
    expect(data.retry).toBeUndefined()
    expect(wrapper.text()).toContain('workflow.editor.config.behavior.inheritSummary')
    // The wire document stays "inherit" (no keys at all).
    const doc = serializeWorkflow([node], [], { name: 'wf' })
    expect(doc.nodes[0]).not.toHaveProperty('on_failure')
    expect(doc.nodes[0]).not.toHaveProperty('retry')
  })

  it('switching to 自定义 prefills the effective defaults and writes them', async () => {
    nodeDefaultsConfig = { onFailure: 'skip', retry: 2 }
    const node = makeNode({ tool: 'file.read', ports: FILEREAD.ports })
    const wrapper = mountPanel(node)
    await settled()

    await setBehaviorMode(wrapper, 'custom')
    const data = node.data as Record<string, any>
    expect(data.on_failure).toBe('skip')
    expect(data.retry).toBe(2)

    // Editing either field applies immediately.
    await wrapper.find('[data-test="npc-on-failure"]').setValue('fail')
    await wrapper.find('[data-test="npc-retry"]').setValue('5')
    await nextTick()
    expect(data.on_failure).toBe('fail')
    expect(data.retry).toBe(5)

    const doc = serializeWorkflow([node], [], { name: 'wf' })
    expect(doc.nodes[0].on_failure).toBe('fail')
    expect(doc.nodes[0].retry).toBe(5)

    // Back to 跟随系统 → the node stops pinning values.
    await setBehaviorMode(wrapper, 'inherit')
    expect(data.on_failure).toBeUndefined()
    expect(data.retry).toBeUndefined()
  })

  it('a node with pinned behaviour opens in 自定义 mode', async () => {
    const node = makeNode({
      tool: 'file.read',
      ports: FILEREAD.ports,
      on_failure: 'skip',
      retry: 3,
    })
    const wrapper = mountPanel(node)
    await settled()

    expect(wrapper.find('[data-test="npc-on-failure"]').exists()).toBe(true)
    expect((wrapper.find('[data-test="npc-on-failure"]').element as HTMLSelectElement).value).toBe('skip')
    expect((wrapper.find('[data-test="npc-retry"]').element as HTMLInputElement).value).toBe('3')
    expect(wrapper.text()).not.toContain('workflow.editor.config.behavior.inheritSummary')
  })

  it('collapses optional parameters once there are more than three', async () => {
    const node = makeNode({ tool: 'exec.shell', ports: SHELLEXEC.ports })
    const wrapper = mountPanel(node)
    await settled()

    // Required first, optionals hidden behind the toggle.
    expect(paramNames(wrapper)).toEqual(['command'])
    const toggle = wrapper.find('[data-test="npc-optional-toggle"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toContain('workflow.editor.config.optional.expand')

    await toggle.trigger('click')
    await nextTick()
    expect(paramNames(wrapper)).toEqual(['command', 'cwd', 'timeout', 'env', 'shell'])
  })

  it('does not render the delete button without a node and emits delete for a node', async () => {
    const empty = mountPanel(null)
    await settled()
    expect(empty.text()).toContain('workflow.editor.config.noSelection')

    const node = makeNode({ tool: 'file.read', ports: FILEREAD.ports })
    const wrapper = mountPanel(node)
    await settled()
    await wrapper.find('[data-test="npc-delete"]').trigger('click')
    expect(wrapper.emitted('delete')).toEqual([['node-1']])
  })
})
