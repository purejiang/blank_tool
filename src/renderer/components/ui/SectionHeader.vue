<template>
  <!-- 卡片/面板的小节标题：图标 + 标题 + 右侧动作。
       替代 AboutPage / DiagnosticsPage / SettingsPage 三份本地 `.section-header`
       + `.section-title`（margin-bottom 还漂成 12px / 14px 两种），
       以及 RunDetailDrawer `.rd-section-title`、ToolsPage `.tc-detail-title`。 -->
  <div class="app-section-header">
    <span v-if="$slots.icon" class="app-section-header-icon"><slot name="icon" /></span>
    <span class="app-section-header-title"><slot /></span>
    <div v-if="$slots.actions" class="app-actions app-section-header-actions"><slot name="actions" /></div>
  </div>
</template>

<script setup lang="ts">
/** 只做排版；图标颜色由调用方通过 AppIcon 的 style 或 `.app-tone--*` 指定。 */
</script>

<style scoped>
.app-section-header {
  display: flex;
  align-items: center;
  gap: var(--sp-10);
  margin-bottom: var(--gap-md);
  min-width: 0;
}

.app-section-header-icon {
  flex: none;
  display: inline-flex;
  align-items: center;
}

.app-section-header-title {
  font-size: var(--fs-section-title);
  font-weight: 600;
  color: var(--text);
}

.app-section-header-actions {
  margin-left: auto;
}
</style>
