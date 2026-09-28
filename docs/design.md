# Design — 视觉设计手册（颜色分级 · token 现状 · 改色指引）

> **本文档的边界**（不要再造出第二份"权威"）：
>
> - **token 契约**（哪些维度必须进 token、唯一来源、护栏、数值回填时机）→ [07-UI设计规范](./07-UI设计规范.md) §4
> - **UI 生成提示词** → [`docs/ui-prompts/`](./ui-prompts/README.md)（索引在 [08](./08-前端页面与功能清单.md) §8）
> - **本文档** → 现有色板与分级的**实况全表**、缺口清单、改颜色 / 改圆角 / 改字体的**操作步骤与验证命令**
>
> ⚠️ 本文档记录的是**当前实现的遗留色板**（重构前的绿色系），**不是目标设计值**。首屏 Stitch 设计稿确认后，按 07 §4 的时机回填 `tokens.ts`，并同步更新本文档的表。
>
> 状态：2026-09-21 逐文件核实（`workflow` 分支）。所有行号可直接对照。

## 1. 主题机制：一次切换经过哪几层

1. `src/renderer/services/ThemeService.ts:39` → `document.documentElement.setAttribute('data-theme', actual)`
2. `src/renderer/assets/styles/themes.css` → 按 `[data-theme="light"|"dark"]` 提供 `--app-*`
3. `src/renderer/App.vue:2` → `n-config-provider :theme :theme-overrides`（`:62` 调 `selectOverrides`）
4. `src/renderer/theme/overrides.ts` → 用**字面量**写 Naive 内部色（色板的第二份）；`assets/styles/naive-overrides.css` → 覆盖 Naive DOM

### 1.1 实际导入的样式文件（`src/renderer/main.ts:13-18`，顺序即层叠顺序）

| # | 文件 | 提供 | 跟随主题？ |
|---|---|---|---|
| 1 | `assets/styles/main.css` | 遗留 Bootstrap 风变量：`--primary-color: #007bff`（蓝）、`--border-radius`（6px）、`--spacing-*`、`--font-size-*`、`--shadow-*` + 工具类 | ❌ 不在 `[data-theme]` 内 |
| 2 | `assets/styles/common/components.css` | 遗留组件类 29 个（`.section` / `.file-drop-zone` / `.progress-*` / `.toggle-*` …） | ❌ |
| 3 | `assets/styles/themes.css` | **`--app-*` 浅/深两套（唯一跟随主题的层）** + vue-flow 映射 + 滚动条 + Naive dark 修补 | ✅ |
| 4 | `assets/styles/common/responsive.css` | 响应式断点（消费 `--spacing-*` / `--font-size-*`） | ❌ |
| 5 | `assets/variables.css` | **第三套变量**：`--color-*`（`--color-primary: #3b82f6`，蓝）、`--space-*`、`--radius-*`（4/8/12px）、`--font-*`、`--shadow-*` | ❌ |
| 6 | `assets/styles/naive-overrides.css` | Naive DOM 覆盖（含裸 `border-radius: 8px`，第 4 行） | 部分（用 `--app-*`） |
| — | `theme/overrides.ts` | Naive 主题字面量：色板第二份 + `borderRadius: '8px'` ×6 | 浅/深各写死一份 |

**一个应用里有四套变量家族，只有 `--app-*` 跟随主题。**"主色"在代码里有三个不同值：`#007bff`（main.css，蓝）、`#3b82f6`（variables.css，蓝）、`#16A34A`/`#22C55E`（themes.css，绿）——**实际生效的是绿色那套**。

### 1.2 导入顺序造成的静默覆盖

`variables.css` 排在第 5 位，同名变量会盖掉 `main.css` 的：`--font-size-sm` 由 `0.875rem`(14px) 变 `12px`、`--font-size-base` 由 `1rem`(16px) 变 `14px`、`--font-size-lg` 由 `1.125rem`(18px) 变 `16px`，`--shadow-sm` / `--shadow-lg` 也各被替换一次（`--font-size-xl` 两边同值）。而 `variables.css` 自己的 `--color-*` / `--space-*` / `--radius-*` / `--font-family` **全仓零引用**（grep 无命中）——它现在唯一的作用就是这次静默覆盖。

## 2. 颜色分级实况（`--app-*`）

### 2.1 层级结构

- **背景 4 级**：`body` → `sidebar` → `card` → `input`（另有 `code-bg` / `drop-zone-bg` / `storage-bg` 三个特例，值常与 sidebar 或 body 同）
- **文本 4 级**：`primary` → `secondary` → `muted` → `dim`
- **描边 3 项**：`card-border`（最弱）、`input-border`、`sidebar-border`（另有 `drop-zone-border`）
- **状态色 6 个色相**：green（主色）/ blue / red / yellow / orange / purple——**只有 green 是完整的**

### 2.2 全表（浅 / 深）

| 分组 | token | 浅色 | 深色 |
|---|---|---|---|
| 背景 | `--app-body-bg` | `#F1F5F9` | `#0F172A` |
| | `--app-sidebar-bg` | `#E2E8F0` | `#0C1322` |
| | `--app-card-bg` | `#FFFFFF` | `#1E293B` |
| | `--app-input-bg` | `#FFFFFF` | `#1E293B` |
| 文本 | `--app-text-primary` | `#0F172A` | `#F8FAFC` |
| | `--app-text-secondary` | `#334155` | `#CBD5E1` |
| | `--app-text-muted` | `#475569` | `#94A3B8` |
| | `--app-text-dim` | `#64748B` | `#64748B` ⚠️ 同值 |
| 描边 | `--app-card-border` | `#E2E8F0` | `#334155` |
| | `--app-input-border` | `#CBD5E1` | `#334155` |
| | `--app-sidebar-border` | `#CBD5E1` | `#1E293B` |
| 交互 | `--app-hover` | `rgba(0,0,0,.04)` | `rgba(34,197,94,.06)` ⚠️ 带主色 |
| | `--app-hover-strong` | `rgba(0,0,0,.08)` | `rgba(34,197,94,.12)` ⚠️ |
| 代码/拖放 | `--app-code-bg` | `#F1F5F9` | `#0C1322` |
| | `--app-drop-zone-bg` | `#F8FAFC` | `#0C1322` |
| | `--app-drop-zone-border` | `#94A3B8` | `#334155` |
| 滚动条/占位 | `--app-scrollbar-thumb` | `#CBD5E1` | `#334155` |
| | `--app-scrollbar-hover` | `#94A3B8` | `#475569` |
| | `--app-placeholder-color` | `#CBD5E1` | `#334155` |
| 其他 | `--app-storage-bg` | `rgba(0,0,0,.04)` | `rgba(15,23,42,.5)` |

### 2.3 状态色：只做了一半

| 色相 | 基色（浅/深） | hover | 弱背景 |
|---|---|---|---|
| green（主色） | `#16A34A` / `#22C55E` | ✅ `#15803D` / `#16A34A` | ✅ `-bg` / `-bg-hover` / `-bg-active` |
| blue | `#2563EB` / `#3B82F6` | ❌ | ✅ 仅 `-bg` |
| red | `#DC2626` / `#EF4444` | ❌ | ❌ |
| yellow | `#B45309` / `#F59E0B` | ❌ | ❌ |
| orange | `#EA580C` / `#FB923C` | ❌ | ❌ |
| purple | `#9333EA` / `#C084FC` | ❌ | ❌ |

### 2.4 编辑器专区别名（`themes.css:76-87`，`:root` 内，**不在主题块里**）

`--node-bg` / `--node-border` / `--node-text` / `--port-color` / `--edge-color` / `--edge-color-selected` / `--palette-bg` / `--palette-text` / `--config-panel-bg` 全部由 `var(--app-*)` 求值，会自动跟随主题；只有 `--minimap-mask: rgba(100,116,139,.3)` 是**硬编码常量，浅深同值**。

## 3. 分级缺口（改色前需要知道的 6 件事）

| # | 缺口 | 证据 | 影响 |
|---|---|---|---|
| 1 | 状态色缺弱背景与 hover：只有 green 完整、blue 有 1 个 | §2.3 | [08 §3 · S4](./08-前端页面与功能清单.md) 要的"成功 / 失败 / 运行中 / 已取消"徽章里，**失败无弱背景、"已取消"连灰都没有**（全表无 `--app-gray`）→ 实现时只能当场拼 `rgba()` 或退回 Naive 内置色 |
| 2 | `--app-text-dim` 浅深同值，且身兼多职 | `themes.css:14,48,80,81,156` | 唯一不跟随主题的 token，还兼任 `--port-color` / `--edge-color` / 小地图节点填充 → 深色下对比度偏低 |
| 3 | hover 语义两态不一致：浅色中性黑、深色带主色 | `themes.css:26,27,60,61` | 同一语义两种含义；**换主色时深色 hover 会跟着旧主色跑** |
| 4 | Naive 侧与 CSS 变量漂移（深色输入框边框） | `themes.css:44` = `#334155` vs `overrides.ts:27` = `#475569` | 深色下 Naive 输入框与自定义组件边框不同色（浅色两侧一致，都是 `#CBD5E1`） |
| 5 | Naive 的主题值是色板第二份手抄 | `overrides.ts` 全文件 | 任何改色都要改两遍，漏一处就同页两种颜色 |
| 6 | 颜色以外完全没有 `--app-*` 分级 | grep 无 `--app-radius` / `--app-space` / `--app-font` | 圆角有 3 个值（6px 遗留 / 8px Naive / 20px 开关）、正文无间距阶、字体 12 处裸 `Inter, sans-serif` |

**另有 3 条与主题无关但会绊人的遗留物**：`components.css:104` 用了未定义变量 `--primary-color-light`、`:106` 用了未定义的 `--transition-normal`（相关声明实际不生效）；`components.css` 的 29 个类在当前 `.vue` 里已无有效引用（唯一同名的 `.section-header` 被各视图 scoped 规则遮蔽）；`main.ts:77-99` 的启动失败兜底页内联了 `#f5f5f5` / `#e74c3c` / `#3498db` 等色值（**属有意例外**，它在主题生效前渲染，不要"顺手修复"）。

## 4. 改色指引

### 4.1 先认清代价

**今天改一个颜色不是改一处。** 以换主色（当前为绿）为例：

| 要动的地方 | 数量 | 漏改的后果 |
|---|---|---|
| `themes.css` 浅色块：`--app-green` + hover + 3 个 `rgba` 弱背景（**`rgba()` 里的 RGB 也要改**） | 5 个值 | 自定义组件不变 |
| `themes.css` 深色块 | 5 个值 | 只有深色态不变 |
| `theme/overrides.ts` 浅 + 深：`primaryColor` / `primaryColorHover` / `primaryColorPressed` / `successColor` / `hoverColor` / `Input`·`InternalSelection` 的 `borderHover`·`borderFocus` | 约 12 个值 | Naive 按钮 / 输入框 / 开关不变 → 同页两种主色 |
| 5 个 `.vue` 里 10 处裸 `#22C55E`（图标/文字） | 10 处 | 图标色与主色不一致 |
| 深色 `--app-hover`（带绿）若也希望跟主色 | 2 个值 | 深色 hover 仍是旧主色 |

### 4.2 路径 A：只调局部 / 试色

改 `themes.css` 里对应 `--app-*` 的**浅深两块**，刷新即生效。适合只调自定义区域（卡片、侧边栏、文本层级）；**Naive 控件不会跟着变**（它们的颜色来自 `overrides.ts` 的字面量）。

### 4.3 路径 B：整体换主色（今天可行）

1. `themes.css` 浅色块：`--app-green` / `--app-green-hover` / `--app-green-bg` / `-bg-hover` / `-bg-active`
2. `themes.css` 深色块：同 5 项；顺带决定 `--app-hover` / `--app-hover-strong` 是否跟着换
3. `overrides.ts`：浅深两份的 `primaryColor` / `primaryColorHover` / `primaryColorPressed` / `successColor` / `hoverColor`，以及 `Input` / `InternalSelection` 的 `borderHover` / `borderFocus`
4. 图标色：把 5 个 `.vue` 里的 10 处 `#22C55E` 换成 `var(--app-green)`（顺手消掉裸值）

校验（命中应只剩 `themes.css`）：

```bash
git grep -n "22C55E\|16A34A\|15803D" -- src/renderer
```

### 4.4 路径 C：token 管道（目标态）

`dev` 分支已有可搬实现：`src/renderer/theme/tokens.ts`、`scripts/generate-theme-css.mjs`、`tests/unit/theme/tokens-css-parity.test.ts`、`tests/unit/theme/themeOverrides.test.ts`（当前分支均不存在）。搬完后改色 = 改 `tokens.ts` 一处 → 跑生成脚本 → 跑 parity 测试，§4.1 那张表直接消失。

### 4.5 速查：我要改 X

| 我要改 | 今天要动 | 备注 |
|---|---|---|
| 主色 | 见 §4.3 四步 | 别忘 `rgba()` 里的 RGB |
| 背景层次（更沉 / 更亮） | `themes.css` 浅深各 4 项（body / sidebar / card / input），并同步 `--app-code-bg`、`--app-drop-zone-bg` | 深色里 sidebar 与 card 是不同层；浅色里 body 与 card 靠描边区分 |
| 新增状态色（如"已取消"灰） | `themes.css` 浅深各加 base（建议连 `-bg` 一起加）→ 若给 Naive 用还要加进 `overrides.ts` | 现无 `--app-gray`；建议命名 `--app-neutral` 或 `--app-cancel` |
| 圆角 | `overrides.ts` ×6 + `naive-overrides.css:4` | **观感主要来自 Naive 那套**；遗留 `--border-radius`（6px）只影响已无引用的遗留 CSS |
| 正文/等宽字体 | 正文：12 处裸 `Inter, sans-serif`；等宽：4 种写法——`'Fira Code', monospace`、裸 `monospace`、`ui-monospace, SFMono-Regular, …`、遗留 `var(--font-family-monospace)`（main.css / components.css） | 无 `--app-font-*` token，只能全量替换 |
| 间距 | 组件里多为裸 px；遗留 `--spacing-*`（main.css）与 `--space-*`（variables.css，零引用）并存 | 无 `--app-space-*` token |

## 5. 验证清单

改完必做：

- [ ] 三态都看：浅色 / 深色 / 自动（`自动` 等价于跟随系统，不必单独出图）
- [ ] 主按钮：常态 / hover / active
- [ ] 图标色与文本层级（`--app-text-dim` 在深色下是否还看得清）
- [ ] 健康圆点（`components/common/StatusBar.vue:92-93`、`views/DiagnosticsPage.vue:319-320`）
- [ ] 输入框边框与聚焦环（注意 §3-#4 的漂移）
- [ ] 行 hover（注意深色 hover 带主色）
- [ ] 滚动条、画布点阵、端口圆点、连边、小地图（吃 `--app-text-dim` 与 `--minimap-mask`）
- [ ] grep 校验：`git grep -n "22C55E\|16A34A\|15803D" -- src/renderer`
- [ ] `npm run dev` 起得来（dev server 固定 3000，端口占用会直接失败）

## 6. 相关文档

- token 契约（维度 / 唯一来源 / 护栏 / 验收）：[07-UI设计规范](./07-UI设计规范.md) §4、§6
- 逐屏功能元素与验收：[08-前端页面与功能清单](./08-前端页面与功能清单.md) §3
- 逐屏 UI 生成提示词：[ui-prompts/](./ui-prompts/README.md)
- 后端缺口与工作包落地状态（WP0–WP6）：[09-后端缺口修复与优化方案](./09-后端缺口修复与优化方案.md)
