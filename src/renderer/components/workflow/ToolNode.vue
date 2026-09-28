<template>
  <!--
    节点卡片 = preview 的 `.wnode`：图标方块 + 节点名 + `tool · operation`，
    左右各一个居中的连接点。
    端口名/类型**不画在卡片上**（一个 exec.shell 有 4 入 4 出，画出来就是 8 个圆点
    + 8 行文字，卡片高到 118px）；要看端口请选中节点，右侧检查器的「参数」「输出」两段
    就是端口清单。这是有意的：**边只表达执行顺序**（节点只有一个 next），不表达数据流
    ——数据流是参数里的 `$nodes.<id>.outputs.<port>` 表达式绑定，所以端口身份对连线
    没有意义（serializer.ts 也从不下发 sourceHandle/targetHandle）。
  -->
  <div
    class="tool-node"
    :class="[`tn-cat-${category}`, `tool-node--${status}`]"
    :data-selected="selected || undefined"
  >
    <Handle
      id="in"
      type="target"
      :position="Position.Left"
      class="tn-port tn-port-in"
      :class="{ 'tn-port--on': hasIncoming }"
      :title="incomingTitle"
    />
    <Handle
      id="next"
      type="source"
      :position="Position.Right"
      class="tn-port tn-port-out"
      :class="{ 'tn-port--on': hasOutgoing }"
      :title="outgoingTitle"
    />

    <span class="tn-icon"><AppIcon :name="iconName" size="sm" /></span>
    <span class="tn-title" :title="`${toolName} · ${subtitle}`">
      <span class="tn-name">{{ displayName }}</span>
      <span class="tn-sub">{{ subtitle }}</span>
    </span>
    <span
      v-if="status !== 'idle'"
      class="tn-status"
      :class="`tn-status-${status}`"
      :title="`status: ${status}`"
    />
    <span v-if="statusMark" class="tn-mark"><AppIcon :name="statusMark" size="sm" /></span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position, useVueFlow, type NodeProps } from '@vue-flow/core'
import AppIcon from '@components/ui/AppIcon.vue'
import {
  CATEGORY_ICONS,
  STATUS_MARKS,
  categoryOfToolName,
  type ToolNodeData,
} from './toolMeta'

// vue-flow passes every NodeProps field (id, type, data, selected, ...) to
// custom node components; only data/selected are used for the MVP render.
const props = defineProps<NodeProps<ToolNodeData>>()

const { edges } = useVueFlow()

const toolName = computed(() => props.data.tool)
// Node display name: the tool name (the backend schema has no node label yet,
// so the tool name IS the name — see docs/08 §3-S2 boundaries).
const displayName = computed(() => String((props.data as any).label || props.data.tool || ''))
// Secondary line: tool · operation, matching the design's node card.
const subtitle = computed(() => {
  const operation = (props.data as any).operation
  return typeof operation === 'string' && operation ? `${props.data.tool} · ${operation}` : props.data.tool
})
const category = computed(() => categoryOfToolName(props.data.tool))
const status = computed(() => props.data.status ?? 'idle')
// Header check/X mark (todo 38): only success and error states carry one.
const statusMark = computed(() =>
  status.value === 'success' || status.value === 'error' ? STATUS_MARKS[status.value] : '',
)
const iconName = computed(() => CATEGORY_ICONS[category.value])

/**
 * Port "connected" state (preview `.port.on`): with one handle per side, the
 * incoming handle lights up when any edge targets this node and the outgoing
 * one when any edge leaves it — i.e. "this end of the chain is linked".
 */
const nodeId = computed(() => props.id)
const hasIncoming = computed(() =>
  edges.value.some((edge) => edge.target === nodeId.value),
)
const hasOutgoing = computed(() =>
  edges.value.some((edge) => edge.source === nodeId.value),
)
const incomingTitle = computed(() =>
  hasIncoming.value ? '已接入上游节点' : '输入连接点：把上游节点拖到这里',
)
const outgoingTitle = computed(() =>
  hasOutgoing.value ? '已连向下一节点' : '输出连接点：拖到下一个节点（线性链，只有一个 next）',
)
</script>

<style scoped>
/*
 * Colors come from the workflow editor tokens (--node-bg/--node-border/
 * --node-text, defined in themes.css as aliases of the app theme tokens); the
 * category only contributes an accent via --tn-accent. Radius/shadow follow
 * the app's minimal rule: 1px border at rest, lift on hover.
 */
.tool-node {
  --tn-accent: var(--app-text-dim);
  position: relative;
  display: flex;
  gap: 10px;
  align-items: center;
  width: 200px;
  padding: 9px 12px;
  background: var(--node-bg);
  border: 1px solid var(--node-border);
  border-radius: var(--radius-control);
  color: var(--node-text);
  font-size: 11px;
  transition: box-shadow 0.14s ease, transform 0.14s ease, border-color 0.14s ease;
}

.tool-node:hover {
  box-shadow: var(--shadow-lift);
  transform: translateY(-1px);
}

.tool-node[data-selected] {
  border-color: var(--app-blue);
  box-shadow: 0 0 0 2px var(--app-blue-bg);
}

/*
 * Execution status (todo 38). Compound selectors (0,2,0) so a status border
 * wins over the [data-selected] rule above. Statuses persist after a run
 * until the next Run or a structural canvas change (see editor page).
 */
.tool-node.tool-node--idle {
  border-color: var(--node-border);
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
  border-radius: var(--radius-control);
  animation: tn-border-pulse 1.2s ease-in-out infinite;
}

.tool-node.tool-node--success {
  border-color: var(--app-green);
}

.tool-node.tool-node--error {
  border-color: var(--app-red);
}

/* Skipped / cancelled: terminal but not a failure of the run itself. */
.tool-node.tool-node--skipped {
  border-color: var(--app-text-dim);
}

.tool-node.tool-node--cancelled {
  border-color: var(--app-orange, var(--app-yellow));
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

/* Category icon square (preview `.wnode .ni`). */
.tn-icon {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  color: var(--tn-accent);
  background: var(--app-storage-bg);
  border-radius: var(--radius-chip);
}

.tn-title {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  line-height: 1.25;
}

.tn-name {
  overflow: hidden;
  font-size: 12.5px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tn-sub {
  overflow: hidden;
  font-family: "Fira Code", Consolas, monospace;
  font-size: 11px;
  color: var(--app-text-dim);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tn-status {
  flex: none;
  width: 7px;
  height: 7px;
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

.tn-status-skipped {
  background: var(--app-text-dim);
}

.tn-status-cancelled {
  background: var(--app-orange, var(--app-yellow));
}

/* Check/X header mark (todo 38) */
.tn-mark {
  display: inline-flex;
  flex: none;
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

/*
 * One handle per side. vue-flow's base .vue-flow__handle is
 * position:absolute with distance -left/-right; the -left/-right modifier
 * classes derived from `Position` also supply `top: 50%` and the centring
 * `transform: translate(±50%, -50%)`. **Never touch `transform` here** — it is
 * what keeps the dot straddling the node edge, so hover feedback grows the box
 * (and adds a ring) instead of scaling.
 */
.tool-node .tn-port {
  width: 9px;
  height: 9px;
  background: var(--node-bg);
  border: 1.6px solid var(--tn-accent);
  border-radius: 50%;
  transition: width 0.12s ease, height 0.12s ease, background-color 0.12s ease,
    border-color 0.12s ease, box-shadow 0.12s ease;
}

.tool-node .tn-port:hover {
  width: 13px;
  height: 13px;
  background: var(--tn-accent);
  box-shadow: 0 0 0 4px var(--app-blue-bg);
}

/* preview `.port.on` — this end of the chain is linked. */
.tool-node .tn-port--on {
  background: var(--app-blue);
  border-color: var(--app-blue);
}
</style>
