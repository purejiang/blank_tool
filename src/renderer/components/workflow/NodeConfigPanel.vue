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
        <!-- 基本: node identity (the id is what $nodes.<id> bindings embed) -->
        <div class="npc-section">
          <div class="npc-section-title">{{ t('workflow.editor.config.sections.basic') }}</div>
          <div class="npc-field">
            <label class="npc-field-label" :title="t('workflow.editor.config.fields.idHint')">
              {{ t('workflow.editor.config.fields.id') }}
            </label>
            <n-input
              v-model:value="draftId"
              size="small"
              data-test="npc-id"
              @update:value="saveError = null"
            />
          </div>
        </div>

        <!-- 功能: what the node does (tool + operation) -->
        <div class="npc-section">
          <div class="npc-section-title">{{ t('workflow.editor.config.sections.capability') }}</div>
          <div v-if="isOperationMode" class="npc-field">
            <label class="npc-field-label">{{ t('workflow.editor.config.operation') }}</label>
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
          <div v-else class="npc-empty-inline">{{ toolName }}</div>
        </div>

        <!-- 参数: typed bindings for the effective input ports -->
        <div class="npc-section">
          <div class="npc-section-title">{{ t('workflow.editor.config.parameters') }}</div>
          <div v-if="isOperationMode && !selectedOperation" class="npc-empty-inline">
            {{ t('workflow.editor.config.operationPlaceholder') }}
          </div>
          <div v-else-if="effectiveInputs.length === 0" class="npc-empty-inline">
            {{ t('workflow.editor.config.noParameters') }}
          </div>
          <n-form v-else :model="draft" label-placement="top" size="small">
            <n-form-item
              v-for="port in effectiveInputs"
              :key="port.name"
              :label="port.name"
              :required="isRequired(port)"
            >
              <PortInput
                :value="draft[port.name]"
                :port="port"
                :inputs="workflowInputs"
                :upstream-nodes="upstreamNodes"
                @update:value="(value: any) => (draft[port.name] = value)"
              />
              <template v-if="port.description" #feedback>
                <span class="npc-port-desc">{{ port.description }}</span>
              </template>
            </n-form-item>
          </n-form>
        </div>

        <!-- 输出: read-only, so authors can reference them downstream -->
        <div class="npc-section">
          <div class="npc-section-title">{{ t('workflow.editor.config.sections.outputs') }}</div>
          <div v-if="effectiveOutputs.length === 0" class="npc-empty-inline">
            {{ t('workflow.editor.config.noOutputs') }}
          </div>
          <div v-else class="npc-outputs">
            <div
              v-for="port in effectiveOutputs"
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

        <!-- 行为: failure handling (配置, distinct from 功能/参数) -->
        <div class="npc-section">
          <div class="npc-section-title">{{ t('workflow.editor.config.sections.behavior') }}</div>
          <div class="npc-field">
            <label class="npc-field-label">{{ t('workflow.editor.config.fields.onFailure') }}</label>
            <n-select v-model:value="draftOnFailure" size="small" :options="failureOptions" />
          </div>
          <div class="npc-field" :title="t('workflow.editor.config.fields.retryHint')">
            <label class="npc-field-label">{{ t('workflow.editor.config.fields.retry') }}</label>
            <n-input-number
              v-model:value="draftRetry"
              class="npc-full"
              size="small"
              :min="0"
              :show-button="false"
            />
          </div>
          <div class="npc-hint">{{ t('workflow.editor.config.fields.retryHint') }}</div>
        </div>
      </div>

      <!-- Commit draft values to node.data (params or operation/inputs) -->
      <div class="npc-footer">
        <div v-if="saveError" class="npc-error">{{ saveError }}</div>
        <n-button size="small" type="error" quaternary data-test="npc-delete" @click="requestDelete">
          {{ t('workflow.editor.config.delete') }}
        </n-button>
        <n-button size="small" type="primary" :disabled="!dirty" data-test="npc-save" @click="save">
          {{ t('workflow.editor.config.save') }}
        </n-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NForm, NFormItem, NInput, NInputNumber, NButton, NSelect } from 'naive-ui'
import type { Node } from '@vue-flow/core'
import unifiedApi from '../../api/unifiedApi'
import { log } from '@utils/logger'
import PortInput from './PortInput.vue'
import { portJsonToTypeKey, type PortTypeKey } from './ioAuthoring'
import type { ToolNodeData, ToolOperation, ToolPorts, UpstreamNodeRef, WorkflowToolInfo } from './toolMeta'
import type { PortJSON } from './serializer'

const { t } = useI18n()

/**
 * Loose port shape accepted by this panel. `ToolPort` (toolMeta.ts) is
 * structurally assignable; the looser form also tolerates bare base-name type
 * strings or missing fields (e.g. nodes rebuilt by the deserializer).
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
  /** Workflow-level inputs, offered as `$inputs.<key>` binding candidates. */
  workflowInputs?: PortJSON[]
  /** Nodes that run before this one, offered as `$nodes.<id>.*` candidates. */
  upstreamNodes?: UpstreamNodeRef[]
  /** Every node id on the canvas (node-id uniqueness validation). */
  nodeIds?: string[]
}>()

const emit = defineEmits<{
  (e: 'delete', nodeId: string): void
  (e: 'rename', payload: { oldId: string; newId: string }): void
}>()

// ---- node data accessors ---------------------------------------------
// Node payload contract is toolMeta.ts `ToolNodeData`:
//   { tool, status?, ports?: { inputs, outputs }, params? (legacy mode),
//     operation?, inputs? (operation mode, T7), on_failure?, retry? }

const nodeData = computed<Record<string, any>>(() => (props.node?.data ?? {}) as Record<string, any>)

const toolName = computed<string>(() => {
  const d = nodeData.value
  return String(d.tool || d.toolName || d.label || props.node?.id || '')
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

/** Prefer nested data.ports; tolerate flat data.inputs/outputs. */
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
// The panel fetches workflow.list_tools independently so it stays
// self-contained (no parent prop). On failure it degrades to the legacy
// free-form params UI.

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
const operationOutputPorts = computed<LoosePort[]>(() => toPorts(currentOperation.value?.outputs))

/** Inputs the parameters section edits: operation inputs, else tool inputs. */
const effectiveInputs = computed<LoosePort[]>(() =>
  isOperationMode.value ? operationInputPorts.value : inputPorts.value,
)

/** Outputs shown read-only: operation outputs when one is selected. */
const effectiveOutputs = computed<LoosePort[]>(() =>
  isOperationMode.value && currentOperation.value ? operationOutputPorts.value : outputPorts.value,
)

function selectOptions(port: LoosePort) {
  const options = Array.isArray(port.options) ? port.options : []
  return options.map((value) => ({ label: String(value), value: String(value) }))
}

// ---- port type helpers -------------------------------------------------

const KNOWN_BASE_TYPES = ['file', 'directory', 'text', 'number', 'boolean', 'json']

function portTypeOf(port: LoosePort): string {
  const raw = port.type
  let base = ''
  if (typeof raw === 'string') base = raw
  else if (raw && typeof raw === 'object' && typeof raw.base === 'string') base = raw.base
  base = base.toLowerCase()
  // Unknown/missing types degrade to a plain text field (advisory typing, D7).
  return KNOWN_BASE_TYPES.includes(base) ? base : 'text'
}

/**
 * Widget kind for an input port — reuses the T6 reverse mapping:
 * text base + options (+multi) → single_select / multi_select; bare bases
 * map 1:1; unknown degrades to text.
 */
function portKindOf(port: LoosePort): PortTypeKey {
  return portJsonToTypeKey({
    name: port.name,
    type: { base: portTypeOf(port) },
    options: Array.isArray(port.options) ? (port.options as string[]) : [],
    multi: port.multi === true,
  })
}

function typeLabel(port: LoosePort): string {
  const base = portTypeOf(port)
  const raw = port.type
  if (raw && typeof raw === 'object' && typeof raw.subtype === 'string' && raw.subtype) {
    return `${base}/${raw.subtype}`
  }
  return base
}

function isRequired(port: LoosePort): boolean {
  // Backend Port defaults to required=True when the flag is absent.
  return port.required !== false
}

// ---- draft editing + save ----------------------------------------------

const draft = reactive<Record<string, any>>({})
const draftId = ref('')
const draftOnFailure = ref<'fail' | 'skip'>('fail')
const draftRetry = ref<number>(0)
const snapshot = ref('')
const saveError = ref<string | null>(null)

const failureOptions = computed(() => [
  { label: t('workflow.editor.config.onFailure.fail'), value: 'fail' },
  { label: t('workflow.editor.config.onFailure.skip'), value: 'skip' },
])

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

/** Snapshot shape includes every editable field so any change flips dirty. */
function snapshotShape(): string {
  return JSON.stringify({
    id: draftId.value,
    op: isOperationMode.value ? selectedOperation.value : null,
    onFailure: draftOnFailure.value,
    retry: draftRetry.value,
    draft,
  })
}

/** Reload the draft whenever another node is selected. */
function resetDraft() {
  for (const key of Object.keys(draft)) delete draft[key]
  saveError.value = null
  const data = nodeData.value
  draftId.value = String(props.node?.id ?? '')
  draftOnFailure.value = data.on_failure === 'skip' ? 'skip' : 'fail'
  draftRetry.value = typeof data.retry === 'number' && data.retry > 0 ? data.retry : 0
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
// The tool list arrives asynchronously and can flip operation mode.
watch(operations, resetDraft)

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

/** Node-id validation (empty / duplicate / contains the reference separator). */
function validateId(): string | null {
  const id = draftId.value.trim()
  if (!id) return t('workflow.editor.config.errors.idRequired')
  if (id.includes('.')) return t('workflow.editor.config.errors.idDot')
  const siblings = props.nodeIds ?? []
  if (id !== props.node?.id && siblings.includes(id)) {
    return t('workflow.editor.config.errors.idDuplicate', { id })
  }
  return null
}

/** Commit the draft into node.data (operation mode or legacy params). */
function save() {
  const node = props.node
  if (!node || !dirty.value) return

  const idError = validateId()
  if (idError) {
    saveError.value = idError
    return
  }

  const data = node.data as ToolNodeData
  if (isOperationMode.value) {
    if (!saveOperation(data)) return
  } else {
    saveLegacy(data)
  }

  data.on_failure = draftOnFailure.value
  data.retry = draftRetry.value > 0 ? draftRetry.value : 0
  saveError.value = null
  snapshot.value = snapshotShape()

  const newId = draftId.value.trim()
  if (newId && newId !== node.id) emit('rename', { oldId: node.id, newId })
}

/** @returns false when the draft could not be committed (error already set). */
function saveLegacy(data: ToolNodeData): boolean {
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
  return true
}

/** @returns false when the draft could not be committed (error already set). */
function saveOperation(data: ToolNodeData): boolean {
  const op = selectedOperation.value
  if (!op) {
    saveError.value = t('workflow.editor.config.errors.noOperation')
    return false
  }
  const missing: string[] = []
  for (const port of operationInputPorts.value) {
    const kind = portKindOf(port)
    const isSelect = kind === 'single_select' || kind === 'multi_select'
    if (isSelect && isRequired(port) && selectOptions(port).length === 0) {
      saveError.value = t('workflow.editor.config.errors.noOptions', { name: port.name })
      return false
    }
    if (!isRequired(port)) continue
    // boolean is always satisfiable (false is a valid bound value).
    if (kind === 'boolean') continue
    if (isEmptyValue(draft[port.name])) missing.push(port.name)
  }
  if (missing.length > 0) {
    saveError.value = t('workflow.editor.config.errors.missingRequired', { names: missing.join(', ') })
    return false
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
  return true
}

/** Deletion goes through the page, which owns the confirmation dialog. */
function requestDelete() {
  if (props.node) emit('delete', props.node.id)
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
  gap: 14px;
  min-height: 0;
  padding: 12px;
  overflow-y: auto;
}

/* Section boxes: 功能 / 参数 / 配置 视觉分区 */
.npc-section {
  padding: 10px 10px 12px;
  background: var(--app-input-bg, transparent);
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-control);
}

.npc-section-title {
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--app-text-secondary);
  text-transform: uppercase;
}

.npc-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.npc-field-label {
  font-size: 12px;
  color: var(--app-text-secondary);
}

.npc-hint {
  font-size: 11px;
  line-height: 1.45;
  color: var(--app-text-dim);
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

.npc-full {
  width: 100%;
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
  background: var(--app-orange, var(--app-yellow));
}

.npc-dot--number {
  background: var(--app-purple, var(--app-text-muted));
}

.npc-output-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
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
