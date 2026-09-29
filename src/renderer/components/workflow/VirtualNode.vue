<template>
  <!--
    纯前端虚拟端点（开始 / 结束）。后端的工作流模型里没有这两个东西——链的入口
    就是"没有被别人指向的节点"——所以它们只存在于画布上：`serializeWorkflow`
    会把它们（以及所有连到它们身上的边）一并丢掉，见 virtualNodes.ts。

    卡片刻意做得比工具节点小、且只有一个连接点：视觉上读作"链的两端"，不读作
    一个可以被配置的步骤。因此它没有可编辑参数，选中它时右栏给的是说明而不是
    节点检查器（WorkflowEditorPage）。
  -->
  <div
    class="vnode"
    :class="`vnode--${kind}`"
    :data-selected="selected || undefined"
    :title="hint"
  >
    <Handle
      v-if="kind === 'start'"
      id="next"
      type="source"
      :position="Position.Right"
      class="vn-port vn-port-out"
      :class="{ 'vn-port--on': hasOutgoing }"
      :title="t('workflow.editor.virtual.startPort')"
    />
    <Handle
      v-else
      id="in"
      type="target"
      :position="Position.Left"
      class="vn-port vn-port-in"
      :class="{ 'vn-port--on': hasIncoming }"
      :title="t('workflow.editor.virtual.endPort')"
    />

    <span class="vn-icon"><AppIcon :name="kind === 'start' ? 'play' : 'check'" size="sm" /></span>
    <span class="vn-label">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position, useVueFlow, type NodeProps } from '@vue-flow/core'
import { useI18n } from 'vue-i18n'
import AppIcon from '@components/ui/AppIcon.vue'

import type { VirtualNodeData } from './virtualNodes'

/**
 * 端点节点：`type: "start"` / `"end"`（注册在 WorkflowEditorPage 的 nodeTypes）。
 * 只画一个连接点——开始只有输出、结束只有输入，所以不可能连出"结束 → 某节点"
 * 这种反方向结构。
 */
const props = defineProps<NodeProps<VirtualNodeData>>()

const { t } = useI18n()
const { edges } = useVueFlow()

const kind = computed(() => (props.type === 'end' ? 'end' : 'start'))
const label = computed(() =>
  kind.value === 'start' ? t('workflow.editor.virtual.start') : t('workflow.editor.virtual.end'),
)
const hasOutgoing = computed(() => edges.value.some((edge) => edge.source === props.id))
const hasIncoming = computed(() => edges.value.some((edge) => edge.target === props.id))

/**
 * 端点自己的提示：它是**工作流出入参的配置入口**（选中后右栏就是该侧的端口编辑），
 * 这条 title 是唯一的可发现性线索——右栏在没选中时不显示。
 */
const hint = computed(() => label.value + ' · ' + t(kind.value === 'start' ? 'workflow.editor.virtual.startIo' : 'workflow.editor.virtual.endIo'))
</script>

<style scoped>
.vnode {
  --vn-accent: var(--app-text-dim);
  position: relative;
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  width: 108px;
  padding: 7px 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--node-text);
  background: var(--node-bg);
  border: 1px dashed var(--node-border);
  border-radius: var(--radius-pill);
  transition: border-color 0.14s ease, box-shadow 0.14s ease;
}

/* 虚线描边 + 药丸形 = "这不是一个步骤，只是链的端点" */
.vnode--start {
  --vn-accent: var(--app-green);
}

.vnode--end {
  --vn-accent: var(--app-text-dim);
}

.vnode:hover {
  box-shadow: var(--shadow-lift);
}

.vnode[data-selected] {
  border-style: solid;
  border-color: var(--vn-accent);
  box-shadow: 0 0 0 2px var(--app-blue-bg);
}

.vn-icon {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--vn-accent);
  background: var(--app-storage-bg);
  border-radius: 50%;
}

.vn-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 与 ToolNode 同一套连接点样式（同样的位置修饰类约定：绝不覆写 transform）。 */
.vnode .vn-port {
  width: 9px;
  height: 9px;
  background: var(--node-bg);
  border: 1.6px solid var(--vn-accent);
  border-radius: 50%;
  transition: width 0.12s ease, height 0.12s ease, background-color 0.12s ease,
    border-color 0.12s ease, box-shadow 0.12s ease;
}

.vnode .vn-port:hover {
  width: 13px;
  height: 13px;
  background: var(--vn-accent);
  box-shadow: 0 0 0 4px var(--app-blue-bg);
}

.vnode .vn-port--on {
  background: var(--app-blue);
  border-color: var(--app-blue);
}
</style>
