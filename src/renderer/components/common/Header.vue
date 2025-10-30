<template>
  <div class="header-nav">
    <div class="header-logo">
      <span class="header-logo-icon">🤖</span>
      Android 开发工具
    </div>
    <div class="header-tabs">
      <router-link 
        v-for="tab in tabs" 
        :key="tab.route"
        :to="tab.route"
        class="header-tab" 
        active-class="active"
      >
        <span class="header-tab-icon">{{ tab.icon }}</span>
        {{ tab.title }}
      </router-link>
    </div>
  </div>
</template>

<script>
import { ref } from 'vue'

export default {
  name: 'Header',
  setup() {
    const tabs = ref([
      { route: '/apk', icon: '📦', title: 'APK 工具' },
      { route: '/device', icon: '📱', title: '设备管理' },
      { route: '/settings', icon: '⚙️', title: '设置' }
    ])

    return {
      tabs
    }
  }
}
</script>

<style scoped>
.header-nav {
    display: flex;
    align-items: center;
    height: 60px;
    padding: 0 var(--spacing-lg);
    background-color: var(--bg-primary);
    border-bottom: 1px solid var(--border-color);
}

.header-logo {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    margin-right: var(--spacing-xl);
    font-size: var(--font-size-lg);
    font-weight: 600;
    color: var(--text-primary);
    text-decoration: none;
}

.header-logo-icon {
    font-size: 1.5rem;
}

.header-tabs {
    display: flex;
    align-items: center;
    gap: var(--spacing-xs);
    flex: 1;
}

.header-tab {
    display: flex;
    align-items: center;
    gap: var(--spacing-xs);
    padding: var(--spacing-sm) var(--spacing-md);
    border: none;
    background: transparent;
    color: var(--text-secondary);
    font-size: var(--font-size-sm);
    font-weight: 500;
    cursor: pointer;
    border-radius: var(--border-radius);
    transition: var(--transition-base);
    position: relative;
}

.header-tab:hover {
    color: var(--text-primary);
    background-color: var(--bg-secondary);
}

.header-tab.active {
    color: var(--primary-color);
    background-color: rgba(0, 123, 255, 0.1);
}

.header-tab.active::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 0;
    right: 0;
    height: 2px;
    background-color: var(--primary-color);
}

.header-tab-icon {
    font-size: 1rem;
}
</style>