<template>
  <!-- 手机底部 Tab：四项一级导航（首页/工作流/任务/工具/设置），触达区 ≥44px。
       ≥768 隐藏（那时用侧边栏）。 -->
  <nav class="bottom-tabs" :aria-label="t('app.primaryNav')">
    <button
      v-for="item in NAV_ITEMS"
      :key="item.key"
      type="button"
      class="bottom-tab"
      :class="{ on: item.key === activeKey }"
      :aria-current="item.key === activeKey ? 'page' : undefined"
      @click="go(item.key)"
    >
      <AppIcon :name="item.icon" size="lg" />
      <span class="bottom-tab-label">{{ t(item.labelKey) }}</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import AppIcon from '@components/ui/AppIcon.vue'
import { NAV_ITEMS, activeNavKey } from './navItems'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const activeKey = computed(() => activeNavKey(route.path))

function go(key: string) {
  if (route.path !== key) void router.push(key)
}
</script>

<style scoped>
.bottom-tabs {
  display: none;
  flex: none;
  background: var(--surface);
  border-top: 1px solid var(--border);
}

.bottom-tab {
  flex: 1;
  min-height: 48px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 6px 2px;
  font: inherit;
  font-size: 10.5px;
  color: var(--text-muted);
  background: transparent;
  border: 0;
  cursor: pointer;
}

.bottom-tab.on {
  color: var(--primary);
  background: var(--primary-soft);
  font-weight: 600;
}

.bottom-tab-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

@media (max-width: 767px) {
  .bottom-tabs {
    display: flex;
  }
}
</style>
