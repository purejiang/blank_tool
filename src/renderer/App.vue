<template>
  <n-config-provider :theme="currentTheme" :theme-overrides="themeOverrides" :locale="locale">
    <n-notification-provider placement="bottom-right">
      <n-message-provider>
        <div id="app" class="pv app-shell">
          <LoadingScreen v-if="isLoading" :progress="progress" :step="step" :time="time"
            :error="error" :retry-count="retryCount" :max-retries="maxRetries" @retry="retry" />
          <template v-else>
            <!-- 外壳（docs/ui-prompts/00-shell.md 的版式）：220/64 侧栏 + 主导区 -->
            <aside class="sider" :class="{ collapsed: sidebarCollapsed }">
              <div class="brand">
                <img src="@assets/images/logo.svg" class="logo" alt="Blank Tool" />
                <span class="brand-name">{{ t('app.title') }}</span>
                <button type="button" class="iconbtn" :title="t('app.collapseSidebar')" @click="sidebarCollapsed = !sidebarCollapsed">
                  <n-icon size="13"><ChevronsLeft v-if="!sidebarCollapsed" /><ChevronsRight v-else /></n-icon>
                </button>
              </div>
              <nav class="nav">
                <button
                  v-for="item in menuOptions"
                  :key="item.key"
                  type="button"
                  class="nav-item"
                  :class="{ on: item.key === activeMenuKey }"
                  :aria-current="item.key === activeMenuKey ? 'page' : undefined"
                  @click="handleMenuSelect(String(item.key))"
                >
                  <n-icon size="18"><component :is="item.icon" /></n-icon>
                  <span class="txt">{{ item.label }}</span>
                </button>
              </nav>
              <div class="sider-foot">
                <!-- 底部主题切换（docs/08 §2.2）：与设计稿同款 .seg 分段控件 -->
                <div class="theme-box">
                  <div class="seg">
                    <button
                      v-for="option in themeOptions"
                      :key="option.value"
                      type="button"
                      :class="{ on: themeMode === option.value }"
                      :aria-pressed="themeMode === option.value"
                      @click="chooseTheme(option.value)"
                    >
                      {{ t(option.labelKey) }}
                    </button>
                  </div>
                </div>
                <StatusBar :collapsed="sidebarCollapsed" />
              </div>
            </aside>
            <main class="main">
              <n-dialog-provider><router-view /></n-dialog-provider>
              <QuitDialog />
              <Notification />
            </main>
          </template>
        </div>
      </n-message-provider>
    </n-notification-provider>
  </n-config-provider>
</template>
<script setup lang="ts">
import { ref, computed, provide, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { darkTheme, NIcon, zhCN, enUS, type GlobalTheme } from 'naive-ui'
import { Settings, ChevronsLeft, ChevronsRight, Workflow, Puzzle, ListTodo } from 'lucide-vue-next'
import StatusBar from '@components/common/StatusBar.vue'
import QuitDialog from '@components/QuitDialog.vue'
import Notification from '@components/common/Notification.vue'
import LoadingScreen from '@components/LoadingScreen.vue'
import { useAppBootstrap } from '@composables/useAppBootstrap'
import { selectOverrides } from './theme/overrides'
import serviceManager from '@services/ServiceManager'
import unifiedApi from './api/unifiedApi'
import { persistLocale } from './i18n'
const router = useRouter()
const route = useRoute()
const { t, locale: i18nLocale } = useI18n()
const currentTheme = ref<GlobalTheme | null>(darkTheme)
const { isLoading, progress, step, time, error, retryCount, maxRetries, retry } = useAppBootstrap(currentTheme)
const themeOverrides = computed(() => selectOverrides(currentTheme.value))
const sidebarCollapsed = ref(false)
/**
 * 一级导航（docs/08 §2.2：工作流 / 任务 / 工具 / 设置）。`activeMenuKey` 按
 * **路径前缀**匹配，这样二级页（`/workflows/editor/x`、`/tasks/editor/x`、
 * `/tools/env`）也能点亮所属模块。`/about`、`/diagnostics` 是二级路由，不进
 * 侧边栏（从设置页进入）。
 */
const MENU_KEYS = ['/workflows', '/tasks', '/tools', '/settings'] as const
const activeMenuKey = computed(
  () => MENU_KEYS.find((key) => route.path === key || route.path.startsWith(`${key}/`)) ?? '',
)
const locale = computed(() => i18nLocale.value === 'zh-CN' ? zhCN : enUS)
const setLocale = (lang: string) => {
  i18nLocale.value = lang
  persistLocale(lang)
  unifiedApi.getAPI()?.appConfig?.set('language', lang).catch(() => {})
}
const setTheme = async (mode: string) => {
  const ts = await serviceManager.getService('theme')
  if (ts) {
    currentTheme.value = await ts.setTheme(mode)
    try { localStorage.setItem('bt:theme', ts.getActualTheme()) } catch {}
  }
}
provide('setLocale', setLocale); provide('setTheme', setTheme); provide('getCurrentTheme', () => currentTheme.value)
/** 一级导航项（图标是组件本身，模板里用 `<component :is>` 渲染）。 */
const menuOptions = computed(() => [
  { label: t('nav.workflows'), key: '/workflows', icon: Workflow },
  { label: t('nav.tasks'), key: '/tasks', icon: ListTodo },
  { label: t('nav.tools'), key: '/tools', icon: Puzzle },
  { label: t('nav.settings'), key: '/settings', icon: Settings },
])

// ---- 底部主题切换（docs/08 §2.2）--------------------------------------------
// 模式由 ThemeService 持有（`getCurrentTheme()`）；持久化键与设置页共用
// `general.theme`，两边改动都会落到同一处。
type ThemeMode = 'auto' | 'light' | 'dark'
const themeMode = ref<ThemeMode>('auto')
const themeOptions: Array<{ value: ThemeMode; labelKey: string }> = [
  { value: 'light', labelKey: 'settings.themeLight' },
  { value: 'dark', labelKey: 'settings.themeDark' },
  { value: 'auto', labelKey: 'settings.themeAuto' },
]

async function refreshThemeMode() {
  const ts = await serviceManager.getService('theme')
  if (ts && typeof ts.getCurrentTheme === 'function') themeMode.value = ts.getCurrentTheme()
}

async function chooseTheme(mode: ThemeMode) {
  themeMode.value = mode
  await setTheme(mode)
  // 与设置页写同一个配置键，避免两处状态漂移
  unifiedApi.getAPI()?.appConfig?.set('general.theme', mode).catch(() => {})
}

onMounted(() => {
  void refreshThemeMode()
})

const handleMenuSelect = (key: string) => { router.push(key) }
</script>
<style scoped>
/* 版式来自 preview-layout.css（.pv 作用域）；这里只补外壳需要的高度约束 */
.pv.app-shell { height: 100vh; }
</style>
