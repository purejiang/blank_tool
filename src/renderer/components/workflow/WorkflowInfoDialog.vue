<template>
  <!--
    工作流信息弹窗（顶栏标题后的「编辑信息」按钮打开）。
    以前这些字段常驻在右栏；右栏现在只服务"选中的节点/端点"，信息改成按需弹窗，
    画布才能吃满宽度（docs/08 §3·S2）。

    弹窗编辑的是 `draft`（打开时从 meta 拷一份），点「保存」才 emit —— 取消/遮罩关闭
    不会把半截输入写回画布（否则未保存改动标记会莫名亮起）。
  -->
  <n-modal
    v-model:show="visible"
    preset="card"
    :title="t('workflow.editor.info.title')"
    :style="{ width: '460px' }"
    :mask-closable="true"
  >
    <WorkflowInfoPanel :meta="draft" @update:meta="draft = $event" />
    <div class="we-info-summary">
      {{
        t('workflow.editor.dock.workflowSummary', {
          nodes: nodeCount,
          edges: edgeCount,
        })
      }}
    </div>
    <template #footer>
      <div class="we-info-footer">
        <n-button size="small" @click="close">{{ t('common.cancel') }}</n-button>
        <n-button size="small" type="primary" :disabled="!nameValid" @click="confirm">
          {{ t('workflow.editor.info.save') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NModal } from 'naive-ui'

import WorkflowInfoPanel from './WorkflowInfoPanel.vue'
import type { WorkflowMeta } from './serializer'

const props = defineProps<{
  show: boolean
  meta: WorkflowMeta
  /** 真实节点数 / 真实连线数（不含画布端点），只作只读摘要。 */
  nodeCount?: number
  edgeCount?: number
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'update:meta', value: WorkflowMeta): void
}>()

const { t } = useI18n()

const visible = computed({
  get: () => props.show,
  set: (value: boolean) => emit('update:show', value),
})

/** Local copy so 取消 never leaks half-typed values into the canvas. */
const draft = ref<WorkflowMeta>({ ...props.meta })

watch(
  () => props.show,
  (show) => {
    if (show) draft.value = { ...props.meta }
  },
)

const nameValid = computed(() => String(draft.value?.name ?? '').trim().length > 0)

function close() {
  emit('update:show', false)
}

function confirm() {
  if (!nameValid.value) return
  emit('update:meta', { ...props.meta, ...draft.value })
  emit('update:show', false)
}
</script>

<style scoped>
.we-info-summary {
  margin-top: 10px;
  font-size: 11px;
  color: var(--app-text-dim);
}

.we-info-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
