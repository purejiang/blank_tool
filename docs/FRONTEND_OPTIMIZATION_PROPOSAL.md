# Blank Tool 前端架构优化建议 v1.0

## 1. 概述

本文档聚焦于 Blank Tool 前端部分的架构优化，涵盖 Electron 主进程 (`src/main`) 和渲染进程 (`src/renderer`)。当前前端架构基于 Vue 3 和 Vite，结构清晰，模块化程度较好。然而，在**状态管理一致性**、**进程间职责划分**、**组件性能**和**代码复用**方面仍有提升空间。

本次优化的目标是：
- **统一状态管理模型:** 整合主进程与渲染进程的状态，确保数据流清晰、单一。
- **明确进程职责:** 优化主进程和渲染进程的责任分工，减少冗余代码。
- **提升渲染性能:** 针对大数据量组件和长列表进行性能优化。
- **加强代码组织与复用:** 建立共享代码机制，提升开发效率和可维护性。

## 2. 核心问题分析

### 2.1. 分散的状态管理

- **现状:** `src/main/stores` 和 `src/renderer/stores` 同时存在。主进程管理着应用级配置（`appStore`）和用户配置（`userStore`），而渲染进程管理着 UI 相关的状态（如 `deviceStore`）。
- **问题:**
    1.  **数据不一致风险:** 两套 `store` 机制可能导致数据同步问题，尤其是在双方都需要修改同一份数据时。
    2.  **逻辑分散:** 状态的读取和修改逻辑分散在两个进程中，增加了理解和维护的复杂度。
    3.  **通信开销:** 需要通过 IPC 在两个 `store` 之间手动同步状态，增加了不必要的通信负担。

### 2.2. 渲染进程中的“重”服务

- **现状:** `src/renderer/services` 包含大量服务，如 `ApkService`, `ToolService` 等。这些服务大多是对 `preload` 暴露的 `electronAPI` 的封装。
- **问题:**
    1.  **职责不清:** 渲染进程承担了过多的业务逻辑封装。理论上，渲染进程应主要关注 UI 展示，而将复杂的业务逻辑处理、API 请求等放在主进程或后端。
    2.  **可测试性差:** 依赖 Electron IPC 的前端服务难以进行单元测试。

### 2.3. 潜在的性能瓶颈

- **现状:** 像 `LogcatViewer.vue` 和 `DeviceManager.vue` 这样的组件，可能会处理大量或频繁更新的数据。
- **问题:**
    1.  **大数据量渲染:** 如果没有采用虚拟滚动（Virtual Scrolling），一次性渲染成百上千条日志或设备列表会导致严重的性能问题和内存占用。
    2.  **频繁更新:** 状态的频繁变更可能导致不必要的组件重渲染。

### 2.4. 缺乏代码共享机制

- **现状:** `src/shared` 目录为空，表明主进程和渲染进程之间没有通用的代码库。
- **问题:** 一些工具函数、常量或类型定义（例如，与后端 API 相关的类型）可能需要在两个进程中重复定义，增加了维护成本。

## 3. 优化方案

### 3.1. 统一状态管理：主进程作为唯一数据源 (Single Source of Truth)

**建议:** 将所有状态管理逻辑统一到 Electron 主进程中，使用 `electron-store` 或类似工具持久化，并建立一套机制让渲染进程订阅和更新状态。

**实施步骤:**

1.  **整合 Store 到主进程:**
    - 移除 `src/renderer/stores` 目录。
    - 增强 `src/main/stores`，使其管理所有应用状态，包括设备列表、配置等。
    - 使用 `electron-store` 进行持久化存储。

    ```javascript
    // src/main/stores/index.js (示例)
    import Store from 'electron-store';

    const schema = {
        userConfig: { type: 'object', default: {} },
        devices: { type: 'array', default: [] },
        // ... 其他状态
    };

    const store = new Store({ schema });

    export default store;
    ```

2.  **创建状态同步服务:**
    - 在主进程中，监听 `store` 的变化，并将更新推送到渲染进程。

    ```javascript
    // src/main/ipc/stateHandlers.js (新增)
    import { ipcMain } from 'electron';
    import store from '../stores';

    export function registerStateHandlers(mainWindow) {
        // 提供获取全量状态的API
        ipcMain.handle('get-store-state', () => {
            return store.store;
        });

        // 提供更新状态的API
        ipcMain.on('set-store-state', (event, key, value) => {
            store.set(key, value);
        });

        // 监听变化并推送
        store.onDidAnyChange((newValue, oldValue) => {
            mainWindow.webContents.send('store-updated', { newValue, oldValue });
        });
    }
    ```

3.  **在渲染进程中创建“镜像” Store:**
    - 在渲染进程中，创建一个轻量级的 Pinia store，它的唯一作用是接收和缓存从主进程同步过来的状态。

    ```javascript
    // src/renderer/stores/syncedStore.js (新增)
    import { defineStore } from 'pinia';
    import { ref, onMounted } from 'vue';

    export const useSyncedStore = defineStore('synced', () => {
        const state = ref({});

        async function initState() {
            state.value = await window.electronAPI.getStoreState();
        }

        onMounted(() => {
            initState();
            window.electronAPI.onStoreUpdated(({ newValue }) => {
                state.value = newValue;
            });
        });

        function setState(key, value) {
            window.electronAPI.setStoreState(key, value);
        }

        return { state, setState };
    });
    ```

### 3.2. 精简渲染进程，强化主进程服务

**建议:** 将 `src/renderer/services` 中的业务逻辑上移到 `src/main/services`。渲染进程的服务层只做最薄的封装。

**实施步骤:**

1.  **强化主进程服务:**
    - 将 `renderer/services` 中的逻辑（如 API 参数处理、错误处理）移至 `main/services`。
    - 主进程的 `commandService.js` 或其他服务应该直接与 Python 服务交互，并处理所有业务逻辑。

2.  **简化渲染进程服务:**
    - `renderer/services` 可以被大幅简化，甚至移除。组件可以直接通过 `useSyncedStore` 获取状态，或通过一个统一的 `apiService` 调用主进程方法。

    ```javascript
    // src/renderer/services/apiService.js (示例)
    export const apiService = {
        callBackend(method, params) {
            return window.electronAPI.callBackend(method, params);
        },
        // ... 其他非后端调用的主进程API
    };
    ```

### 3.3. 实施性能优化策略

**建议:** 对大数据量组件采用虚拟滚动，并优化 Vue 组件的更新机制。

1.  **引入虚拟滚动:**
    - 对于 `LogcatViewer.vue`，使用 `vue-virtual-scroller` 或类似库来只渲染可视区域内的日志条目。

    ```html
    <!-- LogcatViewer.vue (示例) -->
    <template>
      <RecycleScroller
        class="scroller"
        :items="logs"
        :item-size="32" // 每行高度
        key-field="id"
        v-slot="{ item }"
      >
        <div class="log-item">{{ item.message }}</div>
      </RecycleScroller>
    </template>

    <script setup>
    import 'vue-virtual-scroller/dist/vue-virtual-scroller.css';
    import { RecycleScroller } from 'vue-virtual-scroller';
    // ...
    </script>
    ```

2.  **优化组件更新:**
    - 使用 `shallowRef` 和 `triggerRef` 来手动控制大型数据结构的更新时机。
    - 对于不常变化的组件，可以使用 `v-once` 指令。
    - 确保 `key` 的正确使用，避免不必要的 DOM 重建。

### 3.4. 建立代码共享目录

**建议:** 利用 `src/shared` 目录来存放主进程和渲染进程都需要用到的代码。

**实施步骤:**

1.  **配置路径别名:**
    - 在 `vite.config.js` 中为 `src/shared` 设置路径别名。

    ```javascript
    // vite.config.js
    import { defineConfig } from 'vite';
    import path from 'path';

    export default defineConfig({
      // ...
      resolve: {
        alias: {
          '@': path.resolve(__dirname, 'src/renderer'),
          '@shared': path.resolve(__dirname, 'src/shared'),
        },
      },
    });
    ```

2.  **迁移共享代码:**
    - 将常量、TypeScript 类型定义、通用的工具函数等放入 `src/shared` 目录中。
    - 例如，可以创建一个 `src/shared/types/api.ts` 来定义与 Python 后端通信的数据结构。

## 4. 建议的项目结构调整

```
src/
├── main/
│   ├── ipc/              # IPC处理器 (stateHandlers.js 等)
│   ├── services/         # 增强的主进程服务
│   ├── stores/           # 唯一的 Store
│   ├── main.js
│   └── preload.js
├── renderer/
│   ├── components/
│   ├── views/
│   ├── stores/           # 简化的同步 Store (syncedStore.js)
│   ├── services/         # 极简的 API 服务 (apiService.js)
│   └── ...
└── shared/               # 新增：共享代码
    ├── types/
    ├── utils/
    └── constants/
```

## 5. 总结

通过实施以上优化，Blank Tool 的前端架构将变得更加健壮、高效和易于维护。核心思想是将**主进程作为应用的大脑和数据中心**，负责所有核心业务逻辑和状态管理；而**渲染进程则专注于 UI 的呈现和用户交互**，成为一个更“轻”、更纯粹的视图层。这种清晰的职责划分将极大地提升项目的长期可维护性和扩展性。