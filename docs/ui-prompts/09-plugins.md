# ⑨ 插件 `/tools/plugins`

- **导航态**：工具（选中）。本页是「工具」下的**第三个独立页面**（不是同页 tab 面板）：自己的标题、描述、工具栏；靠页面头右侧的**区段切换**在「工具 | 环境 | 插件」之间跳转。
- **前置**：先跑 [`00-shell.md`](./00-shell.md) 并在 Edit Theme 里锁定主题
- **功能元素来源**：[08 §3 · S6.3 插件](../08-前端页面与功能清单.md)
- **本屏产出**：常规态（含一行"加载失败"与一行"未加载"）；浅 / 深两态
- **说明**：插件是**代码加载单元**（`apply(ctx, config)`），与"工具"不是同一层：一个插件可以注册多个工具。本页只回答"哪些插件在加载、哪些失败了、失败原因是什么"。

## 提示词（逐字粘贴，不要改写）

```text
沿用同一外壳，导航「工具」选中。这是「插件」页面。
页面头：左侧标题「插件」+ 一句话描述「代码加载单元：模块、种类、来源与加载状态；失败的直接给出原因。」；
标题右侧是区段切换「工具 | 环境 | 插件」，当前「插件」为选中态。
工具栏：主按钮「添加插件」、次按钮「重载」。
下方一张卡片，内部是插件行列表，每行：
- 最左一个状态圆点（已加载绿色、加载失败红色、未加载灰色）
- 模块名（等宽字体，示例 cli.app.plugins.builtin.core）
- 种类徽章「内置」（shipped-native）或「原生」（native）
- 版本号（等宽小字，示例 1.0.1；未知时显示「—」）
- 状态徽章「已加载」（绿色）/「加载失败」（红色）/「未加载」（灰色）
- 最右删除按钮（内置插件的删除为禁用态）
「加载失败」的行在模块名下方多一行红色等宽错误文案，示例
ImportError: No module named 'unity_bridge'；该行整体降一档透明度。
```

> ⚠️ 三个不要：① **不要把本页做成工具页里的一个 tab 面板**（它是独立页面，有自己的标题、描述与工具栏）；② **不要画环境依赖徽章**——`plugin.list` 不返回环境依赖，插件注册出来的内置工具也没有该字段（缺口 #18），画上去就是编数据；③ **不要显示"该插件注册了哪些工具"**（后端没有插件↔工具的归属字段），也不要显示 `descriptor` 这种 kind（清单加载器只允许 `shipped-native` / `native`，界面上只有两种徽章）。

## 字段与数据来源

| 行元素 | 来源 |
|---|---|
| 模块名 / 版本 | `plugin.list[].module` / `version` |
| 种类徽章 内置 / 原生 | `plugin.list[].kind`（`shipped-native` / `native`，**没有** `descriptor`） |
| 来源（决定删除是否禁用） | `plugin.list[].source`：`shipped`（受保护，删除禁用）/ `user` |
| 状态徽章 已加载 / 加载失败 / 未加载 | `plugin.list[].loaded` + `error`：`loaded=true` → 已加载；`loaded=false` 且有 `error` → 加载失败；清单里存在但既未加载也无错误 → `error = "not loaded"`（显示"未加载"） |
| 红色错误文案 | `plugin.list[].error` |

- 工具栏：「添加插件」→ `plugin.add {module, path?, config?}`（`config` 是 JSON，需要 JSON 编辑器）；「重载」→ `plugin.reload`（重载后刷新列表并**重新拉工具列表**——插件的工具会随之增减）。
- 「删除」→ `plugin.delete {module}`，`shipped-native` 会被拒（界面前置禁用）。
- 清单来源顺序：`SHIPPED_MANIFEST`（5 个核心内置，总是先加载）→ `server.config.json` 的 `tools.atomic_extensions` 选中的 `EXTENDED_MANIFEST`（6 个扩展内置）→ 用户插件（`server.config.json` 的 `plugins` 段，其次 `<output>/plugins.json`）。界面上**不需要**展示这个顺序，但"内置"徽章覆盖前两段。
