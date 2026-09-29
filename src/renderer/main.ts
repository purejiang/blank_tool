import { createApp } from 'vue';
import { createPinia } from 'pinia';
import type { PiniaPluginContext } from 'pinia';
import naive from 'naive-ui';
import i18n from './i18n';
import { log } from '@utils/logger';
import App from './App.vue';
import router from './router';
import { installIconSprite } from './assets/icons/sprite';

// Fonts are loaded via Google Fonts in index.html

// Import app styles
import './assets/styles/tokens.css';
import './assets/styles/main.css';
import './assets/styles/common/components.css';
import './assets/styles/themes.css';
import './assets/styles/common/responsive.css';
import './assets/styles/naive-overrides.css';
// 版式层：逐字取自 docs/ui-prompts/ui-preview.html（规则作用域挂在 .pv 下）
import './assets/styles/preview-layout.css';
import './assets/styles/ui.css';

// Create Vue app
const app = createApp(App);

// Use Naive UI
app.use(naive);

type PersistOption = boolean | { key?: string };

const persistPlugin = ({ store, options }: PiniaPluginContext) => {
  const persist = (options as { persist?: PersistOption }).persist;
  if (!persist) return;

  const key = typeof persist === 'object' && persist.key
    ? persist.key
    : `pinia:${store.$id}`;

  const raw = localStorage.getItem(key);
  if (raw) {
    try {
      store.$patch(JSON.parse(raw));
    } catch {
      localStorage.removeItem(key);
    }
  }

  store.$subscribe(
    (_mutation, state) => {
      localStorage.setItem(key, JSON.stringify(state));
    },
    { detached: true }
  );
};

// 创建Pinia实例
const pinia = createPinia();
pinia.use(persistPlugin);

// 使用Pinia
app.use(pinia);

// 使用Vue Router
app.use(router);

// 使用i18n
app.use(i18n);

// 启动应用
async function launchApp() {
  try {
    // 挂载Vue应用（App.vue会处理服务初始化和错误处理器设置）
    log.debug('Vue 应用准备挂载')
    installIconSprite();
app.mount('#app');
    log.debug('Vue 应用挂载完成')
  } catch (error) {
    log.error('应用启动失败:', error);
    
    // 显示错误信息（这里只能内联样式：Vue 没起来，但 tokens.css 已随模块加载，
    // 所以 --* 变量可用。别再写死 white / 黑阴影 / Arial —— 深色主题下会穿帮。）
    document.body.innerHTML = `
      <div style="
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100vh;
        background: var(--bg);
        font-family: var(--font-family-base);
      ">
        <div style="
          text-align: center;
          padding: 2rem;
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius-card);
          box-shadow: var(--shadow-card);
        ">
          <h2 style="color: var(--danger-text); margin-bottom: 1rem;">App Initialization Failed</h2>
          <p style="color: var(--text-muted); margin-bottom: 1rem;">${error.message}</p>
          <button onclick="location.reload()" style="
            padding: 0.5rem 1rem;
            background: var(--primary);
            color: var(--on-primary);
            border: none;
            border-radius: var(--radius-chip);
            cursor: pointer;
          ">Reload</button>
        </div>
      </div>
    `;
  }
}

launchApp();
