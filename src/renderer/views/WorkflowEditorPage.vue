<template>
  <!--
    版式逐字取自 docs/ui-prompts/ui-preview.html 的 S2 屏：
      .screen.editor  顶栏横跨整宽，下面才是三列
        .ed-top       返回 / 工作流名 / 状态 / 模板 / 问题 / 试运行
        .warn-bar     线性模型守卫（多余出边）
        .ed-body      .ed-left(240) ｜ .canvas ｜ .ed-right(320)
    三列都是**贴边的整高面板**（只有 1px 分隔线），不是三张浮起的圆角卡片——
    那是之前"很挤"的主因：3 层卡片边框 + 2 个 8px 间隙 + 各自的内边距，全是从
    画布身上割的。

    右栏只有一条信息流（没有 tab）：没选中节点 = 工作流信息（名字/版本/描述 +
    输入输出声明），选中节点 = 节点检查器（顶部一行「← 工作流」返回）。
  -->
  <section class="screen editor we-editor">
    <div class="ed-top">
      <n-button size="small" quaternary :title="t('workflow.editor.back')" @click="goBack">
        <template #icon><AppIcon name="back" /></template>
      </n-button>
      <span class="ed-name" :title="meta.name">
        {{ meta.name || t('workflow.editor.title') }}
      </span>
      <!-- 工作流信息（名称/版本/描述）从右栏搬到这个按钮后面的弹窗：右栏只服务选中的
           节点/端点，画布才能吃满宽度（docs/08 §3·S2）。 -->
      <n-button
        size="small"
        quaternary
        class="we-edit-info"
        :title="t('workflow.editor.info.edit')"
        @click="showInfoDialog = true"
      >
        <template #icon><AppIcon name="pencil" size="sm" /></template>
      </n-button>
      <span class="we-state" :class="`we-state--${runState}`">{{ stateLabel }}</span>

      <div class="we-top-actions">
        <WorkflowFileActions
          :get-definition="serializeCanvas"
          :blocked-reason="saveBlockedReason"
          @save="onSaveClick"
          @import="onImportPayload"
        />
        <n-button
          size="small"
          :type="showRunLog ? 'primary' : 'default'"
          :quaternary="!showRunLog"
          :title="t('workflow.editor.runLog.toggle')"
          data-test="run-log-toggle"
          @click="showRunLog = !showRunLog"
        >
          <template #icon><AppIcon name="term" /></template>
          {{ t('workflow.editor.runLog.title') }}
        </n-button>
        <n-button size="small" @click="openProblems">
          {{ t('workflow.editor.problems.button') }}
          <template v-if="problemCount >= 0">&nbsp;{{ problemCount }}</template>
        </n-button>
        <n-button
          v-if="!isRunning"
          size="small"
          type="primary"
          :disabled="realNodes.length === 0"
          @click="onRunClick"
        >
          {{ t('workflow.editor.run') }}
        </n-button>
        <n-button v-else size="small" type="warning" @click="onCancelClick">
          {{ t('workflow.editor.cancel') }}
        </n-button>
      </div>
    </div>

    <!-- Linear-model guard: extra outgoing edges cannot be saved -->
    <div v-if="edgeConflicts.length > 0" class="warn-bar" data-test="edge-guard">
      <div class="w1">
        <AppIcon name="alert" size="sm" />
        <span>{{ t('workflow.editor.guard.title', { count: edgeConflicts.length }) }}</span>
      </div>
      <div
        v-for="conflict in edgeConflicts"
        :key="`${conflict.source}->${conflict.target}`"
        class="w2"
      >
        {{ conflict.source }} → {{ conflict.target }}
      </div>
      <div class="w3">{{ t('workflow.editor.guard.hint') }}</div>
    </div>

    <!-- Terminal execution result banner; closable, persists until next Run -->
    <AppNotice
      v-if="banner"
      class="we-banner"
      :tone="banner.tone"
      closable
      @close="banner = null"
    >
      {{ banner.text }}
    </AppNotice>

    <div class="ed-body">
      <!-- 左栏：工具面板 -->
      <div class="ed-left">
        <WorkflowNodePalette @append="onAppendTool" />
      </div>

      <!-- 画布 -->
      <main class="canvas" @dragover="onDragOver" @drop="onDrop">
        <!--
          No `fit-view-on-init`: it refires whenever nodes first appear, so the
          first drop/append made vue-flow fit-to-view a 1-node graph and clamp
          to ~3.9x — the canvas jumped and the node left the drop point. The
          canvas now stays at whatever viewport the user has, and fitView is
          called once, explicitly, when a saved template is loaded.

          `<Background variant="dots" :gap="20">` matches the preview's 20px dot
          grid but pans/zooms with the canvas (the CSS dot pattern from
          `.pv .canvas` is switched off in the style block — two grids would
          double the dots).

          `connection-radius="40"` widens the drop target: each node has exactly
          one handle per side, so a generous snap radius is what makes chaining
          feel easy.
        -->
        <VueFlow
          :node-types="nodeTypes"
          :min-zoom="0.2"
          :max-zoom="4"
          :connection-radius="40"
          :delete-key-code="null"
          :default-edge-options="defaultEdgeOptions"
          @connect="onConnect"
          @nodes-initialized="onNodesInitialized"
        >
          <Background variant="dots" :gap="20" />
          <!-- Controls' `position` prop is typed as the (deprecated) PanelPosition
               enum, not the string union MiniMap accepts — hence the enum member
               rather than the "bottom-right" literal. -->
          <Controls :position="PanelPosition.BottomRight" />
          <MiniMap position="bottom-left" :pannable="true" :zoomable="true" />
        </VueFlow>

        <div v-if="realNodes.length === 0" class="we-empty">
          <AppIcon name="wf" :size="44" />
          <p class="we-empty-title">{{ t('workflow.editor.emptyCanvas') }}</p>
          <p class="we-empty-hint">{{ t('workflow.editor.emptyCanvasHint') }}</p>
        </div>

        <!-- 运行日志：贴画布底部的抽屉（docs/08 §3·S2）。运行中吃 stream-event
             （节点事件 + flow.log 的 `log` 事件），终态再读一次 task.read_log
             拿到与磁盘一致的全文与 log_path。 -->
        <RunLogPanel
          v-if="showRunLog"
          ref="runLogPanelRef"
          :lines="runLogLines"
          :running="isRunning"
          :loading="runLogLoading"
          :log-path="runLogPath"
          :truncated="runLogTruncated"
          @refresh="() => refreshRunLog(0)"
          @close="showRunLog = false"
          @open-file="openRunLogFile"
        />
      </main>

      <!-- 右栏 = 选中对象（节点 / 端点）的检查器。没有选中就没有右栏：工作流信息已经
           搬到顶栏的弹窗里，画布因此吃满整宽（docs/08 §3·S2）。 -->
      <div class="ed-right we-inspector" :class="{ 'we-inspector--collapsed': !selectedNode }">
        <div class="cfg-hd">
          <!-- 标题 = 选中的东西：工具节点显示**节点名**（`data.label`，空则工具名），
               端点显示 开始 / 结束。节点身份（名字 + id）只在这一处出现，改名入口
               就挂在名字右侧，所以节点面板里不再有「基础」分区（docs/08 §3-S2）。 -->
          <div class="we-cfg-hd-row">
            <n-input
              v-if="renaming"
              ref="renameFieldRef"
              class="we-cfg-rename"
              size="small"
              :value="renameDraft"
              :placeholder="selectedToolName"
              data-test="npc-rename-input"
              @update:value="(value: string) => (renameDraft = value)"
              @keydown.enter.prevent="commitRename"
              @keydown.esc.stop.prevent="cancelRename"
              @blur="commitRename"
            />
            <template v-else>
              <div class="cn" :title="selectedPanelTitle">{{ selectedPanelTitle }}</div>
              <button
                v-if="isToolNodeSelected"
                type="button"
                class="we-cfg-btn we-cfg-btn--icon"
                :title="t('workflow.editor.config.fields.rename')"
                data-test="npc-rename"
                @click="startRename"
              >
                <AppIcon name="pencil" size="sm" />
              </button>
            </template>
            <button
              type="button"
              class="we-cfg-btn we-cfg-btn--icon"
              :title="t('workflow.editor.dock.close')"
              @click="deselectNode"
            >
              <AppIcon name="x" size="sm" />
            </button>
          </div>
          <!-- id 是引用身份（`$nodes.<id>.*`）且自动生成、不可改：一行可复制的文本 -->
          <div
            class="cd"
            :class="{ 'cd--copy': isToolNodeSelected }"
            :title="nodeIdTitle"
            data-test="npc-id"
            @click="copyNodeId"
          >
            {{ selectedNodeSubtitle }}
          </div>
        </div>

        <!-- 端点就是工作流的出入参入口：开始 = 入参，结束 = 出参（docs/08 §3·S2） -->
        <IoAuthoringPanel
          v-if="selectedVirtualKind"
          :key="selectedVirtualKind"
          class="cfg-bd we-endpoint-io"
          :meta="meta"
          :side="selectedVirtualKind === 'start' ? 'inputs' : 'outputs'"
          hide-tabs
          @update:meta="meta = $event"
        />
        <NodeConfigPanel
          v-else-if="selectedNode"
          :node="selectedNode"
          :workflow-inputs="meta.inputs ?? []"
          :upstream-nodes="upstreamNodes"
          @delete="onDeleteNode"
          @open-settings="openNodeSettings"
        />
      </div>
    </div>

    <!-- 工作流信息弹窗（顶栏标题后的「编辑信息」按钮打开） -->
    <WorkflowInfoDialog
      v-model:show="showInfoDialog"
      :meta="meta"
      :node-count="realNodes.length"
      :edge-count="realEdgeCount"
      @update:meta="meta = $event"
    />

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
  </section>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  MarkerType,
  PanelPosition,
  VueFlow,
  useVueFlow,
  type Connection,
  type Edge,
  type Node,
} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import {
  NAlert,
  NButton,
  NInput,
  NModal,
  useDialog,
  useMessage,
} from 'naive-ui'
import AppIcon from '@components/ui/AppIcon.vue'
import AppNotice, { type NoticeTone } from '@components/ui/AppNotice.vue'

import ToolNode from '@components/workflow/ToolNode.vue'
import VirtualNode from '@components/workflow/VirtualNode.vue'
import WorkflowNodePalette from '@components/workflow/WorkflowNodePalette.vue'
import NodeConfigPanel from '@components/workflow/NodeConfigPanel.vue'
import IoAuthoringPanel from '@components/workflow/IoAuthoringPanel.vue'
import WorkflowInfoDialog from '@components/workflow/WorkflowInfoDialog.vue'
import RunInputsDialog from '@components/workflow/RunInputsDialog.vue'
import RunLogPanel from '@components/workflow/RunLogPanel.vue'
import WorkflowFileActions, {
  type WorkflowImportPayload,
} from '@components/workflow/WorkflowFileActions.vue'
import {
  RUN_LOG_EVENT_TYPES,
  TERMINAL_RUN_EVENT_TYPES,
  formatRunLogEvent,
  linesFromTaskLog,
  nowTimeString,
  type RunLogLine,
} from '@components/workflow/runLog'
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
  validateOnDeserialize,
  type WorkflowDefinitionJSON,
  type WorkflowMeta,
} from '@components/workflow/serializer'
import {
  LAYOUT_X_SPACING,
  LAYOUT_X_START,
  LAYOUT_Y,
  chainOrder,
  extraOutgoingEdges,
  upstreamNodeIds,
} from '@components/workflow/graphLayout'
import {
  effectivePorts,
  validateNodeEditable,
} from '@components/workflow/nodeValidation'
import { withNodeDefaults } from '@components/workflow/nodeDefaults'
import {
  VIRTUAL_END_ID,
  VIRTUAL_START_ID,
  appendAnchorBeforeEnd,
  deleteSelectionGraph,
  ensureEndpointGraph,
  isVirtualNodeId,
  insertBeforeEnd,
  realGraph,
  virtualKindOf,
} from '@components/workflow/virtualNodes'
import unifiedApi from '@/api/unifiedApi'
import { toJsonPayload } from '@utils/jsonPayload'
import { log } from '@utils/logger'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

// Custom node registration: node `type: "tool"` renders ToolNode, the two
// canvas-only endpoints render VirtualNode (see virtualNodes.ts).
// markRaw keeps the component out of Vue's reactivity system (vue-flow
// warns about reactive node-types objects).
const nodeTypes = {
  tool: markRaw(ToolNode),
  start: markRaw(VirtualNode),
  end: markRaw(VirtualNode),
}

/**
 * Edge styling: the linear chain runs left → right and the handles sit on the
 * node sides (one per side).
 *
 * `type: 'default'` is vue-flow's **cubic Bézier** edge (the same `C …` path the
 * design mock draws), not `smoothstep`: smoothstep routes with orthogonal
 * segments plus rounded corners, so a chain whose nodes sit at different heights
 * renders as right-angled steps instead of a curve. Note that for two nodes on
 * the SAME row (what the auto-layout produces) a Bézier between a right anchor
 * and a left anchor is a straight horizontal line — that is geometry, not a
 * style choice; the curve only shows up once the nodes are vertically offset.
 */
const defaultEdgeOptions = {
  type: 'default',
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

/**
 * Connection validation (09-28). 一个节点每侧只有一个连接点，**边只表达执行
 * 顺序**——`serializer.ts` 的 `resolveNextMap` 只看 source/target，从不下发
 * sourceHandle/targetHandle。所以这里只剩唯一一条必须挡住的规则：自环
 * （self-loop，后端会当成 cycle 拒绝）。以前那套"按端口 base type 校验"在
 * 单连接点下不成立（没有端口身份可比），已随 ToolNode 的多 handle 一起下线。
 */
function onConnect(connection: Connection) {
  if (connection.source && connection.source === connection.target) {
    message.error(t('workflow.editor.connection.selfLoop'))
    return
  }
  // addEdges generates the edge id and silently skips duplicate connections
  // (same source/target/handles), so no bookkeeping is needed here.
  addEdges(connection)
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

/**
 * Node ids are auto-generated and NOT user-editable, so the generator itself
 * has to guarantee uniqueness: a loaded template can already contain
 * `tool-apktool-1`, and a duplicate id would make the canvas unsavable with no
 * way for the user to fix it. The name is cosmetic (`data.label`).
 */
function makeNodeId(toolName: string, taken: Set<string>): string {
  const slug = toolName.replace(/[^a-z0-9]+/gi, '-')
  let candidate = ''
  do {
    nodeCounter += 1
    candidate = `tool-${slug}-${nodeCounter}`
  } while (taken.has(candidate))
  return candidate
}

/** Shared node-creation path for drag-drop and click-to-append. Returns the new node id. */
function addToolNode(tool: WorkflowToolInfo, position: { x: number; y: number }): string {
  const id = makeNodeId(tool.name, new Set(nodes.value.map((node) => node.id)))
  const data: ToolNodeData = {
    tool: tool.name,
    status: 'idle',
    ports: tool.ports,
  }
  addNodes({ id, type: 'tool', position, data })
  return id
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

/**
 * Palette click: append the tool right before 结束 — the tail of the REAL
 * chain, not the tail of the canvas (which is always the End endpoint).
 *
 * Placing the node to the RIGHT of the tail is not enough — without the edge
 * `next` stays null, so a three-click workflow used to end up with three entry
 * nodes and the backend rejected the save ("must have exactly one entry node").
 * The edge id follows the serializer's `${source}->${target}` convention so it
 * cannot collide with a loaded template's edges.
 */
function onAppendTool(tool: WorkflowToolInfo) {
  // The visible tail of the chain is ALWAYS 结束, so the anchor is resolved on
  // the real graph (virtualNodes.appendAnchorBeforeEnd) and the new node is
  // spliced in right BEFORE End: 开始 → … → 上一个 → 新节点 → 结束.
  const anchorId = appendAnchorBeforeEnd(nodes.value, edges.value)
  const anchor = anchorId ? findNode(anchorId) : null
  const position = anchor
    ? { x: (anchor.position?.x ?? LAYOUT_X_START) + LAYOUT_X_SPACING, y: anchor.position?.y ?? LAYOUT_Y }
    : { x: LAYOUT_X_START, y: LAYOUT_Y }
  const newId = addToolNode(tool, position)
  if (anchorId) {
    setEdges(insertBeforeEnd(edges.value, anchorId, newId))
  }
}

// ---------------------------------------------------------------------------
// Canvas-only endpoints (开始 / 结束) — see components/workflow/virtualNodes.ts
// ---------------------------------------------------------------------------

/** Tool nodes only (everything the serializer will actually save). */
const realNodes = computed(() => nodes.value.filter((node) => !isVirtualNodeId(node.id)))

/**
 * Keep the two endpoints on the canvas. They can be removed like any node
 * (Backspace / 删除), and a chain without its anchors is confusing, so a
 * missing one is restored together with its chain edge. Manual edges are never
 * rewritten: `ensureEndpointGraph` only wires endpoints it had to create.
 */
function restoreEndpoints() {
  const graph = ensureEndpointGraph(nodes.value, edges.value)
  if (graph.nodes.length === nodes.value.length && graph.edges.length === edges.value.length) return
  setNodes(graph.nodes)
  setEdges(graph.edges)
}

const nodeIdSignature = computed(() => nodes.value.map((node) => node.id).join('\u0000'))

watch(nodeIdSignature, () => {
  const ids = new Set(nodes.value.map((node) => node.id))
  if (ids.has(VIRTUAL_START_ID) && ids.has(VIRTUAL_END_ID)) return
  restoreEndpoints()
})

// ---------------------------------------------------------------------------
// Right column: single flow — 工作流信息 ⇄ 节点检查器
// ---------------------------------------------------------------------------

// Deriving selection from `nodes` means the panel follows the canvas with no
// extra event wiring (vue-flow sets node.selected on click). Selecting a node
// swaps the column to the node inspector; clearing the selection swaps it back
// to the workflow info, so no tab state has to be maintained.
const selectedNode = computed(() => nodes.value.find((n) => n.selected) ?? null)

/** Current tool name of the selected node (the node card's title line). */
const selectedToolName = computed(() => String(selectedNode.value?.data?.tool ?? ''))

/**
 * 节点展示名 = `data.label`，没名字时兜底工具名（与画布节点卡片、表达式选择器
 * 同一套口径）。右栏标题显示的就是它。
 */
const selectedNodeTitle = computed(() => {
  const label = (selectedNode.value?.data as Record<string, unknown> | undefined)?.label
  return typeof label === 'string' && label.length > 0 ? label : selectedToolName.value
})

/**
 * `.cd` line for the node inspector: the node's **id**.
 *
 * The id is the node's identity — it is what `$nodes.<id>.outputs…` bindings
 * embed — and it is auto-generated/read-only. It is shown here (and copied on
 * click) instead of in a panel section, so the inspector never repeats it.
 */
const selectedNodeSubtitle = computed(() => {
  const node = selectedNode.value
  if (!node) return ''
  // 端点：`.cn` 已经是「开始 / 结束」，副标题说明这里配的是哪一侧的工作流端口。
  if (isVirtualNodeId(node.id)) {
    return virtualKindOf(node.id) === 'end'
      ? t('workflow.editor.virtual.endIo')
      : t('workflow.editor.virtual.startIo')
  }
  return t('workflow.editor.dock.nodeContext', { label: node.id })
})

/** Real (non-endpoint) connections — the number the saved definition carries. */
const realEdgeCount = computed(
  () =>
    edges.value.filter((edge) => !isVirtualNodeId(edge.source) && !isVirtualNodeId(edge.target))
      .length,
)

/** Selected canvas-only endpoint ('start' / 'end'), or null for a tool node. */
const selectedVirtualKind = computed(() => virtualKindOf(selectedNode.value?.id))

/** 选中的是真实工具节点（端点没有名字，也没有可复制的节点 id）。 */
const isToolNodeSelected = computed(() => !!selectedNode.value && !selectedVirtualKind.value)

/** `.cn` title of the inspector header: node display name, or 开始 / 结束. */
const selectedPanelTitle = computed(() => {
  const kind = selectedVirtualKind.value
  if (kind === 'start') return t('workflow.editor.virtual.start')
  if (kind === 'end') return t('workflow.editor.virtual.end')
  return selectedNodeTitle.value
})

/**
 * `.cd` 的 tooltip：说明 id 只读、可复制。端点行不是 id，不给提示。
 */
const nodeIdTitle = computed(() =>
  isToolNodeSelected.value
    ? `${t('workflow.editor.config.fields.idReadonlyHint')} · ${t('workflow.editor.config.fields.idCopyHint')}`
    : '',
)

// ---- 节点改名（标题右侧的铅笔按钮） ------------------------------------
//
// 名字就是 `data.label`（纯显示用，表达式永远引用 id）。留空或写回工具名都等于
// 「没名字」——直接删键，工具名自然兜底，工作流 JSON 里不会留下冗余 label。

const renaming = ref(false)
const renameDraft = ref('')
const renameFieldRef = ref<InstanceType<typeof NInput> | null>(null)

async function startRename() {
  if (!isToolNodeSelected.value || renaming.value) return
  renameDraft.value = selectedNodeTitle.value
  renaming.value = true
  await nextTick()
  renameFieldRef.value?.focus()
}

function cancelRename() {
  renaming.value = false
  renameDraft.value = ''
}

/** 提交改名：Enter / 失焦都走这里（Esc 走 cancelRename）。 */
function commitRename() {
  if (!renaming.value) return
  const node = selectedNode.value
  const value = renameDraft.value.trim()
  renaming.value = false
  renameDraft.value = ''
  if (!node) return
  const data = (node.data ?? {}) as Record<string, unknown>
  if (!value || value === selectedToolName.value) delete data.label
  else data.label = value
}

/** 换选中（或收起右栏）时退出编辑态，半截输入不留给下一个节点。 */
watch(
  () => selectedNode.value?.id,
  () => cancelRename(),
)

/** 复制节点 id（名称引用 `$nodes.<id>.*` 要用它）。 */
async function copyNodeId() {
  const node = selectedNode.value
  if (!node || !isToolNodeSelected.value) return
  try {
    await navigator.clipboard?.writeText(node.id)
    message.success(t('workflow.editor.config.fields.copied'))
  } catch (error) {
    log.warn('[WorkflowEditorPage] clipboard unavailable', error)
  }
}

/** 工作流信息弹窗的开关（顶栏标题后的「编辑信息」按钮）。 */
const showInfoDialog = ref(false)

/** 取消选中：右栏随之收起（ToolNode 的 selected 由 vue-flow 维护）。 */
function deselectNode() {
  for (const entry of nodes.value) entry.selected = false
}

const nodeIds = computed(() => nodes.value.map((node) => node.id))

/**
 * Upstream nodes of the selected node, in chain order: only these have results
 * in the engine's `$nodes.<id>` context when the node resolves its params.
 * The canvas-only endpoints are filtered out — they produce no results, so
 * offering them in the binding picker would only create broken references.
 *
 * Ports come from the shared `effectivePorts` helper (operation ports when an
 * operation is selected, else the tool's own), so the picker offers exactly
 * what the panel edits and what the engine validates.
 */
const upstreamNodes = computed<UpstreamNodeRef[]>(() => {
  const selected = selectedNode.value
  if (!selected || isVirtualNodeId(selected.id)) return []
  const upstream = upstreamNodeIds(selected.id, edges.value)
  if (upstream.size === 0) return []
  return chainOrder(nodeIds.value, edges.value)
    .filter((id) => !isVirtualNodeId(id) && upstream.has(id))
    .map((id) => {
      const node = findNode(id)
      const data = (node?.data ?? {}) as ToolNodeData & { operation?: string; inputs?: Record<string, unknown> }
      const toolInfo = toolsCache.value?.find((tool) => tool?.name === data.tool)
      const ports = effectivePorts(data, toolInfo)
      const stored = (data.inputs ?? (data as any).params ?? {}) as Record<string, unknown>
      return {
        id,
        label: String((data as any).label || data.tool || id),
        tool: String(data.tool ?? ''),
        outputs: ports.outputs as unknown as ToolPort[],
        paramKeys: Object.keys(stored),
      }
    })
})

// ---------------------------------------------------------------------------
// Linear-model guard: extra outgoing edges cannot be serialized
// ---------------------------------------------------------------------------

/** Edges that serialization would drop (docs/08 §S2). */
const edgeConflicts = computed(() => extraOutgoingEdges(nodeIds.value, edges.value))

/**
 * Canvas-local findings about the 开始 / 结束 wiring. They exist only on the
 * canvas (the wire format has no endpoints), so they cannot come from
 * `validateOnDeserialize` — but they decide which node the engine runs FIRST,
 * so an unwired 开始 is reported exactly like the other structural blockers.
 */
function endpointProblems(): string[] {
  if (realNodes.value.length === 0) return []
  const real = realGraph(nodes.value, edges.value)
  const entry = chainOrder(
    real.nodes.map((node) => node.id),
    real.edges,
  )[0]
  const startTarget = edges.value.find((edge) => edge.source === VIRTUAL_START_ID)?.target
  if (startTarget && startTarget === entry) return []
  return [t('workflow.editor.virtual.notWired', { entry: entry ?? '—' })]
}

/**
 * Reason string handed to TemplateManager; null means saving is allowed.
 *
 * Four independent blockers, checked in order:
 *  1. extra outgoing edges — the canvas shows its own banner for that;
 *  2. 开始 not wired to the chain entry (see endpointProblems);
 *  3. a node that is not runnable yet (operation not picked / required input
 *     missing / select port without options) — the panel marks the same fields
 *     red as you touch them, so the block always has a visible counterpart;
 *  4. a structurally invalid chain (several entry nodes / a cycle / orphans),
 *     which the backend rejects with a raw English message. Validating here with
 *     the SAME rules the loader uses (`validateOnDeserialize`) turns it into a
 *     pointer at the 问题 panel instead of a backend error toast.
 */
function saveBlockedReason(): string | null {
  if (edgeConflicts.value.length > 0) {
    return t('workflow.editor.guard.title', { count: edgeConflicts.value.length })
  }
  const endpoints = endpointProblems()
  if (endpoints.length > 0) return endpoints[0]
  // 序列化一次，节点校验与结构校验共用同一份文档（这个函数在每次渲染时被读）。
  const definition = serializeCanvas()
  if (!definition) return null
  const invalidNode = firstInvalidNode(definition)
  if (invalidNode) {
    return t('workflow.editor.config.errors.nodeInvalid', { id: invalidNode })
  }
  const structural = validateOnDeserialize(definition)
  if (structural.length === 0) return null
  return t('workflow.editor.template.notChained', { count: structural.length })
}

/**
 * First node that cannot run as configured (see nodeValidation), or null.
 *
 * Operates on the already-serialized document so the ids match exactly what the
 * wire document (and the error message) will name.
 */
function firstInvalidNode(definition: WorkflowDefinitionJSON): string | null {
  const tools = new Map((toolsCache.value ?? []).map((tool) => [tool?.name, tool]))
  for (const node of definition.nodes) {
    const data = (findNode(node.id)?.data ?? {}) as Record<string, unknown>
    if (validateNodeEditable(data, tools.get(node.tool)).length > 0) return node.id
  }
  return null
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
 * Snapshot of the canvas for TemplateManager's save flow. Null = nothing worth
 * saving (TemplateManager shows a "nothing to save" toast).
 *
 * The canvas always carries the two virtual endpoints, so "empty" means "no
 * TOOL node": serializing 开始 → 结束 alone would produce `nodes: []`, which is
 * a valid but meaningless document.
 */
function serializeCanvas(): WorkflowDefinitionJSON | null {
  if (realNodes.value.length === 0) return null
  return serializeWorkflow(nodes.value, edges.value, meta.value)
}

// Cached workflow.list_tools payload: tool ports hydrate loaded templates and
// operation outputs feed the binding picker; the right column's `.cd` line also
// reads the tool description from here, so it is a ref rather than a plain let
// (a non-reactive cache would leave the header stale until the next render).
const toolsCache = ref<WorkflowToolInfo[] | null>(null)

async function fetchWorkflowTools(): Promise<WorkflowToolInfo[]> {
  if (toolsCache.value) return toolsCache.value
  try {
    const result = await unifiedApi.call<{ tools?: WorkflowToolInfo[] }>('workflow.list_tools', {})
    toolsCache.value = Array.isArray(result?.tools) ? result.tools : []
    return toolsCache.value
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
 * Apply a loaded workflow (route load OR 导入工作流) to the canvas. The
 * serializer emits generic nodes with `{tool, params, label}` data; that is
 * hydrated into ToolNode shape here (type 'tool', status 'idle', ports from
 * workflow.list_tools) before replacing the whole canvas state. Positions come
 * from the serializer's horizontal auto-layout, shifted one slot to the right
 * so 开始 gets its own column, and the two endpoints are then added around the
 * chain (virtualNodes.ts).
 */
async function applyCanvasPayload(payload: WorkflowImportPayload) {
  const portsByTool = await fetchToolPorts()
  const hydrated: Node[] = payload.nodes.map((node) => ({
    ...node,
    type: 'tool',
    position: {
      x: (node.position?.x ?? LAYOUT_X_START) + LAYOUT_X_SPACING,
      y: node.position?.y ?? LAYOUT_Y,
    },
    data: {
      ...node.data,
      status: 'idle',
      ports: portsByTool[node.data.tool],
      label: (node.data as any).label ?? node.data.tool,
    },
  }))
  const graph = ensureEndpointGraph(hydrated, payload.edges)
  setNodes(graph.nodes)
  setEdges(graph.edges)
  meta.value = { ...payload.meta }
  banner.value = null // stale run feedback belongs to the previous canvas
  problems.value = []
  problemCount.value = -1
  await nextTick()
  // The snapshot must be taken AFTER vue-flow applied the nodes, otherwise the
  // dirty indicator would light up immediately after a load.
  savedSnapshot.value = canvasSnapshot()
  // Only on an explicit load — NOT on every add (see the `fit-view-on-init`
  // note on <VueFlow>). `maxZoom: 1` keeps a 1–2 node workflow from being
  // blown up to the 4x ceiling, which made a freshly loaded canvas unusable.
  requestFitView()
}

// `fitView` needs the nodes' MEASURED size, and vue-flow only learns that from
// its ResizeObserver — one tick after setNodes they still measure 0×0, so an
// awaited fitView right here silently no-ops and a long chain stays half
// outside the canvas (the viewport transform stays `none`). So the fit is
// deferred to vue-flow's `nodes-initialized` event, with a synchronous
// fallback for the case where the nodes were already measured.
let pendingFitView = false

function onNodesInitialized() {
  if (!pendingFitView) return
  pendingFitView = false
  void fitView({ padding: 0.2, maxZoom: 1 })
}

function requestFitView() {
  pendingFitView = true
  const measured =
    nodes.value.length > 0 &&
    nodes.value.every((node) => ((node as any).dimensions?.width ?? 0) > 0)
  if (measured) onNodesInitialized()
}

/** 保存（顶栏）：名称/描述就是 `meta` —— 空名字先让用户去信息弹窗填。 */
async function onSaveClick() {
  const name = (meta.value.name ?? '').trim()
  if (!name) {
    message.warning(t('workflow.editor.template.nameRequired'))
    showInfoDialog.value = true
    return
  }
  const definition = serializeCanvas()
  if (!definition) {
    message.warning(t('workflow.editor.template.emptyCanvas'))
    return
  }
  try {
    await unifiedApi.call('template.save', {
      name,
      // Definition name/description mirror the template identity so the stored
      // WorkflowDefinition is self-consistent (name must be non-empty).
      definition: { ...definition, name, description: meta.value.description ?? '' },
      description: meta.value.description ?? '',
      tags: [],
    })
    savedSnapshot.value = canvasSnapshot()
    message.success(t('workflow.editor.template.saved', { name }))
  } catch (error) {
    log.error(`[WorkflowEditorPage] failed to save workflow “${name}”:`, error)
    message.error(
      t('workflow.editor.template.saveFailed', {
        error: error instanceof Error ? error.message : String(error),
      }),
    )
  }
}

/**
 * 导入工作流：把一份工作流 JSON 读进画布（替换当前画布）。
 *
 * 有未保存改动时先确认——导入是**整块替换**，不是合并，未保存的节点会消失。
 */
function onImportPayload(payload: WorkflowImportPayload, sourcePath: string) {
  const apply = async () => {
    await applyCanvasPayload(payload)
    message.success(
      t('workflow.editor.import.imported', {
        name: payload.meta.name || sourcePath,
      }),
    )
  }
  if (!dirty.value) {
    void apply()
    return
  }
  dialog.warning({
    title: t('workflow.editor.import.confirmTitle'),
    content: t('workflow.editor.import.confirmContent'),
    positiveText: t('workflow.editor.import.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => {
      void apply()
    },
  })
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
    await applyCanvasPayload(deserializeWorkflow(result.definition))
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
    if (target) {
      void loadByName(target)
      return
    }
    // 新建（无 name）：只为**首次进入**的空画布补上 开始 / 结束。已有的画布不动
    // ——从「编辑 foo」跳到「新建」时旧画布原样留着，与本页一直以来的行为一致。
    if (nodes.value.length === 0) {
      const graph = ensureEndpointGraph([], [])
      setNodes(graph.nodes)
      setEdges(graph.edges)
    }
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

/**
 * Keys that delete the current canvas selection.
 *
 * vue-flow's own keyboard delete is switched off (`:delete-key-code="null"`)
 * because it only ever bound **Backspace** (its default `deleteKeyCode`), and
 * its delete is a plain "remove" that cannot keep the chain intact. Here both
 * keys behave identically and share ONE implementation with the inspector's
 * 「删除节点」 button.
 */
const DELETE_KEY_CODES = new Set(['Backspace', 'Delete'])

/**
 * True when the canvas owns the key event. Backspace inside a text field must
 * keep deleting characters, and while a dialog/drawer is open the keyboard
 * belongs to that overlay.
 */
function canvasOwnsKeyEvent(event: KeyboardEvent): boolean {
  const path = typeof event.composedPath === 'function' ? event.composedPath() : []
  const target = (path[0] ?? event.target) as HTMLElement | null
  if (!target) return true
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(target.nodeName)) return false
  if (typeof target.hasAttribute === 'function' && target.hasAttribute('contenteditable')) return false
  if (typeof target.closest === 'function' && target.closest('.nokey')) return false
  // 任何 naive 弹层（模态 / 对话框 / 抽屉）打开时，键盘归它
  return !document.querySelector('.n-modal, .n-dialog, .n-drawer')
}

/** Remove the given selection from the canvas and keep the chain connected. */
function applyDeletion(selectedNodes: Node[], selectedEdges: Edge[]) {
  if (selectedNodes.length === 0 && selectedEdges.length === 0) return
  const result = deleteSelectionGraph(
    nodes.value,
    edges.value,
    selectedNodes.map((node) => node.id),
    selectedEdges.map((edge) => edge.id),
  )
  if (result.removedNodeIds.length > 0) {
    setNodes(result.nodes)
    setEdges(result.edges)
  } else if (selectedEdges.length > 0) {
    setEdges(result.edges)
  }
  // 端点删不掉是**有意**的（它们是画布结构），所以给一句话而不是静默恢复
  if (result.blockedEndpoint) message.info(t('workflow.editor.virtual.protected'))
}

function onCanvasKeyDown(event: KeyboardEvent) {
  if (!DELETE_KEY_CODES.has(event.key)) return
  if (!canvasOwnsKeyEvent(event)) return
  const selectedNodes = nodes.value.filter((node) => node.selected)
  const selectedEdges = edges.value.filter((edge) => edge.selected)
  if (selectedNodes.length === 0 && selectedEdges.length === 0) return
  event.preventDefault()
  applyDeletion(selectedNodes, selectedEdges)
}

function onDeleteNode(nodeId: string) {
  const node = findNode(nodeId)
  if (!node) return
  if (isVirtualNodeId(nodeId)) {
    message.info(t('workflow.editor.virtual.protected'))
    return
  }
  dialog.warning({
    title: t('workflow.editor.config.deleteTitle'),
    content: t('workflow.editor.config.deleteContent', { id: nodeId }),
    positiveText: t('workflow.editor.config.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => applyDeletion([node], []),
  })
}

/**
 * 「去设置」：节点行为默认值配在设置页（节点卡片），面板只负责发起跳转 ——
 * 组件本身不依赖路由，测试里也不需要 router。
 */
function openNodeSettings() {
  void router.push('/settings')
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
  // Structural findings are a CANVAS-LOCAL property (several entry nodes / a
  // cycle / orphans), so report them without a backend round trip. The backend
  // cannot answer for this case either: `workflow.validate` feeds the definition
  // to WorkflowDefinition.from_dict, which RAISES on a broken chain, so the
  // request came back as an error toast instead of findings — dead exactly when
  // the panel mattered most. Same rules the loader uses (validateOnDeserialize),
  // so the panel and the save guard can never disagree.
  const structural = [...endpointProblems(), ...validateOnDeserialize(definition)]
  if (structural.length > 0) {
    problems.value = structural.map((message) => ({
      node_id: null,
      field: 'structure',
      message,
      severity: 'error',
    }))
    problemCount.value = problems.value.length
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
  for (const entry of nodes.value) entry.selected = entry.id === problem.node_id
  showProblems.value = false
}

// ---------------------------------------------------------------------------
// Execution: Run button → inputs dialog → workflow.execute → stream events
// ---------------------------------------------------------------------------

// Event types live in runLog.ts (single source for the filter + the formatter).

/** Engine node status (streaming.py) → canvas status. */
const NODE_STATUS_MAP: Record<string, ToolStatus> = {
  ok: 'success',
  failed: 'error',
  skipped: 'skipped',
  cancelled: 'cancelled',
}

interface ExecutionBanner {
  tone: NoticeTone
  text: string
}

const isRunning = ref(false)
const banner = ref<ExecutionBanner | null>(null)
const showInputsDialog = ref(false)
const pendingDefinition = ref<WorkflowDefinitionJSON | null>(null)

// ---- run log (docs/08 §3·S2) --------------------------------------------------
// Two-phase, deliberately: while the run is in flight the panel shows the
// streamed events (node lifecycle + `log` lines from tools such as flow.log);
// on the terminal event the per-task log file is read back, which is the same
// text plus everything a non-streaming tool logged, and carries `log_path`.

const showRunLog = ref(false)
const runLogLines = ref<RunLogLine[]>([])
const runLogPath = ref('')
const runLogTruncated = ref(false)
const runLogLoading = ref(false)
const runLogPanelRef = ref<InstanceType<typeof RunLogPanel> | null>(null)

/** How much of the per-task log to pull back (the file itself is capped at 50 MiB). */
const RUN_LOG_TAIL_BYTES = 256 * 1024

function pushRunLogLine(line: RunLogLine | null) {
  if (line) runLogLines.value.push(line)
}

/** Start of a run: fresh panel, visible, following the tail again. */
function beginRunLog() {
  runLogLines.value = []
  runLogPath.value = ''
  runLogTruncated.value = false
  showRunLog.value = true
  runLogPanelRef.value?.resetScroll()
}

/**
 * Read the per-task log written by the engine (`task_log_writer`) at teardown.
 *
 * The file is only flushed when the run ends, so this is a terminal-state call —
 * mid-run it would legitimately return nothing. A failure never touches the live
 * lines already collected from the stream.
 *
 * `retries` exists because the flush happens in the backend's teardown, slightly
 * AFTER the terminal event reaches the renderer: an empty read right after
 * `workflow_completed` is usually "not flushed yet", not "no log".
 */
async function refreshRunLog(retries = 0) {
  const taskId = activeWorkflowId
  if (!taskId || runLogLoading.value) return
  runLogLoading.value = true
  try {
    const result = await unifiedApi.call<{
      content?: string
      truncated?: boolean
      log_path?: string
    }>('task.read_log', { task_id: taskId, tail_bytes: RUN_LOG_TAIL_BYTES })
    runLogPath.value = typeof result?.log_path === 'string' ? result.log_path : ''
    runLogTruncated.value = result?.truncated === true
    const fromFile = linesFromTaskLog(result?.content)
    if (fromFile.length === 0 && retries < 3) {
      runLogLoading.value = false
      setTimeout(() => void refreshRunLog(retries + 1), 250)
      return
    }
    // Only replace when the file actually has content: an empty read must not
    // wipe the live lines (e.g. the flush failed).
    if (fromFile.length > 0) runLogLines.value = fromFile
  } catch (error) {
    log.warn('[WorkflowEditorPage] task.read_log failed:', error)
  } finally {
    runLogLoading.value = false
  }
}

function openRunLogFile() {
  if (!runLogPath.value) return
  const api = window.electronAPI
  if (!api || typeof api.openPath !== 'function') return
  void api.openPath(runLogPath.value).catch((error: unknown) => {
    log.warn('[WorkflowEditorPage] openPath failed:', error)
  })
}

// ---- edge status styling ------------------------------------------------------
// The traversed path lights up while a run walks the chain: the edge leaving a
// node takes that node's status colour (and animates while it is running).
// Edges are MUTATED in place rather than pushed back through setEdges — a
// setEdges round trip emits add/remove changes, which onEdgesChange would read
// as "the graph changed" and clear every node status right after a run.

const STATUS_EDGE_COLOR: Record<ToolStatus, string | undefined> = {
  idle: undefined,
  running: 'var(--app-blue)',
  success: 'var(--app-green)',
  error: 'var(--app-red)',
  skipped: 'var(--app-text-dim)',
  cancelled: 'var(--app-orange)',
}

/** Cheap signature of every node's status; the watcher only fires on real changes. */
const nodeStatusSignature = computed(() =>
  nodes.value.map((node) => `${node.id}:${(node.data as ToolNodeData)?.status ?? 'idle'}`).join(),
)

/** source→target keys of the edges serialization would drop (see the guard). */
const conflictPairs = computed(
  () => new Set(edgeConflicts.value.map((conflict) => `${conflict.source}\u0000${conflict.target}`)),
)

function statusOf(nodeId: string | null | undefined): ToolStatus {
  if (!nodeId) return 'idle'
  return ((findNode(nodeId)?.data as ToolNodeData | undefined)?.status ?? 'idle') as ToolStatus
}

function paintEdges() {
  for (const edge of edges.value) {
    // Extra out-edges win over status colours: they are the ones the guard
    // banner is complaining about, so they get the mock's orange dashed mark.
    if (conflictPairs.value.has(`${edge.source}\u0000${edge.target}`)) {
      edge.animated = false
      edge.style = { stroke: 'var(--app-orange)', strokeWidth: 2, strokeDasharray: '5 4' }
      continue
    }
    const status = statusOf(edge.source)
    const color = STATUS_EDGE_COLOR[status]
    edge.animated = isRunning.value && status === 'running'
    edge.style = color ? { stroke: color, strokeWidth: 2 } : undefined
  }
}

watch([nodeStatusSignature, isRunning, conflictPairs], paintEdges, { immediate: true })

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
  if (isRunning.value || realNodes.value.length === 0) return
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
  beginRunLog()

  try {
    // workflow.execute is @streaming: the main process resolves this invoke on
    // the FIRST streamed event, so awaiting here only surfaces startup failures
    // (malformed definition, backend down). The terminal state arrives over the
    // stream-event channel instead, handled in handleStreamRaw.
    //
    // This call bypasses unifiedApi (it needs the raw invoke), so it must flatten
    // the payload itself: `inputs` comes from the run dialog and can still hold
    // Vue reactive proxies (e.g. the array of a 多选 input), which contextBridge
    // refuses to clone — "An object could not be cloned."
    //
    // `node_defaults` carries the settings page's node behaviour defaults: the
    // nodes that did not pin their own failure handling (「跟随系统」) resolve to
    // these values inside the engine.
    await window.electronAPI.callBackendAPI(
      'workflow.execute',
      toJsonPayload(
        await withNodeDefaults({ definition, inputs, task_id: activeWorkflowId }),
      ),
    )
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error)
    isRunning.value = false
    banner.value = { tone: 'danger', text: t('workflow.editor.execution.startFailed', { error: text }) }
    pushRunLogLine({
      kind: 'workflow',
      time: nowTimeString(),
      node: '',
      text,
      error: text,
    })
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
    if (!RUN_LOG_EVENT_TYPES.has(type)) return // logcat/download/etc. noise
    if (!activeWorkflowId) return // nothing started from this page

    // Correlation: api_handler injects the caller's task_id on every streamed
    // event (the event's own `workflow_id` is the DEFINITION name, not a run
    // id). Once a matching event revealed its run_id, match on that.
    if (typeof event.task_id === 'string' && event.task_id && event.task_id !== activeWorkflowId) return
    if (activeRunId && typeof event.run_id === 'string' && event.run_id !== activeRunId) return
    if (!activeRunId && typeof event.run_id === 'string' && event.run_id) activeRunId = event.run_id

    // Every accepted event becomes a line in the run log (same text the engine
    // writes into the per-task file), terminal events included.
    pushRunLogLine(formatRunLogEvent(event))

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
        banner.value = { tone: 'success', text: t('workflow.editor.execution.success') }
        break
      case 'workflow_failed':
        isRunning.value = false
        banner.value = {
          tone: 'danger',
          text: t('workflow.editor.execution.failed', {
            error: typeof event.error === 'string' ? event.error : 'unknown error',
          }),
        }
        break
      case 'workflow_cancelled':
        isRunning.value = false
        markRunningAsCancelled()
        banner.value = { tone: 'warning', text: t('workflow.editor.execution.cancelled') }
        break
      default:
        break
    }

    // Terminal state: the engine flushed the per-task log at teardown, so read
    // it back for the authoritative full text + `log_path`. Deferred a tick so
    // the backend's unregister() flush is not raced by this invoke.
    if (TERMINAL_RUN_EVENT_TYPES.has(type)) {
      setTimeout(() => void refreshRunLog(0), 0)
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

  // 键盘删除由本页接管（vue-flow 自带的已在 <VueFlow> 上关掉），见 onCanvasKeyDown
  window.addEventListener('keydown', onCanvasKeyDown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onCanvasKeyDown)
  if (unsubscribeStream) {
    try {
      unsubscribeStream()
    } catch {}
    unsubscribeStream = null
  }
})
</script>

<style scoped>
/*
 * Only the editor-specific gaps the preview stylesheet does not cover live
 * here: the top bar's flex distribution (title + 编辑信息 button, action group
 * pinned right and never clipped) and the inspector's collapsed state.
 * Everything else (`.screen.editor`, `.ed-top`, `.ed-body`, `.ed-left`,
 * `.canvas`, `.ed-right`, `.cfg-hd`, `.cfg-bd`, `.warn-bar`) comes from
 * assets/styles/preview-layout.css. Compound scoped selectors beat the `.pv`
 * rules regardless of stylesheet injection order.
 */
/* 只读标题：名称的编辑入口是紧随其后的铅笔按钮（弹窗），标题本身不再可点 */
.we-editor .ed-name {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 42%;
  overflow: hidden;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--app-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.we-edit-info {
  flex: none;
}

/* Tail group pinned right. It is allowed to SHRINK and WRAP (never to clip):
   with 保存 / 导入工作流 / 运行日志 / 问题 / 运行 the row is ~460px wide, which no
   longer fits next to a long workflow name on a narrow window — wrapping to a
   second line keeps every action reachable (the alternative, `flex: none`, just
   pushed 运行 off the right edge). */
.we-top-actions {
  display: flex;
  flex: 0 1 auto;
  flex-wrap: wrap;
  gap: 8px;
  row-gap: 6px;
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
  margin-left: auto;
}

.we-state {
  flex: none;
  padding: 1px 6px;
  font-size: 10px;
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-pill);
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

/* Run-result banner sits between the guard bar and the three columns. */
.we-banner {
  flex: none;
  margin: 0 16px 10px;
}

/* `<Background variant="dots">` already paints the 20px dot grid and pans with
   the canvas; `.pv .canvas` also carries a static CSS dot pattern — two grids
   would double the dots, so the CSS one goes. */
.we-editor .canvas {
  background-image: none;
}

.we-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  display: flex;
  z-index: 1;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  pointer-events: none;
  text-align: center;
  transform: translate(-50%, -50%);
}

.we-empty :deep(svg) {
  margin-bottom: 6px;
  color: var(--app-text-dim);
  opacity: 0.45;
}

.we-empty-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.we-empty-hint {
  margin: 0;
  font-size: 12px;
  color: var(--app-text-muted);
}

/* Right column: node/endpoint inspector only, and it exists ONLY while something
   is selected — no selection means the canvas takes the full width (the workflow
   info moved into the top bar's dialog). Width comes from `.pv .ed-right`. */
.we-editor .we-inspector {
  transition: width 0.16s ease;
}

.we-editor .we-inspector--collapsed {
  width: 0;
  overflow: hidden;
  border-left: 0;
}

/* 端点检查器：入参 / 出参编辑区（`.cfg-bd` 已给 padding 与滚动） */
.we-editor .we-endpoint-io {
  margin: 0;
}

.we-cfg-hd-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.we-cfg-hd-row .cn {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 改名输入框就地替换标题（同一个 flex 槽位，宽度不跳） */
.we-cfg-rename {
  flex: 1;
  min-width: 0;
}

/* `.cd` 是节点 id：可点击复制（端点行不是 id，不加这个类） */
.we-cfg-hd-row + .cd--copy {
  cursor: pointer;
}

.cd--copy:hover {
  color: var(--app-blue);
}

.we-cfg-btn {
  display: inline-flex;
  flex: none;
  gap: 4px;
  align-items: center;
  padding: 2px 8px;
  font: inherit;
  font-size: 11px;
  color: var(--app-text-dim);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-pill);
}

.we-cfg-btn--icon {
  padding: 2px 6px;
}

.we-cfg-btn:hover {
  color: var(--app-text-primary);
  background: var(--app-hover);
}

.we-cfg-divider {
  height: 1px;
  margin: 14px 0;
  background: var(--app-card-border);
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
  overscroll-behavior: contain;
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
  border-radius: var(--radius-chip);
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
  font-family: var(--font-family-monospace);
  font-size: 11px;
  color: var(--app-text-secondary);
}

.we-problem-message {
  font-size: 12px;
  line-height: 1.45;
  color: var(--app-text-primary);
}
</style>
