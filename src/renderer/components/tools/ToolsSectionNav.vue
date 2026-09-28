<template>
  <!-- 页面头右侧的区段切换（docs/08 §2.1 工具模块）：工具 / 环境 / 插件各是一个
       独立页面，靠这里互相跳转，共用侧边栏的一个「工具」导航项。 -->
  <div class="tools-section-nav">
    <button
      v-for="section in sections"
      :key="section.key"
      type="button"
      class="tsn-item"
      :class="{ 'tsn-item--active': section.key === active }"
      @click="go(section.key)"
    >
      {{ t(section.labelKey) }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

/**
 * 工具模块的三页区段切换。
 *
 * 与 `/tasks?tab=` 有意不同：那里是同一任务对象的两种视图，这里是三类不同
 * 对象（工具描述符 / 运行环境 / 插件清单），各自有独立的列表、工具栏与空态。
 */
type SectionKey = 'tools' | 'env' | 'plugins'

defineProps<{
  active: SectionKey
}>()

const { t } = useI18n()
const router = useRouter()

const sections: Array<{ key: SectionKey; labelKey: string; path: string }> = [
  { key: 'tools', labelKey: 'tools.sections.tools', path: '/tools' },
  { key: 'env', labelKey: 'tools.sections.env', path: '/tools/env' },
  { key: 'plugins', labelKey: 'tools.sections.plugins', path: '/tools/plugins' },
]

function go(key: SectionKey) {
  const target = sections.find((section) => section.key === key)
  if (target) void router.push(target.path)
}
</script>

<style scoped>
.tools-section-nav {
  display: flex;
  flex-shrink: 0;
  gap: 2px;
  padding: 2px;
  background: var(--app-storage-bg);
  border-radius: var(--radius-control);
}

.tsn-item {
  padding: 4px 12px;
  font: inherit;
  font-size: 12px;
  color: var(--app-text-secondary);
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: var(--radius-chip);
}

.tsn-item:hover {
  color: var(--app-text-primary);
}

.tsn-item--active {
  color: var(--app-text-primary);
  background: var(--app-card-bg);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
}
</style>
