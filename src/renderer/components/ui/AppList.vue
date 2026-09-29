<template>
  <!-- 列表容器：纵向堆叠 + 统一行距。
       替代 AboutPage `.info-grid` / DiagnosticsPage `.path-grid` / EnvsPage `.envs-rows`
       / PluginsPage `.plugins-rows` / TaskListView `.tl-rows` 这 5 份同名同体的规则。 -->
  <div class="app-list" :class="`app-list--${gap}`"><slot /></div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ gap?: 'xs' | 'sm' | 'md' }>(), { gap: 'xs' })
</script>

<style scoped>
.app-list {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.app-list--xs { gap: var(--gap-xs); } /* 6px — 紧凑行列表（行自带边框） */
.app-list--sm { gap: var(--gap-sm); } /* 8px */
.app-list--md { gap: var(--gap-md); } /* 12px — 卡片网格 */
</style>
