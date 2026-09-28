<template>
  <!-- 桌面 / 平板侧边栏：品牌 → 一级导航 → 主题切换 + 状态栏。
       平板（768–1023）可折叠为 64px 图标栏；手机（<768）整条隐藏，改由底部 Tab 导航。 -->
  <aside class="side-nav" :class="{ collapsed }">
    <div class="side-brand">
      <img src="@assets/images/logo.svg" class="side-logo" alt="Blank Tool" />
      <span v-if="!collapsed" class="side-name">{{ t('app.title') }}</span>
      <button
        type="button"
        class="side-collapse"
        :aria-label="t('app.collapseSidebar')"
        :aria-expanded="!collapsed"
        @click="emit('toggle')"
      >
        <AppIcon :name="collapsed ? 'chevrons-r' : 'chevrons-l'" />
      </button>
    </div>

    <nav class="side-nav-list" :aria-label="t('app.primaryNav')">
      <button
        v-for="item in NAV_ITEMS"
        :key="item.key"
        type="button"
        class="side-nav-item"
        :class="{ on: item.key === activeKey }"
        :aria-current="item.key === activeKey ? 'page' : undefined"
        :title="collapsed ? t(item.labelKey) : undefined"
        @click="go(item.key)"
      >
        <AppIcon :name="item.icon" size="lg" />
        <span v-if="!collapsed" class="txt">{{ t(item.labelKey) }}</span>
      </button>
    </nav>

    <div class="side-foot">
      <div v-if="!collapsed" class="side-theme">
        <ThemeToggle />
      </div>
      <slot name="status" />
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppIcon from '@components/ui/AppIcon.vue'

import ThemeToggle from '@components/ui/ThemeToggle.vue'
import { NAV_ITEMS, activeNavKey } from './navItems'

defineProps<{ collapsed?: boolean }>()
const emit = defineEmits<{ (e: 'toggle'): void }>()

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const activeKey = computed(() => activeNavKey(route.path))

function go(key: string) {
  if (route.path !== key) void router.push(key)
}
</script>

<style scoped>
.side-nav {
  width: 220px;
  flex: none;
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--sidebar-border);
}

.side-nav.collapsed {
  width: 64px;
}

.side-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 14px;
  border-bottom: 1px solid var(--sidebar-border);
  flex: none;
}

.side-nav.collapsed .side-brand {
  flex-direction: column;
  gap: 8px;
  padding: 14px 0 10px;
}

.side-logo {
  width: 28px;
  height: 28px;
  flex: none;
}

.side-name {
  flex: 1;
  min-width: 0;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
}

.side-collapse {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex: none;
  color: var(--text-muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  cursor: pointer;
}

.side-collapse:hover {
  color: var(--text);
  background: var(--surface-alt);
}

.side-nav-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px;
}

.side-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 34px;
  padding: 0 10px;
  font: inherit;
  font-size: 13px;
  color: var(--text-secondary);
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  cursor: pointer;
}

.side-nav-item:hover {
  color: var(--text);
  background: var(--surface-alt);
}

.side-nav-item.on {
  color: var(--primary);
  background: var(--primary-soft);
  border-color: var(--primary-soft-border);
  font-weight: 600;
}

.side-nav.collapsed .side-nav-item {
  justify-content: center;
  padding: 0;
}

.side-foot {
  flex: none;
  padding: 8px 10px 0;
}

.side-theme {
  padding: 8px 0;
  border-top: 1px solid var(--sidebar-border);
}

/* 手机：整条侧栏隐藏（导航交给底部 Tab） */
@media (max-width: 767px) {
  .side-nav {
    display: none;
  }
}
</style>
