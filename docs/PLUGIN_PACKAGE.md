# 插件包（Plugin Package）规范

插件除了单个 `.py` 文件，还可以打成一个 **zip 包**（manifest.json + 入口 py + 可选自定义 UI），
在插件页用「导入」一键安装、「导出」打包分享。旧的平铺 `.py` 完全兼容，继续可用。

## 一、包格式

```
hello-ui.zip
├─ manifest.json      # 必需：元数据 + 入口声明
├─ main.py            # 必需：入口模块，必须导出 run(context, **params)
├─ ui/index.html      # 可选：自定义前端 UI（sandboxed iframe 渲染）
└─ assets/...         # 可选：其他资源
```

zip 根目录直接放 `manifest.json`，或所有文件包在**一个**顶层文件夹里（如 `hello-ui-1.0.0/…`）均可。

### manifest.json

```json
{
  "id": "hello-ui",              // 必需，安装目录名，[字母数字_-.]，不得以 __ 开头
  "name": "Hello UI 示例",        // 显示名（缺省用 id）——仅用于界面展示
  "version": "1.0.0",
  "author": "blank_tool",
  "description": "…",
  "entry": "main.py",            // 缺省 main.py，必须位于包内
  "ui": "ui/index.html",         // 缺省无 → 插件页用参数表单渲染
  "params": [                    // 可选参数表单声明（无 ui 时渲染成表单）
    { "key": "text", "type": "string", "required": true, "default": "…" },
    { "key": "repeat", "type": "number", "default": 3 },
    { "key": "upper", "type": "bool", "default": false }
  ]
}
```

**`id` 是身份，`name` 只是标签**：安装目录名、`plugin.run` / `plugin.export` / `plugin.delete`
的参数、`sys.modules` 键全部用 `id`；`name` 仅在插件页列表与详情里显示（后端以
`display_name` 字段返回，回退到 `id`），**换 `name` 不影响任何调用**。详情页在两者不同时会把
`id` 另外标出来。平铺 `.py` 插件没有 manifest，`display_name` 即文件名。

**优先级**：模块属性（`DESCRIPTION/VERSION/AUTHOR/PARAMS`）> manifest 同名字段。

本地可导入的实例见 `output/plugin-samples/`（`scrcpy-mirror.zip` / `jadx-gui.zip`，未纳入版本库）；
自己写的插件也能用插件页「导出」生成一份带 manifest 的包当模板。

## 二、导入 / 导出

- **导入**：插件页右上「导入」→ 选 zip → 校验（manifest 唯一、id 合法、entry 存在、zip-slip 防护）
  → 解压到 `<用户插件目录>/<id>/` → 自动重新加载。同 id 已存在时会弹确认框（覆盖 = 删除旧目录重装）。
- **导出**：选中插件 →「导出」→ 选保存路径。目录插件原样打包；旧的平铺 `.py` 会自动生成一份
  manifest.json（模块元数据回填）一起打入。
- 平铺 `.py` 依旧可以直接丢进用户插件目录即插即用。

## 三、前端 UI：双模式

| 插件形态 | 插件页右侧渲染 |
|---|---|
| 无 `ui` | 参数表单（或 JSON 兜底）+ 日志控制台 + 结果面板 |
| 有 `ui` | **sandboxed iframe 自定义 UI** + 日志控制台 + 结果面板（表单隐藏） |

自定义 UI 通过 `<iframe sandbox="allow-scripts" :srcdoc="…">` 渲染（**不给**
`allow-same-origin`，opaque origin，拿不到 electronAPI / 父页面 DOM），
唯一通道是 postMessage。宿主会往 html 的 `<head>` 里注入一段桥接脚本，
包作者直接用 `window.pluginBridge`：

```js
window.pluginBridge.run(params)            // 触发后端 plugin.run（流式）
window.pluginBridge.cancel()               // 取消运行
window.pluginBridge.log(text, level)       // 直接往前端控制台写一行
window.pluginBridge.getMeta()              // 请求插件元数据
window.pluginBridge.getDevices()           // 请求设备列表快照（只读）
window.pluginBridge.pickFile(options)      // 弹原生文件选择框（Electron DialogOptions：title/filters/properties）
window.pluginBridge.onLog(cb)              // cb(text, level) 后端/自身日志
window.pluginBridge.onResult(cb)           // cb(payload) 运行完成
window.pluginBridge.onError(cb)            // cb(message) 运行出错
window.pluginBridge.onMeta(cb)             // cb({name, display_name, version, author, description, params})
window.pluginBridge.onDevices(cb)          // cb([{id, name, status}]) 设备列表快照
window.pluginBridge.onFile(cb)             // cb(canceled, filePath) 选中的文件路径（取消时 filePath 为空串）
```

iframe → 宿主消息类型（桥接脚本封装，一般不用手写）：
`plugin.ready` / `plugin.getMeta` / `plugin.run{params}` / `plugin.cancel` / `plugin.log{text,level}` /
`plugin.getDevices` / `plugin.pickFile{options}`

宿主 → iframe 消息类型：`__bridge.meta{info}` / `__bridge.log{text,level}` /
`__bridge.result{payload}` / `__bridge.error{message}` / `__bridge.devices{devices}` /
`__bridge.file{canceled, filePath}`

宿主侧只接受 `event.source === iframe.contentWindow` 且 `type` 以 `plugin.` 开头的消息（动作白名单）。

**限制**：UI 以 srcdoc 方式渲染，**相对路径资源无法解析** —— 样式/脚本一律内联，
外链资源只走 CDN（见示例的注释）。

## 四、安全边界

- iframe 无 `allow-same-origin`：插件 UI 是不可信三方代码，隔离在 opaque origin 里。
- `.py` 入口本来就是任意代码执行（与旧机制一致），插件包不提供额外沙箱；只从可信来源导入。
- 导入时的防护：manifest 唯一性、`id` 字符集白名单、entry 不得越界、逐条 zip-slip 校验。

## 五、相关代码

| 层 | 文件 |
|---|---|
| 包导入/导出 handler | `backend/app/handlers/plugin_package_handler.py`（`plugin.import` / `plugin.export`） |
| 目录插件加载 | `backend/app/plugins/manager.py`（平铺 + 目录双布局扫描） |
| 对话框 IPC | 复用既有 `showOpenDialog` / `showSaveDialog` / `readFile` |
| 插件页 UI + 桥 | `src/renderer/views/PluginsPage.vue`、`src/renderer/services/PluginService.ts` |
| 契约测试 | `tests/contracts/test_plugin_manager.py`、`tests/contracts/test_plugin_package.py` |

## 六、插件能力清单

### UI 侧（iframe 桥，`window.pluginBridge`）

**现状：**

| 能力 | 方法 | 说明 |
|---|---|---|
| 触发运行 | `run(params)` | 触发后端 `plugin.run`（流式） |
| 取消 | `cancel()` | |
| 写控制台 | `log(text, level)` | 宿主插件页控制台 |
| 插件元数据 | `getMeta()` + `onMeta` | name/display_name/version/author/description/params |
| 设备列表 | `getDevices()` + `onDevices` | 只读快照 `[{id,name,status}]`，自己渲染下拉框 |
| 文件选择 | `pickFile(options)` + `onFile` | 原生文件管理器对话框（Electron DialogOptions），只回传 `{canceled, filePath}` |

**建议新增（按实用度排序，均走白名单桥）：**

| 能力 | 形态 | 备注 |
|---|---|---|
| 目录选择 | `pickDirectory()` + `onDir` | `electronAPI.selectDirectory` 已有，照 pickFile 抄 |
| 打开文件/所在目录 | `openPath(filePath, reveal?)` | `electronAPI.openPath` 已有（reveal = 资源管理器定位） |
| 轻提示 toast | `toast(text, level)` | 宿主代发 message.success/error/warning |
| 应用内确认框 | `confirm(title, content) → bool` | Naive dialog（原生 showMessageBox 不跟主题，别用） |
| 主题/语言 | 并入 `getMeta` 返回 | `theme: 'light'\|'dark'`、`locale`，供插件 UI 适配 |
| 插件本地存储 | `kv.get/set(key)` | **iframe 是 opaque origin，localStorage 直接抛 SecurityError**，必须宿主代理；按插件 id 隔离命名空间 |

### 后端侧（`run(context, **params)` 的 PluginContext）

**现状：**

| 能力 | API | 说明 |
|---|---|---|
| 内建工具 | `context.get_tool(name)` / `context.adb` 等 | adb/apktool/aapt/apksigner/zipalign（runtime/ 内） |
| 找外部可执行文件 | `context.which(name)` | `BT_TOOL_<NAME>` env → `runtime/<name>/` → PATH |
| 跑外部命令 | `context.run_command(cmd, ...)` | 行级流式输出 + 超时 + 协作式取消 |
| 产物目录 | `context.work_dir(task_id, sub)` | 每次运行的落盘目录 |
| 结束 | `return context.finish(result)` | 保证 complete 恰好一次 |
| 流式事件 | `context.log/error/step_start/step/complete/is_cancelled` | 日志与进度 |

**建议新增：**

| 能力 | 形态 | 备注 |
|---|---|---|
| 插件安装目录 | `context.plugin_dir` | 现在靠 `os.path.dirname(__file__)` 自己拼；正式暴露后打包带工具的插件不依赖 CWD 与入口文件名 |
| 标准路径 | `context.paths` | output/cache/tasks 等，避免插件自己 import env |
| 插件配置存储 | `context.kv.get/set` | 与 UI 侧 kv 同一条链路（后端落盘，按 id 隔离） |

### 带外部工具的打包约定（如 scrcpy / jadx）

- zip 可带整个工具目录，导入时解压到 `<用户插件目录>/<id>/`（zip-slip 有防护）。
- **manifest 不管路径**：相对路径定位写在 `main.py` 里——`os.path.dirname(os.path.abspath(__file__))` 即安装目录，拼出工具绝对路径后交给 `context.run_command`。manifest 只声明 `entry`。
- 不想打包进 zip 的工具走 `context.which(name)`（放 `runtime/<name>/` 或 PATH，或 `BT_TOOL_<NAME>` env 指定）。
- 自带 adb 的工具（如 scrcpy）注意：通过 `env={"ADB": context.adb.tool_path}` 指向 runtime 的 adb，避免双 adb server 版本打架。
