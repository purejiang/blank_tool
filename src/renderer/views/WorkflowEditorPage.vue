<template>
  <div class="screen editor workflow-editor-page">
    <!-- Left panel: tool palette -->
    <WorkflowNodePalette @append="onAppendTool" />

    <!-- Center: toolbar + banners + vue-flow canvas -->
    <div class="we-center">
      <div class="we-toolbar">
        <n-button size="small" quaternary :title="t('workflow.editor.back')" @click="goBack">
          <template #icon><n-icon size="15"><ArrowLeft /></n-icon></template>
        </n-button>
        <button type="button" class="we-title" :title="meta.name" @click="activeTab = 'workflow'">
          {{ meta.name || t('workflow.editor.title') }}
        </button>
        <span class="we-state" :class="`we-state--${runState}`">{{ stateLabel }}</span>
        <TemplateManager
          :get-definition="serializeCanvas"
          :blocked-reason="saveBlockedReason"
          :default-name="meta.name"
          :default-description="meta.description ?? ''"
          @load="onTemplateLoad"
          @saved="onTemplateSaved"
        />
        <n-button size="small" @click="openProblems">
          {{ t('workflow.editor.problems.button') }}
          <template v-if="problemCount >= 0">&nbsp;{{ problemCount }}</template>
        </n-button>
        <n-button
          v-if="!isRunning"
          size="small"
          type="primary"
          :disabled="nodes.length === 0"
          @click="onRunClick"
        >
          {{ t('workflow.editor.run') }}
        </n-button>
        <n-button v-else size="small" type="warning" @click="onCancelClick">
          {{ t('workflow.editor.cancel') }}
        </n-button>
      </div>

      <!-- Linear-model guard: extra outgoing edges cannot be saved -->
      <n-alert
        v-if="edgeConflicts.length > 0"
        class="we-banner"
        type="warning"
        :show-icon="true"
        data-test="edge-guard"
      >
        <div class="we-guard-title">
          {{ t('workflow.editor.guard.title', { count: edgeConflicts.length }) }}
        </div>
        <div class="we-guard-edges">
          <code v-for="conflict in edgeConflicts" :key="`${conflict.source}->${conflict.target}`">
            {{ conflict.source }} → {{ conflict.target }}
          </code>
        </div>
        <div class="we-guard-hint">{{ t('workflow.editor.guard.hint') }}</div>
      </n-alert>

      <!-- Terminal execution result banner; closable, persists until next Run -->
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
          :default-edge-options="defaultEdgeOptions"
          :fit-view-on-init="true"
          @connect="onConnect"
          @connect-start="onConnectStart"
          @connect-end="onConnectEnd"
        >
          <Background />
          <Controls />
          <MiniMap />
        </VueFlow>
        <div v-if="nodes.length === 0" class="we-empty-hint">
          {{ t('workflow.editor.emptyCanvas') }}
        </div>
      </main>
    </div>

    <!-- Right dock: always visible, 工作流 ｜ 节点 -->
    <aside class="we-dock">
      <div class="we-dock-tabs">
        <button
          type="button"
          class="we-dock-tab"
          :class="{ 'we-dock-tab--active': activeTab === 'workflow' }"
          @click="activeTab = 'workflow'"
        >
          {{ t('workflow.editor.dock.tabs.workflow') }}
        </button>
        <button
          type="button"
          class="we-dock-tab"
          :class="{ 'we-dock-tab--active': activeTab === 'node' }"
          @click="activeTab = 'node'"
        >
          {{ t('workflow.editor.dock.tabs.node') }}
        </button>
      </div>

      <div class="we-dock-body">
        <!-- 工作流: identity + workflow-level inputs/outputs -->
        <template v-if="activeTab === 'workflow'">
          <WorkflowInfoPanel
            :meta="meta"
            :node-count="nodes.length"
            :edge-count="edges.length"
            @update:meta="meta = $event"
          />
          <div class="we-dock-divider" />
          <IoAuthoringPanel :meta="meta" @update:meta="meta = $event" />
        </template>

        <!-- 节点: the selected node's configuration -->
        <template v-else>
          <NodeConfigPanel
            v-if="selectedNode"
            :node="selectedNode"
            :workflow-inputs="meta.inputs ?? []"
            :upstream-nodes="upstreamNodes"
            :node-ids="nodeIds"
            @delete="onDeleteNode"
            @rename="onRenameNode"
          />
          <div v-else class="we-dock-empty">{{ t('workflow.editor.config.noSelection') }}</div>
        </template>
      </div>
    </aside>

    <!-- Run dialog（M1 公共弹层）：工作流列表的「试运行」用同一个组件 -->
    <RunInputsDialog
      v-model:show="showInputsDialog"
      :definition="pendingDefinition"
      :loading="isRunning"
      @submit="onRunSubmit"
    />

    <!-- Static validation findings (workflow.validate) -->
    <n-modal
      v-model:show="showProblems"
      preset="card"
      :title="t('workflow.editor.problems.title')"
      :style="{ width: '520px' }"
    >
      <div v-if="problemsLoading" class="we-problems-status">…</div>
      <div v-else-if="problems.length === 0" class="we-problems-status">
        {{ t('workflow.editor.problems.empty') }}
      </div>
      <div v-else class="we-problems">
        <div
          v-for="(problem, index) in problems"
          :key="index"
          class="we-problem-row"
          :class="`we-problem-row--${problem.severity}`"
          @click="focusProblem(problem)"
        >
          <span class="we-problem-severity">
            {{
              problem.severity === 'error'
                ? t('workflow.editor.problems.error')
                : t('workflow.editor.problems.warning')
            }}
          </span>
          <span class="we-problem-node">{{ problem.node_id || '—' }}</span>
          <span class="we-problem-message">{{ problem.message }}</span>
        </div>
      </div>
      <template #footer>
        <div class="we-modal-footer">
          <n-button size="small" @click="openProblems">
            {{ t('workflow.editor.problems.refresh') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  MarkerType,
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
  NIcon,
  NModal,
  useDialog,
  useMessage,
} from 'naive-ui'
import { ArrowLeft } from 'lucide-vue-next'

import ToolNode from '@components/workflow/ToolNode.vue'
import WorkflowNodePalette from '@components/workflow/WorkflowNodePalette.vue'
import NodeConfigPanel from '@components/workflow/NodeConfigPanel.vue'
import IoAuthoringPanel from '@components/workflow/IoAuthoringPanel.vue'
import WorkflowInfoPanel from '@components/workflow/WorkflowInfoPanel.vue'
import RunInputsDialog from '@components/workflow/RunInputsDialog.vue'
import TemplateManager, { type TemplateLoadPayload } from '@components/workflow/TemplateManager.vue'
import {
  TOOL_DRAG_MIME,
  type ToolNodeData,
  type ToolPort,
  type ToolPorts,
  type ToolStatus,
  type UpstreamNodeRef,
  type WorkflowToolInfo,
} from '@components/workflow/toolMeta'
import {
  deserializeWorkflow,
  serializeWorkflow,
  type WorkflowDefinitionJSON,
  type WorkflowMeta,
} from '@components/workflow/serializer'
import {
  CONNECTION_DRAG_KEY,
  isBaseType,
  validateConnection,
  type ConnectionDragInfo,
} from '@components/workflow/PortConnection'
import {
  LAYOUT_X_SPACING,
  LAYOUT_X_START,
  LAYOUT_Y,
  chainOrder,
  extraOutgoingEdges,
  upstreamNodeIds,
} from '@components/workflow/graphLayout'
import { renameNodeId } from '@components/workflow/nodeRename'
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

/**
 * Edge styling: the linear chain runs left → right and the handles sit on the
 * node sides, so a smoothstep edge with an arrow reads as the pipeline it is.
 */
const defaultEdgeOptions = {
  type: 'smoothstep',
  markerEnd: MarkerType.ArrowClosed,
}

// Shared store: created here, injected by the <VueFlow> child component.
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
const dialog = useDialog()
const { t } = useI18n()

// Live connection-drag state: provided here, injected by ToolNode to highlight
// compatible handles and dim incompatible ones mid-drag.
const connectionDrag = ref<ConnectionDragInfo | null>(null)
provide(CONNECTION_DRAG_KEY, connectionDrag)

/** Resolve a port on a node by handle id (handle id == port name). */
function findPort(nodeId: string, handleId: string | null | undefined, side: 'inputs' | 'outputs'): ToolPort | undefined {
  if (!handleId) return undefined
  const node = findNode(nodeId)
  if (!node) return undefined
  const data = node.data as ToolNodeData | undefined
  return data?.ports?.[side]?.find((p) => p.name === handleId)
}

/**
 * Connection validation: base types must match (D7 — subtype is advisory and
 * never enforced). Valid drops become edges; incompatible ones are rejected
 * with a toast instead.
 */
function onConnect(connection: Connection) {
  if (connection.source && connection.source === connection.target) {
    message.error(t('workflow.editor.connection.selfLoop'))
    return
  }
  const sourcePort = findPort(connection.source, connection.sourceHandle, 'outputs')
  const targetPort = findPort(connection.target, connection.targetHandle, 'inputs')
  const result = validateConnection(
    { nodeId: connection.source, portName: connection.sourceHandle ?? '', portType: sourcePort?.type },
    { nodeId: connection.target, portName: connection.targetHandle ?? '', portType: targetPort?.type },
  )
  if (!result.valid) {
    message.error(result.reason ?? t('workflow.editor.connection.rejected'))
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

// Workflow-level metadata supplied to the serializer.
const meta = ref<WorkflowMeta>({
  name: 'Untitled workflow',
  version: '1.0',
  description: '',
  inputs: [],
  outputs: [],
})

// Monotonic counter keeps dropped node ids unique within the session.
let nodeCounter = 0

function makeNodeId(toolName: string): string {
  nodeCounter += 1
  return `tool-${toolName.replace(/[^a-z0-9]+/gi, '-')}-${nodeCounter}`
}

/** Shared node-creation path for drag-drop and click-to-append. */
function addToolNode(tool: WorkflowToolInfo, position: { x: number; y: number }) {
  const data: ToolNodeData = {
    tool: tool.name,
    status: 'idle',
    ports: tool.ports,
  }
  addNodes({ id: makeNodeId(tool.name), type: 'tool', position, data })
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

  addToolNode(tool, screenToFlowCoordinate({ x: event.clientX, y: event.clientY }))
}

/** Palette click: append after the last node of the current chain. */
function onAppendTool(tool: WorkflowToolInfo) {
  const order = chainOrder(nodeIds.value, edges.value)
  const last = order.length > 0 ? findNode(order[order.length - 1]) : null
  const position = last
    ? { x: (last.position?.x ?? LAYOUT_X_START) + LAYOUT_X_SPACING, y: last.position?.y ?? LAYOUT_Y }
    : { x: LAYOUT_X_START, y: LAYOUT_Y }
  addToolNode(tool, position)
}

// ---------------------------------------------------------------------------
// Right dock: 工作流 / 节点 tabs
// ---------------------------------------------------------------------------

type DockTab = 'workflow' | 'node'
const activeTab = ref<DockTab>('workflow')

// Deriving selection from `nodes` means the panel hides automatically on
// deselect with no extra event wiring (vue-flow sets node.selected on click).
const selectedNode = computed(() => nodes.value.find((n) => n.selected) ?? null)

/**
 * Auto-switch rule: follow the SELECTION, never fight a manual tab click.
 * Selecting a node shows 节点; deselecting returns to 工作流.
 */
watch(
  () => selectedNode.value?.id ?? null,
  (id, previous) => {
    if (id && !previous) activeTab.value = 'node'
    if (!id && previous) activeTab.value = 'workflow'
  },
)

const nodeIds = computed(() => nodes.value.map((node) => node.id))

/**
 * Upstream nodes of the selected node, in chain order: only these have results
 * in the engine's `$nodes.<id>` context when the node resolves its params.
 */
const upstreamNodes = computed<UpstreamNodeRef[]>(() => {
  const selected = selectedNode.value
  if (!selected) return []
  const upstream = upstreamNodeIds(selected.id, edges.value)
  if (upstream.size === 0) return []
  return chainOrder(nodeIds.value, edges.value)
    .filter((id) => upstream.has(id))
    .map((id) => {
      const node = findNode(id)
      const data = (node?.data ?? {}) as ToolNodeData & { operation?: string; inputs?: Record<string, unknown> }
      const toolMeta = toolsCache?.find((tool) => tool?.name === data.tool)
      const operation = typeof data.operation === 'string' ? data.operation : ''
      const operationOutputs = operation
        ? toolMeta?.operations?.find((op) => op?.name === operation)?.outputs
        : undefined
      const outputs = (operationOutputs && operationOutputs.length > 0
        ? operationOutputs
        : data.ports?.outputs) as ToolPort[] | undefined
      const stored = (data.inputs ?? (data as any).params ?? {}) as Record<string, unknown>
      return {
        id,
        label: String((data as any).label || data.tool || id),
        tool: String(data.tool ?? ''),
        outputs: outputs ?? [],
        paramKeys: Object.keys(stored),
      }
    })
})

// ---------------------------------------------------------------------------
// Linear-model guard: extra outgoing edges cannot be serialized
// ---------------------------------------------------------------------------

/** Edges that serialization would drop (docs/08 §S2). */
const edgeConflicts = computed(() => extraOutgoingEdges(nodeIds.value, edges.value))

/** Reason string handed to TemplateManager; null means saving is allowed. */
function saveBlockedReason(): string | null {
  if (edgeConflicts.value.length === 0) return null
  return t('workflow.editor.guard.title', { count: edgeConflicts.value.length })
}

// ---------------------------------------------------------------------------
// Template management — TemplateManager owns the dialogs + IPC; the page
// supplies the serialized canvas, applies loaded definitions and tracks the
// unsaved-changes state.
// ---------------------------------------------------------------------------

/** Canvas snapshot as of the last load/save, for the dirty indicator. */
const savedSnapshot = ref('')

function canvasSnapshot(): string {
  const definition = serializeCanvas()
  return definition ? JSON.stringify(definition) : ''
}

const dirty = computed(() => canvasSnapshot() !== savedSnapshot.value)
const runState = computed(() => (isRunning.value ? 'running' : dirty.value ? 'dirty' : 'saved'))
const stateLabel = computed(() =>
  isRunning.value
    ? t('workflow.editor.running')
    : dirty.value
      ? t('workflow.editor.dirty')
      : t('workflow.editor.saved'),
)

/**
 * Snapshot of the canvas for TemplateManager's save flow. Null = empty canvas
 * (TemplateManager shows a "nothing to save" toast).
 */
function serializeCanvas(): WorkflowDefinitionJSON | null {
  if (nodes.value.length === 0) return null
  return serializeWorkflow(nodes.value, edges.value, meta.value)
}

// Cached workflow.list_tools payload: tool ports hydrate loaded templates and
// operation outputs feed the binding picker. Populated lazily; failures are
// not cached (the next call retries the fetch).
let toolsCache: WorkflowToolInfo[] | null = null

async function fetchWorkflowTools(): Promise<WorkflowToolInfo[]> {
  if (toolsCache) return toolsCache
  try {
    const result = await unifiedApi.call<{ tools?: WorkflowToolInfo[] }>('workflow.list_tools', {})
    toolsCache = Array.isArray(result?.tools) ? result.tools : []
    return toolsCache
  } catch (err) {
    log.warn('[WorkflowEditorPage] workflow.list_tools unavailable, loaded nodes render without ports', err)
    return []
  }
}

async function fetchToolPorts(): Promise<Record<string, ToolPorts>> {
  const tools = await fetchWorkflowTools()
  const map: Record<string, ToolPorts> = {}
  for (const tool of tools) {
    if (tool?.name && tool.ports) map[tool.name] = tool.ports
  }
  return map
}

/**
 * Apply a loaded template to the canvas. The serializer emits generic nodes
 * with `{tool, params, label}` data; that is hydrated into ToolNode shape here
 * (type 'tool', status 'idle', ports from workflow.list_tools) before replacing
 * the whole canvas state. Positions come from the serializer's horizontal
 * auto-layout, so a loaded chain renders as one straight row.
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
      label: (node.data as any).label ?? node.data.tool,
    },
  }))
  setNodes(hydrated)
  setEdges(payload.edges)
  meta.value = { ...payload.meta }
  banner.value = null // stale run feedback belongs to the previous canvas
  problems.value = []
  problemCount.value = -1
  await nextTick()
  // The snapshot must be taken AFTER vue-flow applied the nodes, otherwise the
  // dirty indicator would light up immediately after a load.
  savedSnapshot.value = canvasSnapshot()
  await fitView({ padding: 0.2 })
}

/** TemplateManager tells us the name/description it actually persisted. */
function onTemplateSaved(info: { name: string; description: string }) {
  meta.value = { ...meta.value, name: info.name, description: info.description }
  savedSnapshot.value = canvasSnapshot()
}

// ---------------------------------------------------------------------------
// 二级页路由（docs/08 §2.1）：`/workflows/editor/:name?`
// —— 带 name 时进页面即加载该模板；不带 name 是新建空定义。
// ---------------------------------------------------------------------------

const route = useRoute()
const router = useRouter()

async function loadByName(name: string) {
  try {
    const result = await unifiedApi.call<{ definition?: WorkflowDefinitionJSON }>('template.load', {
      name,
    })
    if (!result?.definition || typeof result.definition !== 'object') {
      throw new Error(`template “${name}” returned no definition`)
    }
    await onTemplateLoad(deserializeWorkflow(result.definition))
  } catch (error) {
    log.error(`[WorkflowEditorPage] failed to load template “${name}”:`, error)
    message.error(
      t('workflows.loadFailed', {
        error: error instanceof Error ? error.message : String(error),
      }),
    )
  }
}

watch(
  () => route.params.name,
  (name) => {
    const target = typeof name === 'string' && name ? decodeURIComponent(name) : ''
    if (target) void loadByName(target)
  },
  { immediate: true },
)

/** 返回列表；有未保存改动先确认（docs/08 §3-S2 顶栏「返回」）。 */
function goBack() {
  const leave = () => void router.push('/workflows')
  if (!dirty.value) {
    leave()
    return
  }
  dialog.warning({
    title: t('workflow.editor.discardTitle'),
    content: t('workflow.editor.discardContent'),
    positiveText: t('workflow.editor.discard'),
    negativeText: t('common.cancel'),
    onPositiveClick: leave,
  })
}

// ---------------------------------------------------------------------------
// Node operations (delete / rename) — the canvas owns the graph, the panel
// only asks for them.
// ---------------------------------------------------------------------------

function onDeleteNode(nodeId: string) {
  const node = findNode(nodeId)
  if (!node) return
  dialog.warning({
    title: t('workflow.editor.config.deleteTitle'),
    content: t('workflow.editor.config.deleteContent', { id: nodeId }),
    positiveText: t('workflow.editor.config.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => {
      // Drop the node and every edge touching it (vue-flow also prunes edges
      // created through its own store, but loaded/renamed ones are explicit).
      setNodes(nodes.value.filter((entry) => entry.id !== nodeId))
      setEdges(edges.value.filter((edge) => edge.source !== nodeId && edge.target !== nodeId))
    },
  })
}

/**
 * Rename a node id: rewrites the node, its edges and every `$nodes.<oldId>.*`
 * binding in one pass (see nodeRename.ts), then re-selects the node.
 */
function onRenameNode(payload: { oldId: string; newId: string }) {
  const result = renameNodeId(nodes.value, edges.value, payload.oldId, payload.newId)
  if (!result.ok) {
    const key =
      result.error === 'duplicate'
        ? 'workflow.editor.config.errors.idDuplicate'
        : result.error === 'dot'
          ? 'workflow.editor.config.errors.idDot'
          : 'workflow.editor.config.errors.idRequired'
    message.error(t(key, { id: payload.newId }))
    return
  }
  const nextNodes = result.nodes.map((node) =>
    node.id === payload.newId ? { ...node, selected: true } : node,
  )
  setNodes(nextNodes)
  setEdges(result.edges)
  if (result.bindingsChanged > 0) {
    message.info(t('workflow.editor.renameRebound', { count: result.bindingsChanged }))
  }
}

// ---------------------------------------------------------------------------
// Static validation (workflow.validate) — "问题" panel
// ---------------------------------------------------------------------------

interface ProblemFinding {
  node_id: string | null
  field: string
  message: string
  severity: string
}

const showProblems = ref(false)
const problemsLoading = ref(false)
const problems = ref<ProblemFinding[]>([])
/** -1 = not validated yet (the toolbar count is hidden). */
const problemCount = ref(-1)

async function openProblems() {
  const definition = serializeCanvas()
  showProblems.value = true
  if (!definition) {
    problems.value = []
    problemCount.value = 0
    return
  }
  problemsLoading.value = true
  try {
    const result = await unifiedApi.call<{ errors?: ProblemFinding[] }>('workflow.validate', {
      definition,
    })
    problems.value = Array.isArray(result?.errors) ? result.errors : []
    problemCount.value = problems.value.length
  } catch (err) {
    log.error('[WorkflowEditorPage] workflow.validate failed:', err)
    problems.value = []
    problemCount.value = -1
    message.error(t('workflow.editor.problems.failed', { error: err instanceof Error ? err.message : String(err) }))
  } finally {
    problemsLoading.value = false
  }
}

/** Clicking a finding selects its node so the config panel follows along. */
function focusProblem(problem: ProblemFinding) {
  if (!problem.node_id) return
  const node = findNode(problem.node_id)
  if (!node) return
  activeTab.value = 'node'
  for (const entry of nodes.value) entry.selected = entry.id === problem.node_id
  showProblems.value = false
}

// ---------------------------------------------------------------------------
// Execution: Run button → inputs dialog → workflow.execute → stream events
// ---------------------------------------------------------------------------

/** Real event types emitted by cli/app/workflow/streaming.py. */
const WORKFLOW_EVENT_TYPES = new Set([
  'node_started',
  'node_completed',
  'workflow_completed',
  'workflow_failed',
  'workflow_cancelled',
])

/** Engine node status (streaming.py) → canvas status. */
const NODE_STATUS_MAP: Record<string, ToolStatus> = {
  ok: 'success',
  failed: 'error',
  skipped: 'skipped',
  cancelled: 'cancelled',
}

interface ExecutionBanner {
  type: 'success' | 'error' | 'warning' | 'info'
  text: string
}

const isRunning = ref(false)
const banner = ref<ExecutionBanner | null>(null)
const showInputsDialog = ref(false)
const pendingDefinition = ref<WorkflowDefinitionJSON | null>(null)

// Run identity passed to workflow.execute as `task_id`: the backend registers
// the run under the JSON-RPC request id with this task id as an ALIAS, and
// api_handler stamps `task_id` onto every streamed event — so this is the
// correlation key the page can actually know in advance.
let activeWorkflowId: string | null = null
/** `run_id` of the first matching event; tightens filtering from then on. */
let activeRunId: string | null = null
let unsubscribeStream: (() => void) | null = null

function makeWorkflowRunId(): string {
  return `wf-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

// ---- Run flow ---------------------------------------------------------------

/** Run click: serialize the canvas, then open the shared M1 inputs dialog. */
function onRunClick() {
  if (isRunning.value || nodes.value.length === 0) return
  banner.value = null
  pendingDefinition.value = serializeWorkflow(nodes.value, edges.value, meta.value)
  showInputsDialog.value = true
}

/** M1 submit: the dialog validated the form, so go straight to execution. */
function onRunSubmit(inputs: Record<string, unknown>) {
  const definition = pendingDefinition.value
  if (!definition) return
  showInputsDialog.value = false
  void startExecution(definition, inputs)
}

async function startExecution(
  definition: WorkflowDefinitionJSON,
  inputs: Record<string, unknown>,
) {
  activeWorkflowId = makeWorkflowRunId()
  activeRunId = null
  isRunning.value = true
  banner.value = null
  resetAllNodeStatuses()

  try {
    // workflow.execute is @streaming: the main process resolves this invoke on
    // the FIRST streamed event, so awaiting here only surfaces startup failures
    // (malformed definition, backend down). The terminal state arrives over the
    // stream-event channel instead, handled in handleStreamRaw.
    await window.electronAPI.callBackendAPI('workflow.execute', {
      definition,
      inputs,
      task_id: activeWorkflowId,
    })
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error)
    isRunning.value = false
    banner.value = { type: 'error', text: t('workflow.editor.execution.startFailed', { error: text }) }
    log.error('[WorkflowEditorPage] workflow.execute rejected:', error)
  }
}

/** Cancel the in-flight run (registered under the task_id alias). */
async function onCancelClick() {
  const taskId = activeWorkflowId
  if (!taskId) return
  try {
    await unifiedApi.call('request.cancel', { task_id: taskId })
  } catch (error) {
    log.error('[WorkflowEditorPage] request.cancel failed:', error)
  }
}

// ---- node status --------------------------------------------------------------

function setNodeStatus(nodeId: unknown, status: ToolStatus) {
  if (typeof nodeId !== 'string' || nodeId.length === 0) return
  if (!findNode(nodeId)) return // nested paths / deleted nodes
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

/** The engine does not emit node_completed on cancellation: mark in-flight nodes. */
function markRunningAsCancelled() {
  for (const node of nodes.value) {
    const data = (node.data ?? {}) as ToolNodeData
    if (data.status === 'running') {
      updateNodeData(node.id, { status: 'cancelled' })
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
    if (!activeWorkflowId) return // nothing started from this page

    // Correlation: api_handler injects the caller's task_id on every streamed
    // event (the event's own `workflow_id` is the DEFINITION name, not a run
    // id). Once a matching event revealed its run_id, match on that.
    if (typeof event.task_id === 'string' && event.task_id && event.task_id !== activeWorkflowId) return
    if (activeRunId && typeof event.run_id === 'string' && event.run_id !== activeRunId) return
    if (!activeRunId && typeof event.run_id === 'string' && event.run_id) activeRunId = event.run_id

    switch (type) {
      case 'node_started':
        setNodeStatus(event.node_id, 'running')
        break
      case 'node_completed': {
        const status = NODE_STATUS_MAP[String(event.status ?? '')]
        if (status) setNodeStatus(event.node_id, status)
        if (String(event.status) === 'failed') {
          message.error(
            t('workflow.editor.execution.nodeFailed', {
              error: typeof event.error === 'string' ? event.error : 'unknown error',
            }),
          )
        }
        break
      }
      case 'workflow_completed':
        isRunning.value = false
        banner.value = { type: 'success', text: t('workflow.editor.execution.success') }
        break
      case 'workflow_failed':
        isRunning.value = false
        banner.value = {
          type: 'error',
          text: t('workflow.editor.execution.failed', {
            error: typeof event.error === 'string' ? event.error : 'unknown error',
          }),
        }
        break
      case 'workflow_cancelled':
        isRunning.value = false
        markRunningAsCancelled()
        banner.value = { type: 'warning', text: t('workflow.editor.execution.cancelled') }
        break
      default:
        break
    }
  } catch (err) {
    // Handler errors must never break event routing.
    log.error('[WorkflowEditorPage] stream event handling error:', err)
  }
}

// Subscribe to the shared stream-event channel (same pattern as
// TaskStreamService.initialize); unsubscribe on page teardown.
onMounted(() => {
  // Warm the tool cache so the binding picker can offer operation-level output
  // ports before any template has been loaded.
  void fetchWorkflowTools()

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
</script>

<style scoped>
.workflow-editor-page {
  display: flex;
  gap: 8px;
  height: 100%;
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
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary);
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  background: transparent;
  border: 0;
}

.we-title:hover {
  color: var(--app-blue);
}

.we-state {
  flex-shrink: 0;
  padding: 1px 6px;
  font-size: 10px;
  border: 1px solid var(--app-card-border);
  border-radius: 8px;
  color: var(--app-text-secondary);
}

.we-state--dirty {
  color: var(--app-orange, var(--app-yellow));
  border-color: var(--app-orange, var(--app-yellow));
}

.we-state--running {
  color: var(--app-blue);
  border-color: var(--app-blue);
}

.we-banner {
  flex-shrink: 0;
}

.we-guard-title {
  font-size: 12px;
  font-weight: 600;
}

.we-guard-edges {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 4px 0 0;
}

.we-guard-edges code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 11px;
}

.we-guard-hint {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--app-text-dim);
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
  pointer-events: none;
  font-size: 13px;
  color: var(--app-text-muted);
  transform: translate(-50%, -50%);
}

/* Right dock: always visible so workflow info / ports have a home */
.we-dock {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: 320px;
  min-height: 0;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 6px;
}

.we-dock-tabs {
  display: flex;
  flex-shrink: 0;
  border-bottom: 1px solid var(--app-card-border);
}

.we-dock-tab {
  flex: 1;
  padding: 9px 8px;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-secondary);
  cursor: pointer;
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
}

.we-dock-tab:hover {
  color: var(--app-text-primary);
}

.we-dock-tab--active {
  color: var(--app-blue);
  border-bottom-color: var(--app-blue);
}

.we-dock-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  padding: 12px;
  overflow-y: auto;
}

.we-dock-divider {
  height: 1px;
  background: var(--app-card-border);
}

.we-dock-empty {
  padding: 12px;
  font-size: 12px;
  color: var(--app-text-muted);
}

/* Run dialog (rendered via teleport; scoped attrs still apply) */
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

.we-problems {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 380px;
  overflow-y: auto;
}

.we-problems-status {
  font-size: 12px;
  color: var(--app-text-muted);
}

.we-problem-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 6px 8px;
  cursor: pointer;
  border: 1px solid var(--app-card-border);
  border-radius: 5px;
}

.we-problem-row:hover {
  background: var(--app-hover);
}

.we-problem-severity {
  flex-shrink: 0;
  font-size: 10px;
  text-transform: uppercase;
}

.we-problem-row--error .we-problem-severity {
  color: var(--app-red);
}

.we-problem-row--warning .we-problem-severity {
  color: var(--app-orange, var(--app-yellow));
}

.we-problem-node {
  flex-shrink: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 11px;
  color: var(--app-text-secondary);
}

.we-problem-message {
  font-size: 12px;
  line-height: 1.45;
  color: var(--app-text-primary);
}
</style>
