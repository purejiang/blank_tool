<template>
  <!-- 页面头：标题 + 一句话描述（+ 左侧前置区 + 右侧区段切换/操作槽）。全站统一。
       这是应用里**唯一**的页面头：9 个页面此前各自抄了一份 `.page-header` +
       `.page-title`(22px) + `.page-subtitle`(13px)，而设计契约与 PageHeader 是
       19px / 12.5px —— 同一语义三种字号。 -->
  <header class="app-page-header" :class="{ 'app-page-header--row': row }">
    <div v-if="$slots.lead" class="app-page-header-lead"><slot name="lead" /></div>
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
  gap: var(--gap-lg);
  margin-bottom: var(--gap-lg);
  flex: none;
}

.app-page-header-lead {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
}

.app-page-header-main {
  min-width: 0;
}

.app-page-header h1 {
  margin: 0;
  font-size: var(--fs-page-title);
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text);
}

.app-page-header p {
  margin: var(--sp-4) 0 0;
  font-size: var(--fs-page-desc);
  color: var(--text-dim);
}

.app-page-header-side {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  flex: none;
}
</style>
