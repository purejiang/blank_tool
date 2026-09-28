<template>
  <n-config-provider :theme="currentTheme" :theme-overrides="themeOverrides" :locale="locale">
    <n-notification-provider placement="bottom-right">
      <n-message-provider>
        <div id="app" class="pv app-root">
          <LoadingScreen
            v-if="isLoading"
            :progress="progress"
            :step="step"
            :time="time"
            :error="error"
            :retry-count="retryCount"
            :max-retries="maxRetries"
            @retry="retry"
          />
          <!-- 外壳：桌面/平板侧边栏，手机顶栏 + 底部 Tab（components/shell） -->
          <AppShell v-else :top-bar-title="pageTitle" :flush="isEditorRoute">
            <n-dialog-provider><router-view /></n-dialog-provider>
            <QuitDialog />
            <Notification />
          </AppShell>
        </div>
      </n-message-provider>
    </n-notification-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, provide, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { darkTheme, zhCN, enUS, type GlobalTheme } from 'naive-ui'

import AppShell from '@components/shell/AppShell.vue'
import QuitDialog from '@components/QuitDialog.vue'
import Notification from '@components/common/Notification.vue'
import LoadingScreen from '@components/LoadingScreen.vue'
import { NAV_ITEMS, activeNavKey } from '@components/shell/navItems'
import { useAppBootstrap } from '@composables/useAppBootstrap'
import { selectOverrides } from './theme/overrides'
import serviceManager from '@services/ServiceManager'
import unifiedApi from './api/unifiedApi'
import { persistLocale } from './i18n'

const route = useRoute()
const { t, locale: i18nLocale } = useI18n()

const currentTheme = ref<GlobalTheme | null>(darkTheme)
const { isLoading, progress, step, time, error, retryCount, maxRetries, retry } = useAppBootstrap(currentTheme)
const themeOverrides = computed(() => selectOverrides(currentTheme.value))

const locale = computed(() => (i18nLocale.value === 'zh-CN' ? zhCN : enUS))

/** 手机顶栏标题：一级模块用 i18n 文案，其余回落到路由 meta.title。 */
const pageTitle = computed(() => {
  const navKey = activeNavKey(route.path)
  const navItem = NAV_ITEMS.find((item) => item.key === navKey)
  if (navItem) return t(navItem.labelKey)
  const metaTitle = route.meta?.title
  return typeof metaTitle === 'string' ? metaTitle : t('app.title')
})

/** 编辑器自带满屏三栏布局，内容区不要内边距/滚动 */
const isEditorRoute = computed(() => route.path.startsWith('/workflows/editor'))

const setLocale = (lang: string) => {
  i18nLocale.value = lang
  persistLocale(lang)
  unifiedApi.getAPI()?.appConfig?.set('language', lang).catch(() => {})
}

const setTheme = async (mode: string) => {
  const ts = await serviceManager.getService('theme')
  if (ts) {
    currentTheme.value = await ts.setTheme(mode)
    try {
      localStorage.setItem('bt:theme', ts.getActualTheme())
    } catch {
      /* 忽略持久化失败 */
    }
  }
}

provide('setLocale', setLocale)
provide('setTheme', setTheme)
provide('getCurrentTheme', () => currentTheme.value)
</script>

<style scoped>
.app-root {
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
}
</style>
