<template>
  <!-- 手机顶栏：品牌 + 当前页标题（+ 页面主操作槽）。≥768 隐藏。 -->
  <header class="top-bar">
    <img src="@assets/images/logo.svg" class="top-logo" alt="" aria-hidden="true" />
    <span class="top-title">{{ title || t('app.title') }}</span>
    <div class="top-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ title?: string }>()

const { t } = useI18n()
</script>

<style scoped>
.top-bar {
  display: none;
  align-items: center;
  gap: 10px;
  flex: none;
  padding: 10px 14px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.top-logo {
  width: 24px;
  height: 24px;
  flex: none;
}

.top-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}

@media (max-width: 767px) {
  .top-bar {
    display: flex;
  }
}
</style>
