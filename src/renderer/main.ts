import { createApp } from 'vue';
import { createPinia } from 'pinia';
import type { PiniaPluginContext } from 'pinia';
import naive from 'naive-ui';
import App from './App.vue';
import router from './router';

// Import Inter font
import 'vfonts/Inter.css';
// Import Naive UI styles
import 'vfonts/FiraCode.css';

// Import app styles
import './assets/styles/main.css';
import './assets/styles/common/components.css';
import './assets/styles/themes.css';
import './assets/styles/common/responsive.css';
import './assets/variables.css';

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

// 启动应用
async function launchApp() {
  try {
    // 挂载Vue应用（App.vue会处理服务初始化和错误处理器设置）
    console.log('Vue应用启动');
    app.mount('#app');
    
    console.log('Vue应用启动完成');
  } catch (error) {
    console.error('应用启动失败:', error);
    
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
          <h2 style="color: #e74c3c; margin-bottom: 1rem;">应用初始化失败</h2>
          <p style="color: #666; margin-bottom: 1rem;">${error.message}</p>
          <button onclick="location.reload()" style="
            padding: 0.5rem 1rem;
            background: #3498db;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
          ">重新加载</button>
        </div>
      </div>
    `;
  }
}

launchApp();
