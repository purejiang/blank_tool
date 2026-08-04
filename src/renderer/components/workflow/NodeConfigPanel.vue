<template>
  <div class="node-config-panel">
    <div v-if="!node" class="npc-empty">{{ t('workflow.editor.config.noSelection') }}</div>
    <template v-else>
      <!-- Tool identity -->
      <div class="npc-identity">
        <div class="npc-tool-name">{{ toolName }}</div>
        <div v-if="description" class="npc-tool-desc">{{ description }}</div>
      </div>

      <div class="npc-body">
        <!-- Operation mode (T7): descriptor tools exposing operations -->
        <template v-if="isOperationMode">
          <div class="npc-section">
            <div class="npc-section-title">{{ t('workflow.editor.config.operation') }}</div>
            <n-select
              v-model:value="selectedOperation"
              size="small"
              :options="operationOptions"
              :placeholder="t('workflow.editor.config.operationPlaceholder')"
              clearable
              @update:value="onOperationChange"
            />
            <div v-if="currentOperation && currentOperation.description" class="npc-op-desc">
              {{ currentOperation.description }}
            </div>
          </div>

          <div class="npc-section">
            <div class="npc-section-title">{{ t('workflow.editor.config.parameters') }}</div>
            <div v-if="!selectedOperation" class="npc-empty-inline">
              {{ t('workflow.editor.config.operationPlaceholder') }}
            </div>
            <div v-else-if="operationInputPorts.length === 0" class="npc-empty-inline">
              {{ t('workflow.editor.config.noParameters') }}
            </div>
            <n-form v-else :model="draft" label-placement="top" size="small">
              <n-form-item
                v-for="port in operationInputPorts"
                :key="port.name"
                :label="port.name"
                :required="isRequired(port)"
              >
                <!-- file / directory: text input + native picker button -->
                <div v-if="isPathPort(port)" class="npc-path-row">
                  <n-input
                    v-model:value="draft[port.name]"
                    class="npc-path-input"
                    size="small"
                    :placeholder="
                      portTypeOf(port) === 'directory'
                        ? t('workflow.editor.config.placeholders.directory')
                        : t('workflow.editor.config.placeholders.file')
                    "
                  />
                  <n-button size="small" @click="browsePath(port)">Browse</n-button>
                </div>
                <!-- boolean -->
                <n-switch
                  v-else-if="portKindOf(port) === 'boolean'"
                  v-model:value="draft[port.name]"
                />
                <!-- number -->
                <n-input-number
                  v-else-if="portKindOf(port) === 'number'"
                  v-model:value="draft[port.name]"
                  class="npc-full"
                  size="small"
                  :show-button="false"
                  placeholder="0"
                />
                <!-- json: monospace textarea -->
                <n-input
                  v-else-if="portKindOf(port) === 'json'"
                  v-model:value="draft[port.name]"
                  class="npc-mono"
                  size="small"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 8 }"
                  :placeholder="t('workflow.editor.config.placeholders.json')"
                />
                <!-- single-select (options on a text base, T2 select kinds) -->
                <n-select
                  v-else-if="portKindOf(port) === 'single_select'"
                  v-model:value="draft[port.name]"
                  size="small"
                  :options="selectOptions(port)"
                />
                <!-- multi-select (options + multi) -->
                <n-select
                  v-else-if="portKindOf(port) === 'multi_select'"
                  v-model:value="draft[port.name]"
                  size="small"
                  multiple
                  :options="selectOptions(port)"
                />
                <!-- text / unknown: textarea for longer values -->
                <n-input
                  v-else
                  v-model:value="draft[port.name]"
                  size="small"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                  :placeholder="t('workflow.editor.config.placeholders.text')"
                />
                <template v-if="port.description" #feedback>
                  <span class="npc-port-desc">{{ port.description }}</span>
                </template>
              </n-form-item>
            </n-form>
          </div>
        </template>

        <!-- Legacy free-form mode: builtin tools + descriptors without operations -->
        <template v-else>
          <div class="npc-section">
            <div class="npc-section-title">Parameters</div>
            <div v-if="inputPorts.length === 0" class="npc-empty-inline">No parameters</div>
            <n-form v-else :model="draft" label-placement="top" size="small">
              <n-form-item
                v-for="port in inputPorts"
                :key="port.name"
                :label="port.name"
                :required="isRequired(port)"
              >
                <!-- file / directory: text input + native picker button -->
                <div v-if="isPathPort(port)" class="npc-path-row">
                  <n-input
                    v-model:value="draft[port.name]"
                    class="npc-path-input"
                    size="small"
                    :placeholder="portTypeOf(port) === 'directory' ? '/path/to/folder' : '/path/to/file'"
                  />
                  <n-button size="small" @click="browsePath(port)">Browse</n-button>
                </div>
                <!-- boolean -->
                <n-switch
                  v-else-if="portTypeOf(port) === 'boolean'"
                  v-model:value="draft[port.name]"
                />
                <!-- number -->
                <n-input-number
                  v-else-if="portTypeOf(port) === 'number'"
                  v-model:value="draft[port.name]"
                  class="npc-full"
                  size="small"
                  :show-button="false"
                  placeholder="0"
                />
                <!-- json: monospace textarea -->
                <n-input
                  v-else-if="portTypeOf(port) === 'json'"
                  v-model:value="draft[port.name]"
                  class="npc-mono"
                  size="small"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 8 }"
                  placeholder='{ "key": "value" }'
                />
                <!-- text / unknown: textarea for longer values -->
                <n-input
                  v-else
                  v-model:value="draft[port.name]"
                  size="small"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                  placeholder="Text value (expressions are typed as plain text)"
                />
                <template v-if="port.description" #feedback>
                  <span class="npc-port-desc">{{ port.description }}</span>
                </template>
              </n-form-item>
            </n-form>
          </div>

          <!-- Output ports: read-only -->
          <div v-if="outputPorts.length > 0" class="npc-section">
            <div class="npc-section-title">Outputs</div>
            <div class="npc-outputs">
              <div
                v-for="port in outputPorts"
                :key="port.name"
                class="npc-output-row"
                :title="port.description || ''"
              >
                <span class="npc-dot" :class="`npc-dot--${portTypeOf(port)}`" />
                <span class="npc-output-name">{{ port.name }}</span>
                <span class="npc-output-type">{{ typeLabel(port) }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Commit draft values to node.data (params or operation/inputs) -->
      <div class="npc-footer">
        <div v-if="saveError" class="npc-error">{{ saveError }}</div>
        <n-button size="small" type="primary" :disabled="!dirty" @click="save">Save</n-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NForm, NFormItem, NInput, NInputNumber, NSwitch, NButton, NSelect } from 'naive-ui'
import type { Node } from '@vue-flow/core'
import serviceManager from '@services/ServiceManager'
import unifiedApi from '../../api/unifiedApi'
import { log } from '@utils/logger'
import { portJsonToTypeKey, type PortTypeKey } from './ioAuthoring'
import type { ToolNodeData, ToolOperation, ToolPorts, WorkflowToolInfo } from './toolMeta'

const { t } = useI18n()

/**
 * Loose port shape accepted by this panel. Todo 34's `ToolPort` (toolMeta.ts,
 * mirroring backend `Port.to_dict()`) is structurally assignable to it; the
 * looser form also tolerates bare base-name type strings or missing fields
 * (e.g. nodes rebuilt by the todo 37 deserializer) without crashing.
 * options/multi arrive on operation input ports (T2/T7).
 */
interface LoosePort {
  name: string
  type?: string | { base?: string; subtype?: string | null }
  required?: boolean
  description?: string
  options?: unknown
  multi?: unknown
}

const props = defineProps<{
  /** Selected vue-flow node; null/undefined when nothing is selected. */
  node?: Node | null
}>()

// ---- node data accessors ---------------------------------------------
// Node payload contract is toolMeta.ts `ToolNodeData`:
//   { tool, status?, ports?: { inputs, outputs }, params? (legacy mode),
//     operation?, inputs? (operation mode, T7) }

const nodeData = computed<Record<string, any>>(() => (props.node?.data ?? {}) as Record<string, any>)

const toolName = computed<string>(() => {
  const d = nodeData.value
  return String(d.tool || d.toolName || d.label || props.node?.id || 'Unknown tool')
})

const description = computed<string>(() => {
  const desc = nodeData.value.description
  return typeof desc === 'string' ? desc : ''
})

function toPorts(raw: unknown): LoosePort[] {
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (p): p is LoosePort => !!p && typeof p === 'object' && typeof (p as LoosePort).name === 'string',
  )
}

/** Prefer todo 34's nested data.ports; tolerate flat data.inputs/outputs. */
const ports = computed<ToolPorts | null>(() => {
  const d = nodeData.value
  if (d.ports && typeof d.ports === 'object') return d.ports as ToolPorts
  if (Array.isArray(d.inputs) || Array.isArray(d.outputs)) {
    return { inputs: d.inputs, outputs: d.outputs } as ToolPorts
  }
  return null
})

const inputPorts = computed<LoosePort[]>(() => toPorts(ports.value?.inputs))
const outputPorts = computed<LoosePort[]>(() => toPorts(ports.value?.outputs))

// ---- tool metadata (operation mode, T7) --------------------------------
// The editor page/palette fetch workflow.list_tools for their own needs; the
// panel fetches it independently so it stays self-contained (no parent prop).
// On failure the panel degrades to the legacy free-form params UI — exactly
// the pre-T7 behavior.

const toolList = ref<WorkflowToolInfo[]>([])
let toolsFetched = false

async function fetchToolList() {
  if (toolsFetched) return
  toolsFetched = true
  try {
    const result = await unifiedApi.call<{ tools?: WorkflowToolInfo[] }>('workflow.list_tools', {})
    toolList.value = Array.isArray(result?.tools) ? result.tools : []
  } catch (err) {
    log.warn('[NodeConfigPanel] workflow.list_tools unavailable; operation mode disabled', err)
  }
  // Mode (operation vs legacy) may have changed — rehydrate the draft.
  resetDraft()
}

onMounted(fetchToolList)

const currentToolMeta = computed<WorkflowToolInfo | null>(() => {
  const name = nodeData.value.tool
  if (typeof name !== 'string') return null
  return toolList.value.find((tool) => tool?.name === name) ?? null
})

const operations = computed<ToolOperation[]>(() => {
  const ops = currentToolMeta.value?.operations
  return Array.isArray(ops) ? ops : []
})

/** Operation mode iff the selected tool declares operations (T7). */
const isOperationMode = computed(() => operations.value.length > 0)

const operationOptions = computed(() =>
  operations.value.map((op) => ({ label: op.name, value: op.name })),
)

const selectedOperation = ref<string | null>(null)

const currentOperation = computed<ToolOperation | null>(() => {
  if (!selectedOperation.value) return null
  return operations.value.find((op) => op.name === selectedOperation.value) ?? null
})

const operationInputPorts = computed<LoosePort[]>(() => toPorts(currentOperation.value?.inputs))

function selectOptions(port: LoosePort) {
  const options = Array.isArray(port.options) ? port.options : []
  return options.map((value) => ({ label: String(value), value: String(value) }))
}

// ---- port type helpers -------------------------------------------------

const KNOWN_BASE_TYPES = ['file', 'directory', 'text', 'number', 'boolean', 'json']

function portTypeOf(port: LoosePort): string {
  const t = port.type
  let base = ''
  if (typeof t === 'string') base = t
  else if (t && typeof t === 'object' && typeof t.base === 'string') base = t.base
  base = base.toLowerCase()
  // Unknown/missing types degrade to a plain text field (advisory typing, D7).
  return KNOWN_BASE_TYPES.includes(base) ? base : 'text'
}

/**
 * Widget kind for an operation input port — reuses the T6 reverse mapping:
 * text base + options (+multi) → single_select / multi_select; bare bases
 * map 1:1; unknown degrades to text.
 */
function portKindOf(port: LoosePort): PortTypeKey {
  const base = portTypeOf(port)
  return portJsonToTypeKey({
    name: port.name,
    type: { base },
    options: Array.isArray(port.options) ? (port.options as string[]) : [],
    multi: port.multi === true,
  })
}

function typeLabel(port: LoosePort): string {
  const base = portTypeOf(port)
  const t = port.type
  if (t && typeof t === 'object' && typeof t.subtype === 'string' && t.subtype) {
    return `${base}/${t.subtype}`
  }
  return base
}

function isRequired(port: LoosePort): boolean {
  // Backend Port defaults to required=True when the flag is absent.
  return port.required !== false
}

function isPathPort(port: LoosePort): boolean {
  const t = portTypeOf(port)
  return t === 'file' || t === 'directory'
}

// ---- draft editing + save ----------------------------------------------

const draft = reactive<Record<string, any>>({})
const snapshot = ref('')
const saveError = ref<string | null>(null)

function emptyValueFor(kind: string): unknown {
  if (kind === 'boolean') return false
  if (kind === 'number') return null
  if (kind === 'multi_select') return []
  if (kind === 'single_select') return null
  return ''
}

function isEmptyValue(value: unknown): boolean {
  if (value === undefined || value === null || value === '') return true
  return Array.isArray(value) && value.length === 0
}

/** Fill the draft from stored bindings; objects become JSON text, multi-select arrays stay arrays. */
function fillDraftFrom(
  stored: Record<string, any> | undefined,
  portList: LoosePort[],
  kindOf: (port: LoosePort) => string,
) {
  for (const port of portList) {
    let value = stored ? stored[port.name] : undefined
    if (value === undefined || value === null) {
      value = emptyValueFor(kindOf(port))
    } else if (typeof value === 'object') {
      value = Array.isArray(value) ? [...value] : JSON.stringify(value, null, 2)
    }
    draft[port.name] = value
  }
}

/** Snapshot shape includes the operation selection so op changes flip dirty. */
function snapshotShape(): string {
  return JSON.stringify({ op: isOperationMode.value ? selectedOperation.value : null, draft })
}

/** Reload the draft whenever another node is selected. */
function resetDraft() {
  for (const key of Object.keys(draft)) delete draft[key]
  saveError.value = null
  const data = nodeData.value
  const storedOp = typeof data.operation === 'string' && data.operation ? data.operation : null
  selectedOperation.value = isOperationMode.value ? storedOp : null
  if (isOperationMode.value && currentOperation.value) {
    fillDraftFrom(data.inputs as Record<string, any> | undefined, operationInputPorts.value, portKindOf)
  } else if (!isOperationMode.value) {
    fillDraftFrom(data.params as Record<string, any> | undefined, inputPorts.value, portTypeOf)
  }
  // Stored op the tool no longer declares: selector shows it, draft empty.
  snapshot.value = snapshotShape()
}

watch(() => props.node?.id, resetDraft, { immediate: true })

const dirty = computed(() => snapshotShape() !== snapshot.value)

/** User picked/cleared an operation in the selector. */
function onOperationChange(name: string | null) {
  selectedOperation.value = name
  for (const key of Object.keys(draft)) delete draft[key]
  saveError.value = null
  if (currentOperation.value) {
    const data = nodeData.value
    // Restoring the already-saved operation reloads its saved bindings.
    const stored = data.operation === name ? (data.inputs as Record<string, any> | undefined) : undefined
    fillDraftFrom(stored, operationInputPorts.value, portKindOf)
  }
}

/** Commit the draft into node.data (operation mode or legacy params). */
function save() {
  const node = props.node
  if (!node || !dirty.value) return
  const data = node.data as ToolNodeData
  if (isOperationMode.value) {
    saveOperation(data)
  } else {
    saveLegacy(data)
  }
}

function saveLegacy(data: ToolNodeData) {
  const params: Record<string, unknown> = {}
  for (const port of inputPorts.value) {
    const value = draft[port.name]
    // Skip empty values so unset params stay absent in the workflow JSON.
    if (value === undefined || value === null || value === '') continue
    params[port.name] = value
  }
  data.params = params
  // Operation state is mutually exclusive with legacy params; drop leftovers
  // (e.g. a transient metadata-fetch failure fell back to the legacy UI).
  delete data.operation
  delete data.inputs
  saveError.value = null
  snapshot.value = snapshotShape()
}

function saveOperation(data: ToolNodeData) {
  const op = selectedOperation.value
  if (!op) {
    saveError.value = t('workflow.editor.config.errors.noOperation')
    return
  }
  const missing: string[] = []
  for (const port of operationInputPorts.value) {
    const kind = portKindOf(port)
    const isSelect = kind === 'single_select' || kind === 'multi_select'
    if (isSelect && isRequired(port) && selectOptions(port).length === 0) {
      saveError.value = t('workflow.editor.config.errors.noOptions', { name: port.name })
      return
    }
    if (!isRequired(port)) continue
    // boolean is always satisfiable (false is a valid bound value).
    if (kind === 'boolean') continue
    if (isEmptyValue(draft[port.name])) missing.push(port.name)
  }
  if (missing.length > 0) {
    saveError.value = t('workflow.editor.config.errors.missingRequired', { names: missing.join(', ') })
    return
  }
  const inputs: Record<string, unknown> = {}
  for (const port of operationInputPorts.value) {
    const value = draft[port.name]
    // Skip empty values so unset inputs stay absent in the workflow JSON.
    if (isEmptyValue(value)) continue
    inputs[port.name] = value
  }
  data.operation = op
  data.inputs = inputs
  delete data.params
  saveError.value = null
  snapshot.value = snapshotShape()
}

// ---- native path pickers -------------------------------------------------

async function browsePath(port: LoosePort) {
  const isDir = portTypeOf(port) === 'directory'
  try {
    const svc = (await serviceManager.getService('system')) as any
    const res = isDir
      ? await svc.selectDirectory({ title: `Select ${port.name}` })
      : await svc.selectFile({ title: `Select ${port.name}` })
    if (res && !res.canceled) {
      const p = (res.filePath || (res.filePaths && res.filePaths[0]) || '').trim()
      if (p) draft[port.name] = p
    }
  } catch (error) {
    log.error('NodeConfigPanel: path picker failed', error)
  }
}
</script>

<style scoped>
.node-config-panel {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  background: var(--config-panel-bg);
}

.npc-empty {
  padding: 12px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.npc-identity {
  padding: 12px;
  border-bottom: 1px solid var(--node-border);
}

.npc-tool-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
  word-break: break-all;
}

.npc-tool-desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--app-text-secondary);
}

.npc-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  padding: 12px;
  overflow-y: auto;
}

.npc-section-title {
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--app-text-secondary);
  text-transform: uppercase;
}

.npc-empty-inline {
  font-size: 12px;
  color: var(--app-text-muted);
}

.npc-op-desc {
  margin-top: 6px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--app-text-dim);
}

.npc-path-row {
  display: flex;
  gap: 6px;
  width: 100%;
}

.npc-path-input {
  flex: 1;
  min-width: 0;
}

.npc-full {
  width: 100%;
}

.npc-mono :deep(.n-input__textarea-el) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
}

.npc-port-desc {
  font-size: 11px;
  color: var(--app-text-dim);
}

.npc-outputs {
  display: flex;
  flex-direction: column;
}

.npc-output-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
}

.npc-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--app-text-muted);
}

.npc-dot--file {
  background: var(--app-blue);
}

.npc-dot--text {
  background: var(--app-green);
}

.npc-dot--json {
  /* --app-orange added alongside todo 34's port palette; yellow fallback */
  background: var(--app-orange, var(--app-yellow));
}

.npc-dot--number {
  /* --app-purple added alongside todo 34's port palette; muted fallback */
  background: var(--app-purple, var(--app-text-muted));
}

.npc-output-name {
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  color: var(--app-text-primary);
}

.npc-output-type {
  margin-left: auto;
  font-size: 11px;
  color: var(--app-text-muted);
}

.npc-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--node-border);
}

.npc-error {
  flex: 1;
  margin-right: auto;
  font-size: 12px;
  line-height: 1.4;
  color: var(--app-red);
}
</style>
