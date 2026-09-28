# ⑦ 工具 `/tools`

- **导航态**：工具（选中）。**工具 / 环境 / 插件是三个独立页面**（`/tools`、`/tools/env`、`/tools/plugins`），同属「工具」这一个一级导航项；三页各自有**自己的页面标题、描述、工具栏与空态**，靠页面头右侧的**区段切换**互相跳转（不是同页 tab 面板）。
- **前置**：先跑 [`00-shell.md`](./00-shell.md) 并在 Edit Theme 里锁定主题
- **功能元素来源**：[08 §3 · S6.1 工具](../08-前端页面与功能清单.md)
- **本屏产出**：常规态（卡片网格）+ 空态；浅 / 深两态
- **说明**：本页是"这台机器上有哪些能力单元"。**环境依赖必须写在卡片上**（`env_deps` × `env.list`）——工具"不可用"最常见的原因就是某个环境没配好，只给一个「不可用」徽章等于不说原因。另外两页见 [`08-envs.md`](./08-envs.md)、[`09-plugins.md`](./09-plugins.md)。

## 提示词（逐字粘贴，不要改写）

```text
沿用同一外壳，导航「工具」选中。这是「工具」页面。
页面头：左侧标题「工具」+ 一句话描述「已发现的能力单元：来源、可用状态、实际路径，以及它依赖的运行环境。」；
标题右侧是区段切换（分段控件）「工具 | 环境 | 插件」，当前「工具」为选中态。
工具栏：主按钮「导入工具包」、次按钮「导入描述符」，右侧刷新图标按钮。
下方是两列工具卡片网格，每张卡片：
- 左侧方形图标
- 名称（等宽字体，示例 file.read）、来源徽章「内置」（另有「已导入」「插件」两种取值）、状态徽章「可用」
  或「不可用」（不可用为橙色警示色）
- 一行灰色小字：一句话描述 · 版本号（v1.0.0）· 操作数（3 个操作）
- 一行等宽小字：实际路径（浅色底），示例 cli/registry/tools/file_read.json
- 若该工具声明了运行环境依赖，再出一行小徽章：已就绪的写「需要 Python · 已检测」（绿色），
  缺失的写「需要 Java · 未配置」（橙色）；没有声明依赖的卡片**不显示这一行**
  （例：file.read 与 shell.exec 无依赖 → 无此行；apk.audit → 「需要 Python · 已检测」可用；
   apk.sign → 「需要 Java · 未配置」且状态徽章是「不可用」）
- 右上角 ⋯ 菜单（自定义路径 / 删除）
再出一版空态：居中引导「从 examples/ 导入工具描述符」，一个主按钮「导入工具包」。
```

> ⚠️ 三个不要：① **不要把工具 / 环境 / 插件画成一屏三个 tab 面板**（它们已经是三个页面：各自有标题、描述、工具栏，靠区段切换跳转）；② **不要只给「不可用」而不写原因**——该工具声明的 `env_deps` 里凡是未检测到的环境，都要用橙色徽章点名（`需要 Java · 未配置`）；③ **不要给没有声明依赖的工具编造依赖徽章**（内置工具 `env_deps` 为空是事实，不是缺数据）。

## 字段与数据来源

| 卡片元素 | 来源 |
|---|---|
| 名称 / 版本 / 操作数 / 描述 / `ports` / `operations` | `workflow.list_tools` |
| 来源徽章 内置（`kind = shipped-native`）/ 插件（`native`）/ 已导入（`descriptor`） | `workflow.list_tools` 的 `kind` |
| 状态徽章 可用 / 不可用 | `workflow.list_tools` 的 `is_valid`（或 `tool.get_tools` 的 `status`） |
| 实际路径 | `tool.get_tools` 的 `path`（`refresh: true` 可重新探测）/ `tool_path` |
| **环境依赖徽章** | `workflow.list_tools[].env_deps`（**只有描述符工具返回**，字符串数组如 `["java"]`）**join** `env.list[]`（按 `name` 匹配，取 `display_name` + `is_valid`）——`is_valid` 为真 → 绿「已检测」，假 → 橙「未配置」 |
| 自定义路径覆盖 | `tool.get_custom_paths` |

## 边界

- **`env_deps` 只有描述符工具有**：内置工具（`file.read` / `shell.exec` / `exec.code` …）当前的 `workflow.list_tools` 与 `tool.get_tools` 都**不返回**该字段（缺口 #18）。所以"这张卡片为什么不显示依赖"有两种情况：真的没声明（描述符里 `env_deps: []`）与后端不返回（内置/插件工具）——**界面都表现为"不显示"，不要用占位文字解释**。
- `tool.get_tools` 的**列表分支不返回 `env_deps`**，只有单工具分支返回；卡片上的依赖一律用 `workflow.list_tools` 的字段，不要依赖列表分支。
- `tool.add` / `tool.delete` / `tool.import_pack` 失败时后端**抛错**（error envelope → 渲染层 `BackendError`），不是 `{"error": ...}` 成功 payload（缺口 #7 已修）；坏目录 / 空目录同样走异常路径。
- 详情展开：`ports.inputs` / `ports.outputs`（类型、必填、`options`、`direction: "output"` 的产物端口）、每个 `operations[]`（名称、描述、inputs、outputs）。
- 空态文案**不点名 `android` 子目录**（退役边界，同 [08 §2.1](../08-前端页面与功能清单.md)）。
