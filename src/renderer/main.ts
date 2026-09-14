import { createApp } from 'vue';
import { createPinia } from 'pinia';
import type { PiniaPluginContext } from 'pinia';
import naive from 'naive-ui';
import i18n from './i18n';
import { log } from '@utils/logger';
import App from './App.vue';
import router from './router';

// Fonts are loaded via Google Fonts in index.html

// Import app styles. Order = tokens → reset/base → 通用类 → 第三方覆盖
// （变量在计算期解析，顺序只影响同优先级冲突，后加载者胜）。
import './assets/styles/variables.css';
import './assets/styles/themes.css';
import './assets/styles/main.css';
import './assets/styles/common/components.css';
import './assets/styles/naive-overrides.css';

// Create Vue app
const app = createApp(App);

// Use Naive UI
app.use(naive);

type PersistOption = boolean | { key?: string; omit?: string[] };

const persistPlugin = ({ store, options }: PiniaPluginContext) => {
  const persist = (options as { persist?: PersistOption }).persist;
  if (!persist) return;

  const key = typeof persist === 'object' && persist.key
    ? persist.key
    : `pinia:${store.$id}`;

  // omit：这些键只在内存里存在，不进 localStorage。用于「每次启动应该重新
  // 检测」的大列表（如设备页的已安装应用），否则刷新后会拿旧数据自动回显。
  const omit = typeof persist === 'object' && Array.isArray(persist.omit)
    ? persist.omit
    : [];
  const withoutOmitted = (state: Record<string, any>): Record<string, any> => {
    if (!omit.length) return state;
    const out: Record<string, any> = {};
    for (const k of Object.keys(state)) {
      if (!omit.includes(k)) out[k] = state[k];
    }
    return out;
  };

  const raw = localStorage.getItem(key);
  if (raw) {
    try {
      store.$patch(withoutOmitted(JSON.parse(raw)));
    } catch {
      localStorage.removeItem(key);
    }
  }

  store.$subscribe(
    (_mutation, state) => {
      localStorage.setItem(key, JSON.stringify(withoutOmitted(state as unknown as Record<string, any>)));
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
    app.mount('#app');
    log.debug('Vue 应用挂载完成')
  } catch (error) {
    log.error('应用启动失败:', error);
    
    // 显示错误信息
    document.body.innerHTML = `
      <div style="
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100vh;
        background: #f5f5f5;
        font-family: Arial, sans-serif;
      ">
        <div style="
          text-align: center;
          padding: 2rem;
          background: white;
          border-radius: 8px;
          box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        ">
          <h2 style="color: #e74c3c; margin-bottom: 1rem;">App Initialization Failed</h2>
          <p style="color: #666; margin-bottom: 1rem;">${error.message}</p>
          <button onclick="location.reload()" style="
            padding: 0.5rem 1rem;
            background: #3498db;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
          ">Reload</button>
        </div>
      </div>
    `;
  }
}

launchApp();
