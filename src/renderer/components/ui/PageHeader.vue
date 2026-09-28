<template>
  <!-- 页面头：标题 + 一句话描述（+ 右侧区段切换/操作槽）。全站统一。 -->
  <header class="app-page-header" :class="{ 'app-page-header--row': row }">
    <div class="app-page-header-main">
      <h1>{{ title }}</h1>
      <p v-if="description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions || $slots.nav" class="app-page-header-side">
      <slot name="nav" />
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ title: string; description?: string; row?: boolean }>(), { row: true })
</script>

<style scoped>
.app-page-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
  flex: none;
}

.app-page-header-main {
  min-width: 0;
}

.app-page-header h1 {
  margin: 0;
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text);
}

.app-page-header p {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--text-muted);
}

.app-page-header-side {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}
</style>
