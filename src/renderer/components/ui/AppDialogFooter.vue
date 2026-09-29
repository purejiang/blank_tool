<template>
  <!-- 对话框页脚：右对齐的按钮组。
       替代 7 份逐字节相同的规则：envs-dialog-footer / plugins-dialog-footer /
       qd-actions / rid-footer / we-modal-footer / we-info-footer / wf-dialog-footer。 -->
  <div class="app-dialog-footer"><slot /></div>
</template>

<script setup lang="ts">
/** 放在 `n-modal` 的 `#footer` 槽里；主操作放最后（右端）。 */
</script>

<style scoped>
.app-dialog-footer {
  display: flex;
  gap: var(--gap-sm);
  justify-content: flex-end;
  flex-wrap: wrap;
}
</style>
