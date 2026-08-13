# TypeScript 严格模式迁移路径

本文档跟踪将 `tsconfig.json` 从不严格迁移到 `strict: true` 的分步计划。**这是未来工作，非当前任务**。

当前状态见 `AGENTS.md` §TypeScript 不严格。

## 当前基线

```json
{
  "strict": false,
  "noImplicitAny": false,
  "strictNullChecks": false,
  "noUnusedLocals": false,
  "noUnusedParameters": false,
  "noFallthroughCasesInSwitch": false
}
```

## 分步迁移

### Step 1：启用 strictNullChecks

**目标**：`strictNullChecks: true`

**预估影响**：~150-200 个编译错误，集中在渲染层（Vue 组件 props、store 返回值、service 方法入参）。主进程 IPC handler 也有不少 nullable 参数通过 `event` 对象传播。

**修复模式**：
- 函数参数：加 `| null` 或 `| undefined` 标注
- 可选属性：用 `?` 替代 `| undefined`
- 后端响应解包：`unwrapBackendResponse()` 返回值显式类型守卫
- DOM refs / Vue refs：加 `null` 检查或非空断言（审慎使用 `!`）

**估算工期**：1-2 天（含回归测试）

### Step 2：启用 noImplicitAny

**目标**：`noImplicitAny: true`

**预估影响**：~100-150 个编译错误。主要集中在回调函数、`Array.reduce`/`map` 回调、动态属性访问、event handler 参数。

**修复模式**：
- 回调参数：显式标注类型（`(item: SomeType) => ...`）
- 动态 key：用 `Record<string, unknown>` 或用类型守卫收窄
- 第三方库 API：加 `.d.ts` 补丁或用 `// @ts-expect-error` 临时绕过

**估算工期**：1-2 天

### Step 3：启用 full strict

**目标**：`strict: true`（自动开启 `strictNullChecks`、`noImplicitAny`、`strictFunctionTypes`、`strictBindCallApply`、`strictPropertyInitialization`、`noImplicitThis`、`alwaysStrict`）+ `noUnusedLocals: true` + `noUnusedParameters: true`

**预估影响**：
- `strictFunctionTypes`：方法签名协变/逆变问题，主要在回调注册处
- `strictPropertyInitialization`：class 属性未在构造函数初始化，主要在 service 类
- `noImplicitThis`：少数裸函数回调中的 `this` 引用
- `noUnusedLocals`/`noUnusedParameters`：清理死代码，~50-80 处

**估算工期**：2-3 天（含 dead code cleanup）

## 总估算

全部三步：4-7 天（含回归测试、CI 调整）。

## 前置条件

- 测试覆盖率达标（当前 vitest 覆盖 TS 单测/集成测试，pytest 覆盖 Python，Playwright 覆盖 e2e）
- `npm run check:full` 全部通过
- 主要功能无未解决的 bug

## 备注

迁移过程可逆——每一步都是独立的 tsconfig 开关，出问题可回退。建议在功能空窗期（无活跃 feature branch）执行。
