# E2E Tests (Deferred)

E2E 测试**推迟到新 UI 模块落地之后**编写。

## 为什么推迟

- 目标页面 `/workflows`（工作流列表页）与 `/tasks`（任务页）尚在规划中（开发计划的 Phase 2-3），目前只有 `/settings`、`/about`、`/diagnostics`、`/workflow-editor` 四个页面。
- 之前的 e2e 套件（`critical-flows.spec.ts`）是**占位测试（placebo）**：
  - 测试的是已被删除的 DevicePage（T22，commit 79fa03d 删除），全部用例引用不存在的页面。
  - 每个用例用 `try/catch` 包裹，任何错误一律 `test.skip(true, 'Dev server not running')` —— 测试要么被跳过、要么断言的是恒真条件。
  - 例如 `deviceList.count() >= 0` 是恒真断言（元素不存在也为 0），无法提供任何回归价值。
  - 配置 `baseURL` 指向 `http://localhost:5173`，而 vite dev server 实际跑在 `http://localhost:3000`，即使运行也无法命中。
- 该占位套件已删除（2026-08-10），`playwright.config.ts` 保留供未来使用。

## 何时编写真实 e2e

当 `/workflows` 与 `/tasks` 页面实现后，编写真实 e2e 覆盖：

- 工作流列表：新建 / 编辑 / 删除 / 导入 / 导出
- 任务页：选模板 → 动态表单 → 执行 → 节点进度与日志

在无测试文件的情况下，`npm run check:full` 中的 Playwright 步骤会报告 "no tests found"，属正常现象，无需改动 `package.json`。

## 运行方式（未来）

```bash
npx playwright test
```
