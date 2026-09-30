<template>
  <!-- M2 导入结果报告（docs/08 §4）：逐条列出成功/失败与原因。
       `workflow.import_path` 与 `tool.import_pack` 的条目形状不同，这里按可选字段
       兼容渲染（工作流：file/name/status/reason/renamed_from；描述符：name/status/reason/warnings）。 -->
  <n-modal
    v-model:show="visible"
    preset="card"
    :title="title"
    :style="{ width: '560px' }"
    data-test="import-report-dialog"
  >
    <div v-if="report" class="irp-summary">
      <n-tag :type="report.failed > 0 ? 'warning' : 'success'" size="small" :bordered="false">
        {{ t('workflows.import.imported', { count: report.imported }) }}
      </n-tag>
      <!-- `tool.import_pack` 的条目多一个 updated（同名覆盖） -->
      <n-tag v-if="report.updated" size="small" :bordered="false">
        {{ t('tools.importUpdated', { count: report.updated }) }}
      </n-tag>
      <n-tag v-if="report.failed > 0" type="error" size="small" :bordered="false">
        {{ report.failed }}
      </n-tag>
    </div>

    <div v-if="report" class="irp-list">
      <div
        v-for="(entry, index) in report.results"
        :key="`${entry.name || entry.file || index}`"
        class="irp-row"
        :class="`irp-row--${entry.status}`"
      >
        <span class="irp-row-name">{{ entry.name || entry.file || '—' }}</span>
        <span class="irp-row-status">{{ entry.status }}</span>
        <div class="irp-row-detail">
          <div v-if="entry.renamed_from" class="irp-row-hint">
            {{ t('workflows.import.renamedFrom', { stem: entry.renamed_from }) }}
          </div>
          <div v-if="entry.reason" class="irp-row-reason">{{ entry.reason }}</div>
          <div v-for="(warning, wi) in entry.warnings ?? []" :key="wi" class="irp-row-hint">
            {{ warning }}
          </div>
        </div>
      </div>
    </div>

    <div v-else class="irp-empty">{{ t('workflows.import.none') }}</div>

    <template #footer>
      <div class="irp-footer">
        <n-button size="small" type="primary" @click="visible = false">
          {{ t('workflow.editor.actions.close') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NModal, NTag } from 'naive-ui'

/** One import report entry — a superset of the workflow/descriptor shapes. */
export interface ImportReportEntry {
  status: string
  file?: string
  name?: string
  reason?: string
  renamed_from?: string
  warnings?: string[]
}

/** `workflow.import_path` / `tool.import_pack` report shape. */
export interface ImportReport {
  ok: boolean
  imported: number
  failed: number
  results: ImportReportEntry[]
  /** `tool.import_pack` only: entries that overwrote an existing descriptor. */
  updated?: number
}

/**
 * M2: share the "what got imported and what failed, and why" report between
 * workflow import (`workflow.import_path`) and descriptor import
 * (`tool.import_pack`).
 */
const props = defineProps<{
  show: boolean
  report: ImportReport | null
  title: string
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
}>()

const { t } = useI18n()

const visible = computed({
  get: () => props.show,
  set: (value: boolean) => emit('update:show', value),
})
</script>

<style scoped>
.irp-summary {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.irp-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 360px;
  overflow-y: auto;
  /* 内部列表自己滚，滚到底不带动整页 */
  overscroll-behavior: contain;
}

.irp-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
  padding: 7px 9px;
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-chip);
}

.irp-row--failed {
  border-color: var(--app-red);
}

.irp-row-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary);
  word-break: break-all;
}

.irp-row-status {
  font-size: 10px;
  text-transform: uppercase;
  color: var(--app-text-dim);
}

.irp-row--failed .irp-row-status {
  color: var(--app-red);
}

.irp-row-detail {
  flex-basis: 100%;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.irp-row-reason {
  font-size: 11px;
  line-height: 1.45;
  color: var(--app-red);
}

.irp-row-hint {
  font-size: 11px;
  color: var(--app-text-dim);
}

.irp-empty {
  font-size: 12px;
  color: var(--app-text-muted);
}

.irp-footer {
  display: flex;
  justify-content: flex-end;
}
</style>
