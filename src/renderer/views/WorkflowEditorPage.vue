<template>
  <div class="workflow-editor-page">
    <!-- Left panel: tool palette (todo 34) -->
    <WorkflowNodePalette />

    <!-- Center: toolbar + execution banner + vue-flow canvas -->
    <div class="we-center">
      <div class="we-toolbar">
        <span class="we-title" :title="meta.name">{{ meta.name }}</span>
        <!-- Template save/load/delete (todo 39) -->
        <TemplateManager :get-definition="serializeCanvas" @load="onTemplateLoad" />
        <!-- Workflow-level inputs/outputs authoring (T6) -->
        <n-button size="small" @click="showIoPanel = true">
          {{ t('workflow.editor.io.title') }}
        </n-button>
        <n-button
          size="small"
          type="primary"
          :loading="isRunning"
          :disabled="isRunning || nodes.length === 0"
          @click="onRunClick"
        >
          Run
        </n-button>
      </div>

      <!-- Terminal execution result banner (todo 38); closable, persists until next Run -->
      <n-alert
        v-if="banner"
        class="we-banner"
        :type="banner.type"
        closable
        @close="banner = null"
      >
        {{ banner.text }}
      </n-alert>

      <main class="we-canvas" @dragover="onDragOver" @drop="onDrop">
        <VueFlow
          :node-types="nodeTypes"
          :min-zoom="0.2"
          :max-zoom="4"
          @connect="onConnect"
          @connect-start="onConnectStart"
          @connect-end="onConnectEnd"
        >
          <Background />
          <Controls />
          <MiniMap />
        </VueFlow>
        <div v-if="nodes.length === 0" class="we-empty-hint">
          Empty workflow — drag a tool from the palette to get started
        </div>
      </main>
    </div>

    <!-- Right panel: node config (todo 36), shown while a node is selected -->
    <aside v-if="selectedNode" class="we-panel we-config">
      <div class="we-panel-header">Node Config</div>
      <NodeConfigPanel :node="selectedNode" />
    </aside>

    <!-- Inputs dialog (todo 38): one field per declared workflow-level input -->
    <n-modal
      v-model:show="showInputsDialog"
      preset="card"
      title="Workflow inputs"
      :style="{ width: '440px' }"
      :mask-closable="false"
    >
      <n-form
        v-if="declaredInputs.length > 0"
        :model="inputDraft"
        label-placement="top"
        size="small"
      >
        <n-form-item
          v-for="port in declaredInputs"
          :key="port.name"
          :label="port.name"
          :required="port.required !== false"
        >
          <!-- file / directory: text input + native picker button -->
          <div v-if="isPathInput(port)" class="we-path-row">
            <n-input
              v-model:value="inputDraft[port.name]"
              class="we-path-input"
              size="small"
              :placeholder="portBase(port) === 'directory' ? '/path/to/folder' : '/path/to/file'"
            />
            <n-button size="small" @click="browseInput(port)">Browse</n-button>
          </div>
          <!-- boolean -->
          <n-switch
            v-else-if="portBase(port) === 'boolean'"
            v-model:value="inputDraft[port.name]"
          />
          <!-- number -->
          <n-input-number
            v-else-if="portBase(port) === 'number'"
            v-model:value="inputDraft[port.name]"
            class="we-full"
            size="small"
            :show-button="false"
            placeholder="0"
          />
          <!-- json: monospace textarea -->
          <n-input
            v-else-if="portBase(port) === 'json'"
            v-model:value="inputDraft[port.name]"
            class="we-mono"
            size="small"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            placeholder='{ "key": "value" }'
          />
          <!-- text / unknown: plain textarea -->
          <n-input
            v-else
            v-model:value="inputDraft[port.name]"
            size="small"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
          />
          <template v-if="port.description" #feedback>
            <span class="we-port-desc">{{ port.description }}</span>
          </template>
        </n-form-item>
      </n-form>
      <div v-else class="we-no-inputs">This workflow declares no inputs — run it as-is.</div>
      <template #footer>
        <div class="we-modal-footer">
          <n-button size="small" @click="showInputsDialog = false">Cancel</n-button>
          <n-button size="small" type="primary" @click="onInputsSubmit">Run</n-button>
        </div>
      </template>
    </n-modal>

    <!-- Workflow-level inputs/outputs authoring modal (T6): edits
         meta.inputs / meta.outputs so serializeCanvas carries them to
         template.save. Pure authoring rules live in ioAuthoring.ts. -->
    <IoAuthoringPanel v-model:show="showIoPanel" v-model:meta="meta" />
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  VueFlow,
  useVueFlow,
  type Connection,
  type Edge,
  type Node,
  type OnConnectStartParams,
} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import {
  NAlert,
  NButton,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NSwitch,
  useMessage,
} from 'naive-ui'

import ToolNode from '@components/workflow/ToolNode.vue'
import WorkflowNodePalette from '@components/workflow/WorkflowNodePalette.vue'
import NodeConfigPanel from '@components/workflow/NodeConfigPanel.vue'
import IoAuthoringPanel from '@components/workflow/IoAuthoringPanel.vue'
import TemplateManager, { type TemplateLoadPayload } from '@components/workflow/TemplateManager.vue'
import {
  TOOL_DRAG_MIME,
  type ToolNodeData,
  type ToolPort,
  type ToolPorts,
  type ToolStatus,
  type WorkflowToolInfo,
} from '@components/workflow/toolMeta'
import {
  serializeWorkflow,
  type PortJSON,
  type WorkflowDefinitionJSON,
  type WorkflowMeta,
} from '@components/workflow/serializer'
import {
  CONNECTION_DRAG_KEY,
  isBaseType,
  validateConnection,
  type ConnectionDragInfo,
} from '@components/workflow/PortConnection'
import serviceManager from '@services/ServiceManager'
import unifiedApi from '@/api/unifiedApi'
import { log } from '@utils/logger'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

// Custom node registration: node `type: "tool"` renders ToolNode.
// markRaw keeps the component out of Vue's reactivity system (vue-flow
// warns about reactive node-types objects).
const nodeTypes = {
  tool: markRaw(ToolNode),
}

// Shared store: created here, injected by the <VueFlow> child component.
// screenToFlowCoordinate/addNodes come from the store's viewport actions
// and are used by the palette drop handler below; setNodes/setEdges/fitView
// by the template-load handler (todo 39).
const {
  nodes,
  edges,
  addNodes,
  addEdges,
  screenToFlowCoordinate,
  findNode,
  updateNodeData,
  onNodesChange,
  onEdgesChange,
  setNodes,
  setEdges,
  fitView,
} = useVueFlow({
  nodes: [] as Node[],
  edges: [] as Edge[],
})

const message = useMessage()
const { t } = useI18n()

// Live connection-drag state (todo 35): provided here, injected by ToolNode
// to highlight compatible handles and dim incompatible ones mid-drag.
const connectionDrag = ref<ConnectionDragInfo | null>(null)
provide(CONNECTION_DRAG_KEY, connectionDrag)

/** Resolve a port on a node by handle id (handle id == port name, todo 34). */
function findPort(nodeId: string, handleId: string | null | undefined, side: 'inputs' | 'outputs'): ToolPort | undefined {
  if (!handleId) return undefined
  const node = findNode(nodeId)
  if (!node) return undefined
  const data = node.data as ToolNodeData | undefined
  return data?.ports?.[side]?.find((p) => p.name === handleId)
}

/**
 * Connection validation (todo 35): base types must match (D7 — subtype is
 * advisory and never enforced). Valid drops become edges; incompatible ones
 * are rejected with a toast instead.
 */
function onConnect(connection: Connection) {
  const sourcePort = findPort(connection.source, connection.sourceHandle, 'outputs')
  const targetPort = findPort(connection.target, connection.targetHandle, 'inputs')
  const result = validateConnection(
    { nodeId: connection.source, portName: connection.sourceHandle ?? '', portType: sourcePort?.type },
    { nodeId: connection.target, portName: connection.targetHandle ?? '', portType: targetPort?.type },
  )
  if (!result.valid) {
    message.error(result.reason ?? 'Connection rejected')
    return
  }
  // addEdges generates the edge id and silently skips duplicate connections
  // (same source/target/handles), so no bookkeeping is needed here.
  addEdges(connection)
}

function onConnectStart(params: OnConnectStartParams) {
  connectionDrag.value = null
  if (!params.nodeId || !params.handleId || !params.handleType) return
  const side = params.handleType === 'source' ? 'outputs' : 'inputs'
  const base = findPort(params.nodeId, params.handleId, side)?.type.base
  if (isBaseType(base)) {
    connectionDrag.value = { base, fromHandleType: params.handleType }
  }
}

function onConnectEnd() {
  connectionDrag.value = null
}

// Workflow-level metadata supplied to the serializer. Updated from loaded
// templates (todo 39 onTemplateLoad); the inputs dialog below reads
// `meta.inputs`.
const meta = ref<WorkflowMeta>({
  name: 'Untitled workflow',
  version: '1.0',
  description: '',
  inputs: [],
  outputs: [],
})

// Open/close state of the workflow-level inputs/outputs authoring modal (T6).
const showIoPanel = ref(false)

// Monotonic counter keeps dropped node ids unique within the session.
let nodeCounter = 0

function makeNodeId(toolName: string): string {
  nodeCounter += 1
  return `tool-${toolName.replace(/[^a-z0-9]+/gi, '-')}-${nodeCounter}`
}

function onDragOver(event: DragEvent) {
  // Required so the canvas accepts the drop; restrict to palette tool drags.
  if (!event.dataTransfer?.types.includes(TOOL_DRAG_MIME)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
}

function onDrop(event: DragEvent) {
  event.preventDefault()
  const raw = event.dataTransfer?.getData(TOOL_DRAG_MIME)
  if (!raw) return

  let tool: WorkflowToolInfo
  try {
    tool = JSON.parse(raw)
  } catch {
    return
  }
  if (!tool || typeof tool.name !== 'string' || tool.name.length === 0) return

  const position = screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
  const data: ToolNodeData = {
    tool: tool.name,
    status: 'idle',
    ports: tool.ports,
  }
  addNodes({
    id: makeNodeId(tool.name),
    type: 'tool',
    position,
    data,
  })
}

// Right panel shows the config form for the selected node (todo 36).
// vue-flow's built-in selection sets node.selected on click (elementsSelectable
// defaults true); pane-click / Escape clear it — deriving from `nodes` means the
// panel hides automatically on deselect with no extra event wiring.
const selectedNode = computed(() => nodes.value.find((n) => n.selected) ?? null)

// ---------------------------------------------------------------------------
// Template management (todo 39) — TemplateManager owns the dialogs + IPC;
// the page supplies the serialized canvas and applies loaded definitions.
// ---------------------------------------------------------------------------

/**
 * Snapshot of the canvas for TemplateManager's save flow. Null = empty canvas
 * (TemplateManager shows a "nothing to save" toast). TemplateManager overrides
 * the definition's name/description with its dialog values before template.save.
 */
function serializeCanvas(): WorkflowDefinitionJSON | null {
  if (nodes.value.length === 0) return null
  return serializeWorkflow(nodes.value, edges.value, meta.value)
}

// Cached tool-name → ports map, used to hydrate loaded templates into
// ToolNode shape (see onTemplateLoad). Populated lazily on first load;
// successes are cached, failures are not (the next load retries the fetch).
let toolPortsCache: Record<string, ToolPorts> | null = null

async function fetchToolPorts(): Promise<Record<string, ToolPorts>> {
  if (toolPortsCache) return toolPortsCache
  try {
    const result = await unifiedApi.call<{ tools?: WorkflowToolInfo[] }>('workflow.list_tools', {})
    const map: Record<string, ToolPorts> = {}
    for (const tool of result?.tools ?? []) {
      if (tool?.name && tool.ports) map[tool.name] = tool.ports
    }
    toolPortsCache = map
    return map
  } catch (err) {
    // Degrade gracefully: nodes still load, rendered header-only (no ports).
    log.warn('[WorkflowEditorPage] workflow.list_tools unavailable, loaded nodes will render without ports', err)
    return {}
  }
}

/**
 * Apply a loaded template to the canvas. The serializer (todo 37) emits
 * generic `type: 'default'` nodes with `{tool, params, label}` data; that is
 * hydrated into ToolNode shape here (type 'tool', status 'idle', ports from
 * workflow.list_tools — the known-limitation hydration todo 36 deferred to
 * the template-load flow) before replacing the whole canvas state. The loaded
 * meta becomes the page meta (title + Run-dialog inputs, todo 38).
 */
async function onTemplateLoad(payload: TemplateLoadPayload) {
  const portsByTool = await fetchToolPorts()
  const hydrated: Node[] = payload.nodes.map((node) => ({
    ...node,
    type: 'tool',
    data: {
      ...node.data,
      status: 'idle',
      ports: portsByTool[node.data.tool],
    },
  }))
  setNodes(hydrated)
  setEdges(payload.edges)
  meta.value = { ...payload.meta }
  banner.value = null // stale run feedback belongs to the previous canvas
  await nextTick()
  await fitView({ padding: 0.2 })
}

// ---------------------------------------------------------------------------
// Execution (todo 38): Run button → inputs dialog → workflow.execute → stream
// events drive node status colors and the terminal banner.
// ---------------------------------------------------------------------------

/** Event types emitted by the workflow engine (backend/app/workflow/streaming.py). */
const WORKFLOW_EVENT_TYPES = new Set([
  'node_started',
  'node_output',
  'node_completed',
  'node_failed',
  'workflow_completed',
  'workflow_failed',
  'workflow_cancelled',
])

interface ExecutionBanner {
  type: 'success' | 'error' | 'warning' | 'info'
  text: string
}

const isRunning = ref(false)
const banner = ref<ExecutionBanner | null>(null)
const showInputsDialog = ref(false)
const pendingDefinition = ref<WorkflowDefinitionJSON | null>(null)
const inputDraft = reactive<Record<string, any>>({})

// Workflow id (task_id) of the currently/last started run; stream events are
// correlated back to this page via their `workflow_id` field.
let activeWorkflowId: string | null = null
let unsubscribeStream: (() => void) | null = null

function makeWorkflowRunId(): string {
  return `wf-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

/** Declared workflow-level inputs of the serialized definition (for the dialog). */
const declaredInputs = computed<PortJSON[]>(() => {
  const raw = pendingDefinition.value?.inputs
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (p): p is PortJSON => !!p && typeof p === 'object' && typeof p.name === 'string',
  )
})

// ---- port type helpers (mirror NodeConfigPanel, todo 36) -------------------

const KNOWN_INPUT_BASES = ['file', 'directory', 'text', 'number', 'boolean', 'json']

function portBase(port: PortJSON): string {
  const base = String(port.type?.base ?? '').toLowerCase()
  // Unknown/missing types degrade to a plain text field (advisory typing).
  return KNOWN_INPUT_BASES.includes(base) ? base : 'text'
}

function isPathInput(port: PortJSON): boolean {
  const base = portBase(port)
  return base === 'file' || base === 'directory'
}

// ---- Run flow ---------------------------------------------------------------

/** Run click: serialize the canvas, then open the inputs dialog. */
function onRunClick() {
  if (isRunning.value || nodes.value.length === 0) return
  banner.value = null
  pendingDefinition.value = serializeWorkflow(nodes.value, edges.value, meta.value)
  initInputDraft()
  showInputsDialog.value = true
}

function initInputDraft() {
  for (const key of Object.keys(inputDraft)) delete inputDraft[key]
  for (const port of declaredInputs.value) {
    const base = portBase(port)
    inputDraft[port.name] = base === 'boolean' ? false : base === 'number' ? null : ''
  }
}

/** Dialog submit: collect values, validate required inputs, start execution. */
function onInputsSubmit() {
  const definition = pendingDefinition.value
  if (!definition) return

  const inputs: Record<string, unknown> = {}
  for (const port of declaredInputs.value) {
    let value = inputDraft[port.name]
    if (value === undefined || value === null || value === '') {
      if (port.required !== false) {
        message.error(`Missing required input: ${port.name}`)
        return
      }
      continue // empty optional inputs stay absent, like NodeConfigPanel params
    }
    if (portBase(port) === 'json' && typeof value === 'string') {
      try {
        value = JSON.parse(value)
      } catch {
        message.error(`Input '${port.name}' is not valid JSON`)
        return
      }
    }
    inputs[port.name] = value
  }

  showInputsDialog.value = false
  startExecution(definition, inputs)
}

async function startExecution(
  definition: WorkflowDefinitionJSON,
  inputs: Record<string, unknown>,
) {
  activeWorkflowId = makeWorkflowRunId()
  isRunning.value = true
  banner.value = null
  resetAllNodeStatuses()

  try {
    // workflow.execute is @streaming: the main process resolves this invoke on
    // the FIRST streamed event (src/main/ipc/commandHandlers.ts), so awaiting
    // here only surfaces startup failures (malformed definition, backend down).
    // The terminal state arrives over the stream-event channel instead
    // (workflow_completed / workflow_failed), handled in handleStreamRaw.
    await window.electronAPI.callBackendAPI('workflow.execute', {
      definition,
      inputs,
      task_id: activeWorkflowId,
    })
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error)
    isRunning.value = false
    banner.value = { type: 'error', text: `Execution failed to start: ${text}` }
    log.error('[WorkflowEditorPage] workflow.execute rejected:', error)
  }
}

// ---- node status --------------------------------------------------------------

function setNodeStatus(nodeId: unknown, status: ToolStatus) {
  if (typeof nodeId !== 'string' || nodeId.length === 0) return
  if (!findNode(nodeId)) return // events may reference nodes deleted mid-run
  updateNodeData(nodeId, { status })
}

function resetAllNodeStatuses() {
  for (const node of nodes.value) {
    const data = (node.data ?? {}) as ToolNodeData
    if (data.status && data.status !== 'idle') {
      updateNodeData(node.id, { status: 'idle' })
    }
  }
}

// Status colors persist after a run finishes; once the graph structure changes
// they are stale, so clear them on add/remove (but never mid-run).
onNodesChange((changes) => {
  if (!isRunning.value && changes.some((c) => c.type === 'add' || c.type === 'remove')) {
    resetAllNodeStatuses()
  }
})
onEdgesChange((changes) => {
  if (!isRunning.value && changes.some((c) => c.type === 'add' || c.type === 'remove')) {
    resetAllNodeStatuses()
  }
})

// ---- stream-event routing ---------------------------------------------------

function handleStreamRaw(raw: unknown) {
  if (!raw || typeof raw !== 'object') return
  try {
    // Main forwards { stream_id, data: <event dict> } on the stream-event
    // channel; tolerate a bare event dict too (TaskStreamService convention).
    const envelope = raw as Record<string, any>
    const event = (
      envelope.data && typeof envelope.data === 'object' ? envelope.data : envelope
    ) as Record<string, any>

    const type = typeof event.type === 'string' ? event.type : ''
    if (!WORKFLOW_EVENT_TYPES.has(type)) return // logcat/download/etc. noise
    if (event.workflow_id !== activeWorkflowId) return // another run's events

    switch (type) {
      case 'node_started':
        setNodeStatus(event.node_id, 'running')
        break
      case 'node_completed':
        setNodeStatus(event.node_id, 'success')
        break
      case 'node_failed':
        setNodeStatus(event.node_id, 'error')
        message.error(
          `Node failed: ${typeof event.error === 'string' ? event.error : 'unknown error'}`,
        )
        break
      case 'workflow_completed':
        isRunning.value = false
        banner.value = { type: 'success', text: 'Workflow completed successfully' }
        break
      case 'workflow_failed':
        isRunning.value = false
        banner.value = {
          type: 'error',
          text: `Workflow failed: ${typeof event.error === 'string' ? event.error : 'unknown error'}`,
        }
        break
      case 'workflow_cancelled':
        isRunning.value = false
        resetAllNodeStatuses()
        banner.value = { type: 'warning', text: 'Workflow cancelled' }
        break
      default:
        break // node_output: nothing to visualize in the MVP
    }
  } catch (err) {
    // Handler errors must never break event routing.
    log.error('[WorkflowEditorPage] stream event handling error:', err)
  }
}

// Subscribe to the shared stream-event channel (same pattern as
// TaskStreamService.initialize); unsubscribe on page teardown.
onMounted(() => {
  const api = window.electronAPI
  if (api && typeof api.onStreamEvent === 'function') {
    unsubscribeStream = api.onStreamEvent((raw: any) => handleStreamRaw(raw))
  } else {
    log.warn('[WorkflowEditorPage] onStreamEvent not available — execution events will not be received')
  }
})

onBeforeUnmount(() => {
  if (unsubscribeStream) {
    try {
      unsubscribeStream()
    } catch {}
    unsubscribeStream = null
  }
})

// ---- native path pickers for file/directory inputs ---------------------------

async function browseInput(port: PortJSON) {
  const isDir = portBase(port) === 'directory'
  try {
    const svc = (await serviceManager.getService('system')) as any
    const res = isDir
      ? await svc.selectDirectory({ title: `Select ${port.name}` })
      : await svc.selectFile({ title: `Select ${port.name}` })
    if (res && !res.canceled) {
      const p = (res.filePath || (res.filePaths && res.filePaths[0]) || '').trim()
      if (p) inputDraft[port.name] = p
    }
  } catch (error) {
    log.error('[WorkflowEditorPage] path picker failed', error)
  }
}
</script>

<style scoped>
.workflow-editor-page {
  display: flex;
  gap: 8px;
  height: 100%;
}

.we-panel {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: 220px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 6px;
}

.we-panel-header {
  padding: 10px 12px;
  border-bottom: 1px solid var(--app-card-border);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--app-text-secondary);
}

.we-placeholder {
  padding: 12px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.we-config {
  width: 300px;
}

.we-center {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.we-toolbar {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 6px;
}

.we-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-primary);
}

.we-banner {
  flex-shrink: 0;
}

.we-canvas {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 6px;
}

.we-empty-hint {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 1;
  transform: translate(-50%, -50%);
  pointer-events: none;
  font-size: 13px;
  color: var(--app-text-muted);
}

/* Inputs dialog (rendered via teleport; scoped attrs still apply) */
.we-full {
  width: 100%;
}

.we-path-row {
  display: flex;
  gap: 6px;
  width: 100%;
}

.we-path-input {
  flex: 1;
  min-width: 0;
}

.we-mono :deep(.n-input__textarea-el) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
}

.we-port-desc {
  font-size: 11px;
  color: var(--app-text-dim);
}

.we-no-inputs {
  padding: 4px 0;
  font-size: 12px;
  color: var(--app-text-muted);
}

.we-modal-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
