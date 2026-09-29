<template>
  <!-- 工具栏：左区（状态文字 / 筛选器 / 主操作）+ 右区（动作，永远贴右）。
       替代全仓 5 份 `*-toolbar` 与 5 份逐字节相同的 `*-status-row`，
       以及那些为了把刷新推到最右而塞进来的 `<span class="xx-grow" />` 占位。 -->
  <div class="app-toolbar">
    <div class="app-toolbar-main"><slot /></div>
    <div v-if="$slots.actions" class="app-toolbar-actions"><slot name="actions" /></div>
  </div>
</template>

<script setup lang="ts">
/**
 * 工具栏布局。**不带外边距** —— 页面根容器已经用 `gap` 控制纵向间距，
 * 再给工具栏加 margin-bottom 会变成双倍间距（旧代码里两种写法都有）。
 */
</script>

<style scoped>
.app-toolbar {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  flex: none;
  min-width: 0;
}

.app-toolbar-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
}

.app-toolbar-actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  margin-left: auto;
}
</style>
