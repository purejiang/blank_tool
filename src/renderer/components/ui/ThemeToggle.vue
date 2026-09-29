<template>
  <!-- 主题切换：亮 / 暗 / 自动 三段控件。
       真源是 ThemeService（它写 html[data-theme]），同时落 localStorage 与
       appConfig.general.theme，保证与设置页同一份状态。键盘可用（原生 button）。 -->
  <div class="app-theme-toggle seg" role="group" :aria-label="t('settings.theme')">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="seg-item"
      :class="{ on: mode === option.value }"
      :aria-pressed="mode === option.value"
      @click="choose(option.value)"
    >
      {{ t(option.labelKey) }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import serviceManager from '@services/ServiceManager'
import unifiedApi from '@/api/unifiedApi'

export type ThemeMode = 'light' | 'dark' | 'auto'

const { t } = useI18n()

/**
 * 分段控件里用**短标签**：侧栏只有 ~150px 给三段，"跟随系统"（4 字）在 12px 下
 * 放不进 1/3 宽，会被折成两行（"跟随系" / "统"）。设计契约（docs/ui-prompts/
 * ui-preview.html 的 `.theme-box`）用的就是「自动」。设置页那个下拉继续用
 * `themeAuto`（空间充裕，写全更清楚）。
 */
const options: Array<{ value: ThemeMode; labelKey: string }> = [
  { value: 'light', labelKey: 'settings.themeLight' },
  { value: 'dark', labelKey: 'settings.themeDark' },
  { value: 'auto', labelKey: 'settings.themeAutoShort' },
]

const mode = ref<ThemeMode>('auto')

async function refresh() {
  const ts = await serviceManager.getService('theme')
  if (ts && typeof ts.getCurrentTheme === 'function') mode.value = ts.getCurrentTheme()
  else {
    try {
      const saved = localStorage.getItem('bt:theme-mode')
      if (saved === 'light' || saved === 'dark' || saved === 'auto') mode.value = saved
    } catch {
      /* localStorage 不可用时保持默认 auto */
    }
  }
}

async function choose(next: ThemeMode) {
  mode.value = next
  const ts = await serviceManager.getService('theme')
  if (ts && typeof ts.setTheme === 'function') await ts.setTheme(next)
  try {
    localStorage.setItem('bt:theme-mode', next)
  } catch {
    /* 忽略持久化失败 */
  }
  unifiedApi.getAPI()?.appConfig?.set('general.theme', next).catch(() => {})
}

onMounted(() => {
  void refresh()
})

defineExpose({ refresh })
</script>

<style scoped>
.seg {
  display: inline-flex;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  overflow: hidden;
  background: var(--surface);
}

.seg-item {
  flex: 1;
  padding: 5px 0;
  font: inherit;
  font-size: 12px;
  color: var(--text-muted);
  background: transparent;
  border: 0;
  border-right: 1px solid var(--border);
  cursor: pointer;
  /* 宁可被 .seg 的 overflow:hidden 裁掉，也不要折成两行。 */
  white-space: nowrap;
}

.seg-item:last-child {
  border-right: 0;
}

.seg-item:hover {
  background: var(--surface-alt);
  color: var(--text-secondary);
}

.seg-item.on {
  color: var(--primary);
  background: var(--primary-soft);
  font-weight: 600;
}
</style>
