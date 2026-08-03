<template>
  <div class="workflow-editor-page">
    <!-- Left panel: tool palette (todo 34) -->
    <WorkflowNodePalette />

    <!-- Center: vue-flow canvas -->
    <main class="we-canvas" @dragover="onDragOver" @drop="onDrop">
      <VueFlow :node-types="nodeTypes" :min-zoom="0.2" :max-zoom="4">
        <Background />
        <Controls />
        <MiniMap />
      </VueFlow>
      <div v-if="nodes.length === 0" class="we-empty-hint">
        Empty workflow — drag a tool from the palette to get started
      </div>
    </main>

    <!-- Right panel: node config (todo 36), shown while a node is selected -->
    <aside v-if="selectedNode" class="we-panel we-config">
      <div class="we-panel-header">Node Config</div>
      <NodeConfigPanel :node="selectedNode" />
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue'
import { VueFlow, useVueFlow, type Node, type Edge } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'

import ToolNode from '@components/workflow/ToolNode.vue'
import WorkflowNodePalette from '@components/workflow/WorkflowNodePalette.vue'
import NodeConfigPanel from '@components/workflow/NodeConfigPanel.vue'
import {
  TOOL_DRAG_MIME,
  type ToolNodeData,
  type WorkflowToolInfo,
} from '@components/workflow/toolMeta'

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
// and are used by the palette drop handler below.
const { nodes, edges, addNodes, screenToFlowCoordinate } = useVueFlow({
  nodes: [] as Node[],
  edges: [] as Edge[],
})

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

.we-canvas {
  position: relative;
  flex: 1;
  min-width: 0;
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
</style>
