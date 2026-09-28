<template>
  <!-- 应用外壳：桌面/平板 = 侧边栏 + 内容区；手机 = 顶栏 + 内容区 + 底部 Tab。
       折叠状态持久化在 localStorage（平板 768–1023 常用）。 -->
  <div class="app-shell">
    <SideNav :collapsed="collapsed" @toggle="toggleCollapsed">
      <template #status>
        <StatusBar :collapsed="collapsed" />
      </template>
    </SideNav>

    <div class="app-shell-main">
      <TopBar :title="topBarTitle">
        <template #actions>
          <slot name="topbar-actions" />
        </template>
      </TopBar>
      <main class="app-shell-content" :class="{ 'app-shell-content--flush': flush }">
        <slot />
      </main>
      <BottomTabBar />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import SideNav from './SideNav.vue'
import TopBar from './TopBar.vue'
import BottomTabBar from './BottomTabBar.vue'
import StatusBar from '@components/common/StatusBar.vue'

withDefaults(
  defineProps<{
    /** 手机顶栏显示的标题（通常传当前页标题） */
    topBarTitle?: string
    /** 内容区不要内边距（编辑器这类自带满屏布局的页面） */
    flush?: boolean
  }>(),
  { flush: false },
)

const COLLAPSE_KEY = 'bt:sidenav-collapsed'
const collapsed = ref(false)

function toggleCollapsed() {
  collapsed.value = !collapsed.value
  try {
    localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0')
  } catch {
    /* 忽略持久化失败 */
  }
}

onMounted(() => {
  try {
    collapsed.value = localStorage.getItem(COLLAPSE_KEY) === '1'
  } catch {
    collapsed.value = false
  }
})
</script>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
}

.app-shell-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.app-shell-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

/* 页面自带宽高布局时用 flush（例如工作流编辑器） */
.app-shell-content--flush {
  overflow: hidden;
}
</style>
