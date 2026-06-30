# AGENTS.md

本文件为 OpenCode / Claude Code 会话提供本仓库的工作指引。仅记录容易踩坑、文件名看不出来、与默认约定不同的高信号信息。

## 常用命令

```bash
npm run dev          # 启动开发模式（仅运行 vite；vite-plugin-electron 自动拉起 Electron 主进程/preload）
npm run lint         # vue-tsc --noEmit --pretty false（非 ESLint，是 Vue 类型检查）
npm run typecheck    # vue-tsc --noEmit（带详细输出）
npm run test         # vitest run（仅跑 TS 单测 + 集成测试）
npm run test:watch   # vitest 监听模式
npm run test:coverage
npm run check        # lint && typecheck && test（提交前一键三连）
npm run build:win    # node scripts/build.mjs --win（mac/linux 同理）
```

Dev server 监听 `http://localhost:3000`（strictPort，端口被占会直接失败）。Vite 的 `root` 是 `src/`，不是项目根。

## 测试有三套，分别由不同运行器驱动（最容易踩坑）

| 命令 | 运行器 | 范围 | 配置 |
|---|---|---|---|
| `npm run test` | **vitest** | `tests/unit/**`、`tests/integration/**` | `vitest.config.ts`，环境 `happy-dom` |
| `pytest tests/contracts/` | **pytest**（不在 npm scripts 里） | 后端 handler 契约测试（Python） | `tests/contracts/conftest.py` 自动把 `backend/` 加入 `sys.path` |
| `node --test tests/shared-contracts.test.mjs` | **node:test**（不在 npm scripts 里） | 校验 `src/shared/ipc/channels.ts` 与 `pathConfig.ts` 的字符串契约 | 无配置 |
| `npx playwright test` | **Playwright** | `tests/e2e/critical-flows.spec.ts` | `tests/e2e/playwright.config.ts` |

`npm run test` 在 `vitest.config.ts` 里显式 **exclude** 了 `tests/e2e/**` 和 `shared-contracts.test.mjs`，所以它不会跑后两者。改了后端 handler 或 IPC 通道名后，必须手动跑对应的契约测试。

`tests/setup.ts` 给 happy-dom 补了 `localStorage` / `sessionStorage` 桩，单元测试里的 Pinia 持久化依赖它。

## TypeScript 不严格（重要约定）

`tsconfig.json` 显式关闭了 `strict`、`noImplicitAny`、`strictNullChecks`、`noUnusedLocals`、`noUnusedParameters`。**不要**按默认严格模式去"修复"已有代码，也不要在 PR review 时把 nullable 误判为 bug。新增代码可以写得严格些，但不要大面积重构老代码。

路径别名（在 `tsconfig.json` 和 `vite.config.ts` 都有定义）：`@/` → `src/renderer/`，另有 `@components`、`@views`、`@services`、`@stores`、`@composables`、`@utils`、`@assets`。

## 架构（三进程桌面应用）

```
Renderer (Vue 3 + Pinia + Vue Router + Naive UI)
  window.electronAPI  ←  contextBridge (src/preload/index.ts)
        │  IPC
Main Process (Electron, src/main/)
  src/main/ipc/{commandHandlers,configHandlers,electronHandlers,updateHandlers}.ts
        │  spawn Python 子进程，stdin/stdout JSON-RPC
Python Backend (backend/main.py)
  ApiHandler → 自动扫描 app/handlers/ 下的 API_MAP
```

### 通信与超时

- **Renderer → Main**：渲染层调 `window.electronAPI.*`，经 `contextBridge` 路由到 `src/main/ipc/` 下的 handler。
- **Main → Python**：`commandHandlers.ts` 通过 stdin 写 JSON-RPC 请求，按 `request.id` 在 `requestCallbacks` Map 里匹配响应。**默认超时是 300000ms（5 分钟），不是 30 秒**——长任务（反编译、签名）依赖这个。
- **流式响应**：被 `@streaming`（`backend/app/common/decorators.py`）装饰的 handler 在独立线程运行，多次回包 `finished: false`，主进程通过命名 IPC 通道（如 `stream-event`）转发给渲染层（logcat、下载进度等）。

### 后端自动发现

- **Handlers**：`backend/app/handlers/` 下任何导出 `API_MAP` 字典的 `.py` 都会被 `ApiHandler` 自动注册。键是方法名（如 `"adb.devices"`），值是 handler 函数。新增 handler 不需要改注册表。
- **Tools**：`backend/app/tools/` 下任何 `BaseTool` 子类被 `ToolManager` 自动发现。子类按工具类型分：`BinaryTool`（exe）、`JavaTool`（.jar）、`PythonTool`（.py）、`NodeTool`（.js）。
- **Plugins**：`backend/plugins/` 下任何带 `run(context, **params)` 的 `.py` 会被自动加载。**目前该目录为空**，自动发现机制已就绪但无实际插件。

后端 Python 仅用标准库（`main.py`、`api_handler.py` 全部 import 自 stdlib + 本地 `app/` 包），**没有 `requirements.txt`**，开发时直接用系统或 `runtime/python/python.exe` 即可运行。

### 渲染层服务层

- `ServiceManager`（`src/renderer/services/ServiceManager.ts`）是 DI 容器：注册构造函数 + 依赖，首次 `getService()` 时懒加载。注册点在 `App.vue` 的 `registerServices()`。
- Pinia store（`src/renderer/stores/`）通过 `src/renderer/main.ts` 里的自定义 localStorage 持久化插件工作。store 声明 `persist: true` 或 `persist: { key }` 即自动同步 localStorage。

### 配置与路径

- **应用配置**：主进程用 `electron-store`（`src/main/stores/appStore.ts`），带 JSON schema 校验和版本化迁移。渲染层通过 `window.electronAPI.appConfig.get/set/getAll` 访问。
- **后端配置**：`backend/.env`（实际只有 `APP_VERSION`、`PROJECT_NAME`）+ `backend/server.config.json`（从 `server.config.example.json` 拷贝），由 `app/utils/env.py` 加载。关键 env：`BT_RUNTIME_DIR`、`BT_CACHE_DIR`、`BT_OUTPUT_DIR`、`BT_JAVA_BIN`、`BT_LOG_LEVEL`。**`server.config.json` 里的路径是相对于 `backend/` 目录的**（如 `../cache`）。
- **共享路径配置**：`src/shared/config/pathConfig.ts` 定义 `PATH_CONFIG_DEFAULTS`、`APP_CONFIG_KEYS`，主进程和渲染层都用它。
- **共享 IPC 通道名**：`src/shared/ipc/channels.ts` 集中定义所有 IPC 通道字符串。**改通道名必须同步 `tests/shared-contracts.test.mjs`**，否则契约测试会挂。

### 路径解析（开发 vs 打包）

- **Dev**（`!app.isPackaged`）：所有路径相对项目根。
- **Production**（`app.isPackaged`）：路径相对 `process.resourcesPath`——即 `electron-builder` 把 `extraResources` 放置的位置（见 `package.json` 的 `build.extraResources`：`backend/` 和 `runtime/` 都会被拷过去）。

判别逻辑集中在 `src/main/main.ts` 的 `getBaseDir()`，请勿在别处重新实现。

### 内置运行时（`runtime/`）

打包时会随应用分发，包含：`adb/`、`aapt/`（aapt2）、`apktool/`（.jar）、`bundletool/`（.jar）、`android/`（zipalign、apksigner.jar）、`jre/`（java、jarsigner）、`python/`。所有外部工具都从这里调用，不要假设系统 PATH 里有 `adb`/`java` 等。

## 构建流程的坑

`scripts/build.mjs` 做了三步：

1. `git describe --tags --abbrev=0` 取最新 tag，去掉 `v` 前缀作为版本号。
2. **备份 `package.json` 为 `package.json.bak`，把版本号注入 `package.json`**，然后跑 `npx vite build` + `npx electron-builder --<platform>`。
3. `finally` 块里恢复 `package.json`。

**坑**：构建过程中如果 `package.json.bak` 残留（上次崩溃），下次构建会覆盖；CI 中途 kill 进程可能留下脏状态。`package.json` 里的 `"version": "2.0.5"` **不是**发布版本，发布版本完全由 git tag 决定。

### 分支策略

```
dev     ← 日常开发，所有 commit 先到这里
main    ← 主线分支，只从 dev 合并，不打 commit
```

发布流程：
1. `dev` 开发完成 → `git checkout main && git merge dev`
2. 在 `main` 上打 tag：`git tag -a vX.Y.Z -m "..."` + `git push`
3. 打包 → 创建 GitHub Release
4. 切回 `dev` 继续开发

**tag 必须打在 `main` 上，不要打在 `dev` 上。**

发布：`git tag -a vX.Y.Z -m "..."` + `git push origin vX.Y.Z`。`electron-builder` 配置了 GitHub 自动更新（`publish.provider: github`，仓库 `purejiang/blank_tool`），主进程 `src/main/updater/` + `updateHandlers.ts` 负责检查和安装。

### Release 维护（释放 GitHub 存储空间）

GitHub Release 有 2GB 总大小限制，旧版本 `.exe` 会占满配额。**只删 exe 资产，保留 release 页面和 changelog：**

```bash
# ✅ 正确 — 只删 exe，release 页面和 tag 都保留
gh release delete-asset vX.Y.Z "Blank.Tool.Setup.X.Y.Z.exe" --yes

# ❌ 错误 — 删了整条 release + git tag，版本历史永久丢失
gh release delete vX.Y.Z --yes --cleanup-tag
```

每次新建 release 后，顺手清理上一个旧版本的 exe 即可。

## 其他约定

- 仓库根有 `dev-app-update.yml`，是 `electron-updater` 在开发模式下的测试配置，**不要提交生产凭证**。
- `.github/` 目录目前为空（没有 CI workflow），所有检查靠本地 `npm run check`。
- 国际化在 `src/renderer/i18n/`（zh-CN、en-US），UI 文案改动需同步两个语言文件。
- 主题系统用 CSS 变量驱动，三模式（浅色/深色/自动）在 `src/renderer/assets/styles/themes/`。
- 提交信息、文档、注释混用中英文是本仓库的常态，无需统一。
