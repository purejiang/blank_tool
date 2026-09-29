<template>
  <!-- 等宽日志/输出查看器：自己滚动 + overscroll 不甩给整页 + 可选的底部 meta。
       替代 DiagnosticsPage `.log-view`（同一份规则在 3 个 tab 里各写一遍）
       与 RunDetailDrawer `.rd-pre`（2 处）。

       注意：编辑器底部的「运行日志」是**结构化**日志（时间/节点/状态/文本 + tone
       着色），不是纯文本，那个仍由 RunLogPanel.vue 负责，只是改用全局 .app-tone--*。 -->
  <div class="app-log">
    <pre
      v-if="!empty"
      class="app-log-body"
      :style="{ maxHeight, minHeight }"
    >{{ content }}</pre>
    <div v-else class="app-log-placeholder" :style="{ minHeight }"><slot name="empty" /></div>
    <div v-if="$slots.meta" class="app-log-meta"><slot name="meta" /></div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 已拼好的文本（多行用 \n 连接） */
    content?: string
    /** 无内容：渲染 empty 槽而不是空 `<pre>` */
    empty?: boolean
    maxHeight?: string
    minHeight?: string
  }>(),
  { content: '', maxHeight: '400px', minHeight: '120px' },
)
</script>

<style scoped>
.app-log {
  min-width: 0;
}

.app-log-body {
  margin: var(--sp-8) 0 var(--sp-6);
  padding: var(--sp-12);
  overflow-y: auto;
  /* 列表/日志类控件自己滚到底，不把滚动链甩给整页 */
  overscroll-behavior: contain;
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-chip);
  font-family: var(--font-family-monospace);
  font-size: var(--fs-mono);
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}

.app-log-placeholder {
  display: flex;
  align-items: center;
  margin: var(--sp-8) 0 var(--sp-6);
  padding: var(--sp-12);
  border: var(--hairline);
  border-radius: var(--radius-chip);
  font-size: var(--fs-12);
  color: var(--text-muted);
}

.app-log-meta {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  font-size: var(--fs-meta);
  color: var(--text-dim);
}
</style>
