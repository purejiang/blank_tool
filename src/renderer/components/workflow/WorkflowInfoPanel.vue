<template>
  <!-- Workflow-level identity (name / version / description).
       Rendered inside WorkflowInfoDialog (opened from the editor's top bar); it
       used to live permanently in the right dock. `template.save` uses the name
       as the template name, hence the required-field validation. -->
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
import { NForm, NFormItem, NInput } from 'naive-ui'

import type { WorkflowMeta } from './serializer'

/**
 * Workflow metadata form. Stateless: every keystroke emits a new meta object,
 * so the host owns the single source of truth (and its unsaved-changes flag).
 *
 * 节点数 / 连线数不在这里显示 —— 弹窗（`WorkflowInfoDialog`）在表单下方另起一行写
 * 「N 个节点 · M 条连线」，那是宿主传进来的只读摘要。
 */
const props = defineProps<{
  meta: WorkflowMeta
}>()

const emit = defineEmits<{
  (e: 'update:meta', value: WorkflowMeta): void
}>()

const { t } = useI18n()

const nameMissing = computed(() => !String(props.meta?.name ?? '').trim())

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
</style>
