<template>
  <!-- Workflow-level identity (name / version / description).
       Lives in the right dock's 工作流 tab: the editor is the only place a
       workflow's name can be edited (there is no list page yet), and
       `template.save` uses it as the template name. -->
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
 * so the page owns the single source of truth (and its unsaved-changes flag).
 *
 * 节点数 / 连线数不在这里显示 —— 编辑器右栏头部的 `.cd`（preview 的 `.cfg-hd`）
 * 已经写了「N 个节点 · M 条连线」，同一栏里再来一遍是重复信息。
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
