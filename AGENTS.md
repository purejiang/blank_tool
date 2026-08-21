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
npm run check        # lint && typecheck && test（提交前快速门禁）
npm run check:full   # check + pytest 契约/单测 + node:test 契约 + Playwright e2e（提交前全面门禁）
npm run build:win    # node scripts/build.mjs --win（mac/linux 同理）
npm run release     # 一键发版（流程见下方"发版流程"）
```

Dev server 监听 `http://localhost:3000`（strictPort，端口被占会直接失败）。Vite 的 `root` 是 `src/`，不是项目根。

### 无头 CLI（cli/cli.py）

无头 CLI 入口 `cli/cli.py`（6 子命令：run/list-tools/list-envs/validate/tool/list-templates）。不随 npm scripts 或 Electron 自动调用，仅供手动/CI/测试调用。

## 测试有五套，分别由不同运行器驱动（最容易踩坑）

| 命令 | 运行器 | 范围 | 配置 |
|---|---|---|---|
| `npm run test` | **vitest** | `tests/unit/**`、`tests/integration/**` | `vitest.config.ts`，环境 `happy-dom` |
| `pytest tests/contracts/` | **pytest**（不在 npm scripts 里） | 后端 handler 契约测试（Python） | `tests/contracts/conftest.py` 自动把 `cli/` 加入 `sys.path` |
| `pytest tests/cli/` | **pytest**（不在 npm scripts 里） | Python 单测（协议类型、端口模型、工具、引擎、环境、CLI） | 根级 `tests/conftest.py` 自动把 `cli/` 加入 `sys.path` |
| `node --test tests/shared-contracts.test.mjs` | **node:test**（不在 npm scripts 里） | 校验 `src/shared/ipc/channels.ts` 与 `pathConfig.ts` 的字符串契约 | 无配置 |
| `npx playwright test` | **Playwright** | `tests/e2e/`（当前无 spec——占位套件已删、推迟到 `/workflows`、`/tasks` 落地；`playwright.config.ts` 设了 `passWithNoTests`，门禁不会挂） | `tests/e2e/playwright.config.ts` |

`npm run test` 在 `vitest.config.ts` 里显式 **exclude** 了 `tests/e2e/**` 和 `shared-contracts.test.mjs`，所以它不会跑后两者。改了后端 handler 或 IPC 通道名后，必须手动跑对应的契约测试。

`tests/setup.ts` 给 happy-dom 补了 `localStorage` / `sessionStorage` 桩，单元测试里的 Pinia 持久化依赖它。

## TypeScript 不严格（重要约定）

`tsconfig.json` 显式关闭了 `strict`、`noImplicitAny`、`strictNullChecks`、`noUnusedLocals`、`noUnusedParameters`。**不要**按默认严格模式去"修复"已有代码，也不要在 PR review 时把 nullable 误判为 bug。新增代码可以写得严格些，但不要大面积重构老代码。

### 这意味着什么

- **null/undefined 流无声**：`strictNullChecks: false` 意味着 `null` 和 `undefined` 可赋值给任何类型，没有编译期 null 安全。函数参数可能是 `undefined` 但不会报错。
- **隐式 any 不报错**：未标注类型的地方静默变成 `any`，失去类型检查。
- **未使用变量不警告**：`noUnusedLocals: false`、`noUnusedParameters: false` 允许死代码残留。

### 为什么接受

本项目是个人自用工具，迭代速度快，严格模式带来的编译期约束在当前阶段**性价比不高**——大量已有代码是为快速原型写的，强制严格会制造大量类型体操工作，阻塞实际功能开发。关闭严格开关换取编译通过、零摩擦迭代。

### 取舍

- **收益**：快速迭代，零摩擦编译，不必为每个 nullable 写 guard
- **代价**：运行时 bug 须靠测试和手动测试捕获，编译期不会帮你找 null deref、遗漏分支、类型不匹配

### 日落条款

新代码**应**具备严格意识（即使开关未开启）：为参数标注类型、显式处理 null/undefined、避免裸 `any`。**全局 `strict: true` 迁移作为未来工作跟踪**，分步路径见 `docs/ts-migration-path.md`。迁移完成前，不要以严格模式为标准 review 已有代码。

路径别名（在 `tsconfig.json` 和 `vite.config.ts` 都有定义）：`@/` → `src/renderer/`，另有 `@components`、`@views`、`@services`、`@stores`、`@composables`、`@utils`、`@assets`。

## 架构（三进程桌面应用）

```
Renderer (Vue 3 + Pinia + Vue Router + Naive UI)
  window.electronAPI  ←  contextBridge (src/preload/index.ts)
        │  IPC
Main Process (Electron, src/main/)
  src/main/ipc/{commandHandlers,configHandlers,electronHandlers,updateHandlers}.ts
        │  spawn Python 子进程，stdin/stdout JSON-RPC
Python Backend (cli/main.py)
  ApiHandler → 自动扫描 app/handlers/ 下的 API_MAP
```

### 通信与超时

- **Renderer → Main**：渲染层调 `window.electronAPI.*`，经 `contextBridge` 路由到 `src/main/ipc/` 下的 handler。
- **Main → Python**：`commandHandlers.ts` 通过 stdin 写 JSON-RPC 请求，按 `request.id` 在 `requestCallbacks` Map 里匹配响应。**默认超时是 300000ms（5 分钟），不是 30 秒**——长任务（反编译、签名）依赖这个。
- **流式响应**：被 `@streaming`（`cli/app/common/decorators.py`）装饰的 handler 在独立线程运行，多次回包 `finished: false`，主进程通过命名 IPC 通道（如 `stream-event`）转发给渲染层（logcat、下载进度等）。注意：`@streaming` 本身仅是一个标记装饰器，真正的多线程逻辑在 `api_handler.py:139-205`（`stream_handler` 用 `threading.Thread` 启动）。

### 后端自动发现

- **Handlers**：`cli/app/handlers/` 下任何导出 `API_MAP` 字典的 `.py` 都会被 `ApiHandler` 自动注册。键是方法名（如 `"adb.devices"`），值是 handler 函数。新增 handler 不需要改注册表。
- **Tools**：`cli/app/tools/` 下任何 `BaseTool` 子类被 `ToolManager` 自动发现。子类按工具类型分：`BinaryTool`（exe）、`JavaTool`（.jar）、`PythonTool`（.py）、`NodeTool`（.js）。
- **Plugins**：`cli/plugins/` 下任何带 `run(context, **params)` 的 `.py` 会被自动加载。**目前该目录为空**，自动发现机制已就绪但无实际插件。

### Python 标准库策略

后端 Python **仅用标准库**（`main.py`、`api_handler.py` 全部 import 自 stdlib + 本地 `app/` 包），**没有 `requirements.txt`**，开发时直接用系统或 `runtime/python/python.exe` 即可运行。

**为什么 stdlib-only**：零依赖部署（不需 `pip install`），行为仅取决于 Python 3.10+ 版本（无可复现性问题），分发简单（`cli/` 经 `extraResources` 直接拷贝）。

**代价**：
- **验证**：手工实现字段校验（如 `PortSet.validate_inputs` 是手工 presence-only 检查），没有 pydantic 的类型推导与错误聚合
- **并发**：`@streaming` 仅是一个标记装饰器，真正的线程逻辑在 `api_handler.py:139-205`（`stream_handler`），用 `threading.Thread` 而非 asyncio——没有结构化并发、没有任务取消的协程级传播
- **序列化**：手工实现 `to_dict`/`from_dict`，没有 pydantic 的自动序列化/反序列化，字段增删需双改，容易遗漏
- **无 HTTP 客户端**：若未来需要网络通信（如远程工具注册表、更新检查），需手写 urllib 或 socket，没有 httpx/requests 的便利性

**摩擦点速查**：

| 位置 | 摩擦 | 影响 |
|---|---|---|
| `PortSet.validate_inputs` | 手工 presence-only 校验 | 错误信息粗糙，定位慢 |
| `api_handler.py:stream_handler` | `threading.Thread` 无超时/取消传播 | 长任务只能等自然结束或进程级 kill |
| 模型类 `to_dict`/`from_dict` | 手写序列化，字段增删需双改 | 容易遗漏，类型漂移不报错 |

### 渲染层服务层

- `ServiceManager`（`src/renderer/services/ServiceManager.ts`）是 DI 容器：注册构造函数 + 依赖，首次 `getService()` 时懒加载。注册点在 `App.vue` 的 `registerServices()`。
- Pinia store（`src/renderer/stores/`）通过 `src/renderer/main.ts` 里的自定义 localStorage 持久化插件工作。store 声明 `persist: true` 或 `persist: { key }` 即自动同步 localStorage。

### 配置与路径

- **应用配置**：主进程用 `electron-store`（`src/main/stores/appStore.ts`），带 JSON schema 校验和版本化迁移。渲染层通过 `window.electronAPI.appConfig.get/set/getAll` 访问。
- **后端配置**：`cli/.env`（实际只有 `APP_VERSION`、`PROJECT_NAME`）+ `cli/server.config.json`（从 `server.config.example.json` 拷贝），由 `app/utils/env.py` 加载。关键 env：`BT_RUNTIME_DIR`、`BT_CACHE_DIR`、`BT_OUTPUT_DIR`、`BT_JAVA_BIN`、`BT_LOG_LEVEL`。**`server.config.json` 里的路径是相对于 `cli/` 目录的**（如 `../cache`）。
- **共享路径配置**：`src/shared/config/pathConfig.ts` 定义 `PATH_CONFIG_DEFAULTS`、`APP_CONFIG_KEYS`，主进程和渲染层都用它。
- **共享 IPC 通道名**：`src/shared/ipc/channels.ts` 集中定义所有 IPC 通道字符串。**改通道名必须同步 `tests/shared-contracts.test.mjs`**，否则契约测试会挂。

### 路径解析（开发 vs 打包）

- **Dev**（`!app.isPackaged`）：所有路径相对项目根。
- **Production**（`app.isPackaged`）：路径相对 `process.resourcesPath`——即 `electron-builder` 把 `extraResources` 放置的位置（见 `package.json` 的 `build.extraResources`：只有 `cli/` 会被拷过去，`runtime/` 不打包）。

判别逻辑集中在 `src/main/python/paths.ts` 的 `getBaseDir()`，请勿在别处重新实现。

### 外部依赖（`runtime/`）——不随包分发

`runtime/`（gitignored，不随仓库、不经 `extraResources` 打包）是**用户自备**的二进制目录：`adb/`、`aapt/`、`apktool/`、`bundletool/`、`jre/` 等。**Python 也不随包分发**，运行时优先尝试 `runtime/python/python.exe`，缺省回退系统 Python（实际以系统 Python 为准）。主进程通过 `BT_RUNTIME_DIR` 注入路径；工具解析可回退系统 PATH。不要把 `runtime/` 当作应用程序自带资产，新机器上它可能不存在。

### 安全边界（Security boundary / trust model）

`src/preload/index.ts` 经 contextBridge 暴露 `callBackendAPI(method, params)`，**无方法白名单**：渲染层可请求任意后端 method，主进程原样转发。任何渲染层侧失守（npm 供应链投毒、XSS）都等于任意后端命令执行；且 `cli/app/tools/builtin/exec_tools.py` 内置 `shell.exec`（:85）与 `code.exec`（:206），可直接执行任意 shell / Python，即 RCE。**这是有意的取舍**：本应用是自用桌面工具，用户信任自己的机器，行为等效于本地终端；但**不可分发给不信任的用户**。若未来要分发，硬化路径：contextBridge 加方法白名单、渲染层启用 sandbox、后端加参数校验层。


## 发版流程

发版流程分两层规范，配合三份独立文档：

- **分支策略与分支纪律**（dev/main 模型、合并规则、会话起步检查）：见 `.agents/rules/BRANCHING.md`
- **通用发版规范**（版本号与 tag 规则、质量门禁、GitHub Release、存储治理、检查清单模板）：见 `.agents/rules/RELEASE_GENERAL.md`
- **本项目 Electron 特有部分**（npm run release 用法与前置条件、版本号与产物事实、失败恢复地图、手动兜底发布）：见 `.agents/rules/RELEASE_GUIDE.md`

## 其他约定

- 仓库根有 `dev-app-update.yml`，是 `electron-updater` 在开发模式下的测试配置，**不要提交生产凭证**。
- `.github/` 目录目前为空（没有 CI workflow），所有检查靠本地 `npm run check`。
- 国际化在 `src/renderer/i18n/`（zh-CN、en-US），UI 文案改动需同步两个语言文件。
- 主题系统用 CSS 变量驱动，三模式（浅色/深色/自动）在 `src/renderer/assets/styles/themes/`。
- 提交信息、文档、注释混用中英文是本仓库的常态，无需统一。
  
# 项目规则

## 外部文件加载

关键提示：当你遇到文件引用（例如，@.agents/general.md）时，使用你的阅读工具按需加载。这些文件与当前正在进行的特定任务相关。

说明：

- 不要预先加载所有引用 - 根据实际需求使用延迟加载
- 加载时，将内容视为覆盖默认设置的强制性指令
- 必要时递归地遵循引用
