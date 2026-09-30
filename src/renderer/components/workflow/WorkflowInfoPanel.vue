<template>
  <!-- Workflow-level identity (name / version / description).
       Rendered inside WorkflowInfoDialog (opened from the editor's top bar); it
       used to live permanently in the right dock. The name is display-only now:
       it is NOT the storage identity (the `wf-…` id is), so it needs no
       path-safety validation — only "not empty", because the schema requires a
       name. -->
  <div class="workflow-info-panel">
    <n-form label-placement="top" size="small">
      <n-form-item
        :label="t('workflow.editor.info.name')"
        required
        :validation-status="nameMissing ? 'error' : undefined"
        :feedback="nameMissing ? t('workflow.editor.info.nameRequired') : t('workflow.editor.info.nameHint')"
      >
        <n-input
          :value="meta.name"
          size="small"
          data-test="workflow-name"
          :placeholder="t('workflow.editor.info.namePlaceholder')"
          @update:value="(value: string) => update({ name: value })"
        />
      </n-form-item>
      <!-- 只读 id：与节点 id 同一套交互（点击复制），但工作流 id 决定磁盘文件名与
           所有引用，改不了。未保存的新工作流还没有 id，这一行就不显示。 -->
      <n-form-item v-if="workflowId" :label="t('workflow.editor.idLabel')">
        <button
          type="button"
          class="wip-id"
          data-test="workflow-id"
          :title="t('workflow.editor.idLabel')"
          @click="copyId"
        >
          {{ workflowId }}
        </button>
      </n-form-item>
      <n-form-item :label="t('workflow.editor.info.version')">
        <n-input
          :value="meta.version ?? ''"
          size="small"
          :placeholder="t('workflow.editor.info.versionPlaceholder')"
          @update:value="(value: string) => update({ version: value })"
        />
      </n-form-item>
      <n-form-item :label="t('workflow.editor.info.description')">
        <n-input
          :value="meta.description ?? ''"
          size="small"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :placeholder="t('workflow.editor.info.descriptionPlaceholder')"
          @update:value="(value: string) => update({ description: value })"
        />
      </n-form-item>
    </n-form>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NForm, NFormItem, NInput, useMessage } from 'naive-ui'

import type { WorkflowMeta } from './serializer'
import { log } from '@utils/logger'

/**
 * Workflow metadata form. Stateless: every keystroke emits a new meta object,
 * so the host owns the single source of truth (and its unsaved-changes flag).
 *
 * 节点数 / 连线数不在这里显示 —— 弹窗（`WorkflowInfoDialog`）在表单下方另起一行写
 * 「N 个节点 · M 条连线」，那是宿主传进来的只读摘要。
 */
const props = defineProps<{
  meta: WorkflowMeta
  /** 已保存工作流的 id；新建（尚未保存）时传空串，隐藏只读行。 */
  workflowId?: string
}>()

const emit = defineEmits<{
  (e: 'update:meta', value: WorkflowMeta): void
}>()

const { t } = useI18n()
const message = useMessage()

const nameMissing = computed(() => !String(props.meta?.name ?? '').trim())

const workflowId = computed(() => String(props.workflowId ?? '').trim())

/** 复制工作流 id：与节点 id 的 `.cd` 行同一套交互（点击即复制）。 */
async function copyId() {
  if (!workflowId.value) return
  try {
    await navigator.clipboard?.writeText(workflowId.value)
    message.success(t('workflow.editor.idCopied'))
  } catch (error) {
    log.warn('[WorkflowInfoPanel] clipboard unavailable', error)
  }
}

function update(patch: Partial<WorkflowMeta>) {
  emit('update:meta', { ...props.meta, ...patch })
}
</script>

<style scoped>
.workflow-info-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.wip-id {
  font-family: var(--app-font-mono, monospace);
  font-size: 12px;
  color: var(--app-text-dim);
  background: transparent;
  border: 1px dashed var(--app-card-border);
  border-radius: var(--radius-chip);
  padding: 2px 6px;
  cursor: pointer;
}

.wip-id:hover {
  color: var(--app-text-primary);
}
</style>
