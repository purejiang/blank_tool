<template>
  <!-- 描述列表：label + value（+ 行内动作）逐行排布。
       合并 AboutPage `.info-row`、DiagnosticsPage `.path-row`/`.health-row`、
       SettingsPage `.storage-row`、RunDetailDrawer `.rd-kv-row`/`.rd-output-row`
       这 5 套「一行一个键值」的实现。 -->
  <div class="app-kv"><slot /></div>
</template>

<script setup lang="ts">
/** 容器：只负责纵向堆叠与行距（与 `AppList gap="xs"` 同档，独立成对更顺手）。 */
</script>

<style scoped>
.app-kv {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  min-width: 0;
}
</style>
