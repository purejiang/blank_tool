<template>
  <div
    class="tool-node"
    :class="[`tn-cat-${category}`, `tool-node--${status}`]"
    :data-selected="selected || undefined"
  >
    <Handle
      v-for="(port, index) in inputs"
      :key="`in-${port.name}`"
      :id="port.name"
      type="target"
      :position="Position.Left"
      class="tn-handle tn-handle-in"
      :class="handleDragClass(port, 'in')"
      :style="{ top: `${portRowCenterY(index)}px` }"
      :title="portTitle(port)"
    />
    <Handle
      v-for="(port, index) in outputs"
      :key="`out-${port.name}`"
      :id="port.name"
      type="source"
      :position="Position.Right"
      class="tn-handle tn-handle-out"
      :class="handleDragClass(port, 'out')"
      :style="{ top: `${portRowCenterY(index)}px` }"
      :title="portTitle(port)"
    />

    <div class="tn-header">
      <span class="tn-icon" v-html="iconSvg" />
      <span class="tn-name" :title="toolName">{{ toolName }}</span>
      <span class="tn-status" :class="`tn-status-${status}`" :title="`status: ${status}`" />
      <span v-if="statusMark" class="tn-mark" v-html="statusMark" />
    </div>

    <div v-if="inputs.length > 0 || outputs.length > 0" class="tn-body" :style="{ height: `${bodyHeightPx}px` }">
      <div class="tn-port-col">
        <div v-for="port in inputs" :key="port.name" class="tn-port" :title="portTitle(port)">
          {{ port.name }}<span v-if="port.required" class="tn-req">*</span>
        </div>
      </div>
      <div class="tn-port-col tn-port-col-out">
        <div v-for="port in outputs" :key="port.name" class="tn-port" :title="portTitle(port)">
          {{ port.name }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { Handle, Position, type NodeProps } from '@vue-flow/core'
import {
  CONNECTION_DRAG_KEY,
  isPortCompatible,
  type ConnectionDragInfo,
} from './PortConnection'
import {
  CATEGORY_ICONS,
  PORT_ROW_HEIGHT_PX,
  PORTS_PADDING_Y_PX,
  STATUS_MARKS,
  categoryOfToolName,
  portRowCenterY,
  portTitle,
  type ToolNodeData,
  type ToolPort,
} from './toolMeta'

// vue-flow passes every NodeProps field (id, type, data, selected, ...) to
// custom node components; only data/selected are used for the MVP render.
const props = defineProps<NodeProps<ToolNodeData>>()

const toolName = computed(() => props.data.tool)
const category = computed(() => categoryOfToolName(props.data.tool))
const status = computed(() => props.data.status ?? 'idle')
// Header check/X mark (todo 38): only success and error states carry one.
const statusMark = computed(() =>
  status.value === 'success' || status.value === 'error' ? STATUS_MARKS[status.value] : '',
)
const inputs = computed(() => props.data.ports?.inputs ?? [])
const outputs = computed(() => props.data.ports?.outputs ?? [])
const iconSvg = computed(() => CATEGORY_ICONS[category.value])
const bodyHeightPx = computed(
  () => PORTS_PADDING_Y_PX * 2 + Math.max(inputs.value.length, outputs.value.length) * PORT_ROW_HEIGHT_PX,
)

// Live connection-drag state from WorkflowEditorPage (todo 35): while a
// connection is being dragged, opposite-side handles with a matching base
// type highlight and mismatched ones dim. Default ref keeps ToolNode usable
// outside a providing ancestor.
const connectionDrag = inject(CONNECTION_DRAG_KEY, ref<ConnectionDragInfo | null>(null))

/** 'tn-handle-compatible' / 'tn-handle-incompatible' while dragging, else undefined. */
function handleDragClass(port: ToolPort, side: 'in' | 'out'): string | undefined {
  const drag = connectionDrag.value
  if (!drag) return undefined
  const isDropSide =
    (side === 'in' && drag.fromHandleType === 'source') ||
    (side === 'out' && drag.fromHandleType === 'target')
  if (!isDropSide) return undefined
  return isPortCompatible(drag.base, port.type.base) ? 'tn-handle-compatible' : 'tn-handle-incompatible'
}
</script>

<style scoped>
/*
 * Functional monochrome MVP styling. Colors come from the workflow editor
 * tokens (--node-bg/--node-border/--node-text, defined in themes.css as
 * aliases of the app theme tokens); the category only contributes an accent
 * via --tn-accent. Row metrics here must match toolMeta.ts: header 28px,
 * port row 18px, body vertical padding 6px.
 */
.tool-node {
  --tn-accent: var(--app-text-dim);
  position: relative;
  min-width: 150px;
  background: var(--node-bg);
  border: 1px solid var(--node-border);
  border-left: 3px solid var(--tn-accent);
  border-radius: 6px;
  color: var(--node-text);
  font-size: 11px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}

.tool-node[data-selected] {
  border-color: var(--app-blue);
  box-shadow: 0 0 0 1px var(--app-blue);
}

/*
 * Execution status (todo 38). Compound selectors (0,2,0) so a status border
 * wins over the [data-selected] rule above. Statuses persist after a run
 * until the next Run or a structural canvas change (see editor page).
 */
.tool-node.tool-node--idle {
  border-color: var(--node-border);
  border-left-color: var(--tn-accent);
}

.tool-node.tool-node--running {
  border-color: var(--app-blue);
}

/* Pulsing outer ring — animates opacity only (compositor-friendly). */
.tool-node.tool-node--running::after {
  content: "";
  position: absolute;
  inset: -3px;
  pointer-events: none;
  border: 2px solid var(--app-blue);
  border-radius: 8px;
  animation: tn-border-pulse 1.2s ease-in-out infinite;
}

.tool-node.tool-node--success {
  border-color: var(--app-green);
}

.tool-node.tool-node--error {
  border-color: var(--app-red);
}

@keyframes tn-border-pulse {
  0%,
  100% {
    opacity: 0.9;
  }

  50% {
    opacity: 0.15;
  }
}

.tn-cat-file {
  --tn-accent: var(--app-blue);
}

.tn-cat-net {
  --tn-accent: var(--app-green);
}

.tn-cat-exec {
  --tn-accent: var(--app-orange);
}

.tn-cat-flow {
  --tn-accent: var(--app-purple);
}

.tn-header {
  display: flex;
  gap: 6px;
  align-items: center;
  height: 28px;
  padding: 0 8px;
}

.tn-icon {
  display: inline-flex;
  flex-shrink: 0;
  color: var(--tn-accent);
}

.tn-icon :deep(svg) {
  width: 12px;
  height: 12px;
}

.tn-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tn-status {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--app-text-dim);
}

.tn-status-running {
  background: var(--app-blue);
  animation: tn-pulse 1.1s ease-in-out infinite;
}

.tn-status-success {
  background: var(--app-green);
}

.tn-status-error {
  background: var(--app-red);
}

/* Check/X header mark (todo 38) */
.tn-mark {
  display: inline-flex;
  flex-shrink: 0;
}

.tn-mark :deep(svg) {
  width: 12px;
  height: 12px;
}

.tool-node--success .tn-mark {
  color: var(--app-green);
}

.tool-node--error .tn-mark {
  color: var(--app-red);
}

@keyframes tn-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }

  50% {
    opacity: 0.45;
    transform: scale(0.72);
  }
}

.tn-body {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 6px 10px;
  border-top: 1px solid var(--node-border);
}

.tn-port-col {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.tn-port {
  height: 18px;
  overflow: hidden;
  line-height: 18px;
  color: var(--app-text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tn-port-col-out .tn-port {
  text-align: right;
}

.tn-req {
  margin-left: 1px;
  color: var(--app-yellow);
}

/*
 * vue-flow's base .vue-flow__handle is position:absolute with left/right
 * pinned to the node edge; we only override size, shape and the top offset
 * (inline per-port, see template).
 */
.tn-handle {
  width: 8px;
  height: 8px;
  background: var(--node-bg);
  border: 1.5px solid var(--tn-accent);
  border-radius: 50%;
  transition: transform 0.12s ease, opacity 0.12s ease, background-color 0.12s ease;
}

.tn-handle:hover {
  background: var(--tn-accent);
}

/*
 * Connection-drag feedback (todo 35): while a connection is being dragged,
 * opposite-side handles whose base type matches highlight, mismatched ones
 * dim. Colors reuse theme tokens; only transform/opacity are transitioned.
 */
.tn-handle-compatible {
  background: var(--app-green);
  border-color: var(--app-green);
  transform: scale(1.4);
}

.tn-handle-incompatible {
  opacity: 0.25;
}
</style>
