<template>
  <!--
    顶栏的文件动作簇（docs/08 §3·S2）：
      • 保存        —— 以工作流自己的名字/描述落盘（名称与描述在标题后的弹窗里改）
      • 导入工作流  —— 选一个工作流 JSON 读进当前画布

    「加载工作流」对话框的入口已删除（2026-09-29）：打开某个已保存工作流一律走工作流列表页
    （`/workflows/editor/:ref`，`:ref` 是工作流 id），编辑器里再挂一份列表只是第二条重复的路。
  -->
  <div class="wf-actions">
    <n-button size="small" data-test="workflow-save" @click="onSave">
      <template #icon>
        <AppIcon name="save" />
      </template>
      {{ t('workflow.editor.actions.save') }}
    </n-button>
    <n-button size="small" :loading="importing" data-test="workflow-import" @click="onImport">
      <template #icon>
        <AppIcon name="download" />
      </template>
      {{ t('workflow.editor.import.label') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, useMessage } from 'naive-ui'

import AppIcon from '@components/ui/AppIcon.vue'
import { log } from '@utils/logger'
import {
  deserializeWorkflow,
  type WorkflowDefinitionJSON,
} from './serializer'

/**
 * Canvas state emitted on import — the exact shape returned by the serializer's
 * deserializeWorkflow. The parent page applies it to the vue-flow canvas
 * (hydrating ToolNode ports on the way).
 */
export type WorkflowImportPayload = ReturnType<typeof deserializeWorkflow>

const props = defineProps<{
  /**
   * Snapshot of the current canvas as a WorkflowDefinition JSON, or null when
   * there is nothing to save (empty canvas).
   */
  getDefinition: () => WorkflowDefinitionJSON | null
  /**
   * Non-null when the canvas cannot be persisted (extra outgoing edges /
   * unwired 开始 — see the page's saveBlockedReason). Checked on click so the
   * guard message is the page's, not a raw backend error.
   */
  blockedReason?: () => string | null
}>()

const emit = defineEmits<{
  /** The page owns the definition identity (name/description in `meta`). */
  (e: 'save'): void
  (e: 'import', payload: WorkflowImportPayload, sourcePath: string): void
}>()

const { t } = useI18n()
const message = useMessage()

const importing = ref(false)

function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

function onSave() {
  const reason = props.blockedReason?.() ?? null
  if (reason) {
    message.error(`${t('workflow.editor.actions.blockedTitle')}: ${reason}`)
    return
  }
  if (!props.getDefinition()) {
    message.warning(t('workflow.editor.actions.emptyCanvas'))
    return
  }
  emit('save')
}

/**
 * Import a workflow JSON file INTO the canvas (replacing it).
 *
 * Only `*.json` files, one at a time: importing is a file → canvas operation,
 * so "several at once" has no meaning here (that is the workflow list page's
 * batch import into the template store).
 */
async function onImport() {
  if (importing.value) return
  importing.value = true
  try {
    const api = window.electronAPI
    if (!api || typeof api.selectFile !== 'function' || typeof api.readTextFile !== 'function') {
      throw new Error('file dialogs are unavailable in this environment')
    }
    const picked = await api.selectFile({
      title: t('workflow.editor.import.title'),
      properties: ['openFile'],
      filters: [{ name: 'JSON', extensions: ['json'] }],
    })
    if (!picked || picked.canceled) return
    const path = (picked.filePaths ?? []).find((candidate) => !!candidate)
    if (!path) return

    const read = await api.readTextFile(path)
    if (!read?.success || typeof read.content !== 'string') {
      throw new Error(read?.error || `failed to read ${path}`)
    }
    let json: any
    try {
      json = JSON.parse(read.content)
    } catch (err) {
      throw new Error(t('workflow.editor.import.invalidJson', { error: errMsg(err) }))
    }
    // Throws with every structural problem listed (serializer validation).
    const payload = deserializeWorkflow(json as WorkflowDefinitionJSON)
    emit('import', payload, path)
  } catch (error) {
    log.error('[WorkflowFileActions] import failed:', error)
    message.error(t('workflow.editor.import.failed', { error: errMsg(error) }))
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
/* Toolbar row fragment mounted in the page's `.we-top-actions`. */
.wf-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
