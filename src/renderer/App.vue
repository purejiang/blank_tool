<template>
  <n-config-provider :theme="currentTheme" :theme-overrides="themeOverrides" :locale="locale">
    <n-notification-provider placement="bottom-right">
      <n-message-provider>
        <div id="app">
          <LoadingScreen v-if="isLoading" :progress="progress" :step="step" :time="time"
            :error="error" :retry-count="retryCount" :max-retries="maxRetries" @retry="retry" />
          <n-layout v-else has-sider class="app-layout">
            <n-layout-sider bordered collapse-mode="width" :collapsed-width="64" :width="220"
              :collapsed="sidebarCollapsed" :native-scrollbar="false" class="app-sider">
              <div class="sider-inner">
                <div class="sider-brand" :class="{ collapsed: sidebarCollapsed }">
                  <img src="@assets/images/logo.svg" class="brand-logo" alt="Blank Tool" />
                  <span v-if="!sidebarCollapsed" class="brand-text">{{ $t('app.title') }}</span>
                  <div class="brand-collapse">
                    <n-button quaternary circle size="tiny" @click="sidebarCollapsed = !sidebarCollapsed">
                      <template #icon>
                        <n-icon size="16"><ChevronsLeft v-if="!sidebarCollapsed" /><ChevronsRight v-else /></n-icon>
                      </template>
                    </n-button>
                  </div>
                </div>
                <n-menu :value="activeMenuKey" :collapsed="sidebarCollapsed" :collapsed-width="64"
                  :collapsed-icon-size="22" :options="menuOptions" :render-label="renderMenuLabel"
                  @update:value="handleMenuSelect" class="sider-menu" />
                <StatusBar :collapsed="sidebarCollapsed" />
              </div>
            </n-layout-sider>
            <n-layout>
              <n-layout-content class="main-content">
                <n-dialog-provider><router-view /></n-dialog-provider>
                <QuitDialog />
                <Notification />
              </n-layout-content>
            </n-layout>
          </n-layout>
        </div>
      </n-message-provider>
    </n-notification-provider>
  </n-config-provider>
</template>
<script setup lang="ts">
import { ref, h, computed, provide, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { darkTheme, NIcon, zhCN, enUS, type GlobalTheme, type MenuOption } from 'naive-ui'
import { Package, Settings, ChevronsLeft, ChevronsRight, Info, Activity, Smartphone, Bot, Puzzle } from 'lucide-vue-next'
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
const activeMenuKey = ref(route.path || '/package')
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
const renderMenuLabel = (option: MenuOption) => option.label as string
const renderIcon = (icon: any) => () => h(NIcon, null, { default: () => h(icon) })
const menuOptions = computed<MenuOption[]>(() => [
  { label: t('nav.package'), key: '/package', icon: renderIcon(Package) },
  { label: t('nav.device'), key: '/device', icon: renderIcon(Smartphone) },
  { label: t('nav.automation'), key: '/automation', icon: renderIcon(Bot) },
  { label: t('nav.plugins'), key: '/plugins', icon: renderIcon(Puzzle) },
  { label: t('nav.settings'), key: '/settings', icon: renderIcon(Settings) },
  { label: t('diagnostics.title'), key: '/diagnostics', icon: renderIcon(Activity) },
  { label: t('nav.about'), key: '/about', icon: renderIcon(Info) },
])
const handleMenuSelect = (key: string) => { activeMenuKey.value = key; router.push(key) }
watch(() => route.path, (p) => { if (p !== '/') activeMenuKey.value = p }, { immediate: true })
</script>
<style scoped>
.app-layout { height: 100vh; }
.app-sider { background: var(--app-sidebar-bg); }
.sider-inner { display: flex; flex-direction: column; height: 100%; }
.sider-brand { display: flex; align-items: center; gap: 10px; padding: 20px 18px 16px; border-bottom: 1px solid var(--app-sidebar-border); flex-shrink: 0; }
.brand-collapse { margin-left: auto; } .brand-logo { width: 28px; height: 28px; flex-shrink: 0; }
.sider-brand.collapsed { justify-content: center; flex-direction: column; gap: 8px; padding: 16px 0 12px; }
.sider-brand.collapsed .brand-collapse { margin-left: 0; }
.brand-text { font-family: Inter, sans-serif; font-size: 16px; font-weight: 700; color: var(--app-text-primary); letter-spacing: -0.02em; }
.sider-menu { flex: 1; overflow-y: auto; } .main-content { padding: 24px; background: var(--app-body-bg); height: 100vh; overflow-y: auto; }
</style>
