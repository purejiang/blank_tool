# 插件架构

> 本文档描述 Blank Tool 的插件体系：两层插件模型（native Python 与描述符即声明式插件）。架构总览见 [02-系统架构.md](./02-系统架构.md)，数据模型见 [03-数据模型.md](./03-数据模型.md)。

## 描述符即声明式插件

工具描述符（tool descriptor）本质上就是第二层插件：一份纯 JSON 声明，经 `ToolDescriptor` / `DescriptorTool` 变成可注册、可发现、可执行的工具。它与 `native` 插件的差别不在"是不是插件"，而在执行边界。

### 两层插件模型

| 维度 | native（含 shipped-native） | descriptor |
|---|---|---|
| 载体 | Python 包 + `apply(ctx, config)` 入口（`cli/app/plugins/`） | JSON 文件（`ToolDescriptor` 字段，`cli/app/tools/descriptor_tool.py`） |
| 执行边界 | **进程内**：与后端同一 Python 解释器，直接注册实例进共享注册表 | **进程边界**：经 `CommandExecutor` 以子进程方式运行，后端进程不执行工具代码 |
| 语言 | 仅 Python | 任意：由 `type` 字段决定运行器（binary / java_jar / python_script / node_script / shell_script） |
| 注册方式 | `apply(ctx, config)` → `PluginContext.register_tool` → `ToolRegistry.register_plugin_tool(name, tool, kind)` | 扫描 bundled/overlay 工具目录 → `self._descriptor_tools[name] = DescriptorTool(...)`（`tool_manager.py:175`） |
| 注册 kind | `"shipped-native"`（内置 20 个原子工具）或 `"native"`（用户插件） | `"descriptor"`（`workflow_handler.py:139-143`：非前两种 kind 且为 `DescriptorTool`/带 `_descriptor` 属性时归入） |
| 生命周期 | 由 `app.plugins.loader.PluginLoader` 管理（config list + importlib + load/unmount）；`unmount_all` 只卸载 `native`，`shipped-native` 常驻 | 与注册表同生命周期：`refresh`/`_rediscover_descriptors` 重建，`add_descriptor_file` / `delete_descriptor`（T15）增删 |
| 对工作流上下文 | 可访问完整 `ToolContext`（`stream_handler`、`engine`、`template_store`） | 只能拿到 inputs 绑定值与 `ToolContext` 转成的 `CommandExecutionContext`（cwd/task_id/env） |

### 解析流程

- `apply(ctx, config)` 是唯一的 native 插件入口（`loader.py:_invoke_apply` 会按 `inspect.signature` 自适应 1 参/2 参）。manifest 优先级：`SHIPPED_MANIFEST`（启动必载，`loader.py:63`）→ `server.config.json` 的 `plugins` → `<output_dir>/plugins.json`。
- 描述符发现：`_discover_descriptors` 扫描 bundled 目录与 overlay 目录，`load_descriptor` 校验 JSON 后构造 `DescriptorTool`，写入 `_descriptor_tools`；脚本类描述符经 `add_descriptor_file` 导入时会把脚本文件复制进 `<overlay>/scripts/<tool_name>/` 并把 `path` 改写为复制位置，保证 JSON 自包含。
- `get()` 解析优先级（`tool_manager.py:186`）：实例缓存 → `_plugin_tools`（`shipped-native` 内置工具在同名冲突时胜出）→ `_descriptor_tools` → `_discovered` 代码类。

### `type` 字段：声明式执行模型

`ToolDescriptor._VALID_TYPES`（`descriptor_tool.py:91-93`）只有五个取值，且**允许按平台覆盖**（`type` 可为字符串或 `{"win": ..., "mac": ..., "linux": ...}` 字典，例如 apksigner 在 Windows 是 `java_jar`、在 mac/linux 是 `binary`）：

| type | 执行方式（`DescriptorTool._build_command`，`descriptor_tool.py:644`） | 所需 env_dep（`_INTERPRETER_DEP_BY_TYPE`，`descriptor_tool.py:280-284`） |
|---|---|---|
| `binary` | 直接执行 `tool_path` + 命令 | 无（但可用 `env_deps` 声明其他依赖） |
| `java_jar` | `[java, "-jar", tool_path]` + 命令 | `java` |
| `python_script` | `[python, tool_path]` + 命令 | `python` |
| `node_script` | `[node, tool_path]` + 命令 | `node` |
| `shell_script` | 平台 shell（Windows 用 `COMSPEC`/cmd.exe，其余 `/bin/sh`）+ `tool_path` + 命令 | 无 env_dep（shell 本身即运行器） |

解释器来源（`_interpreter_for`，`descriptor_tool.py:683`）：优先取描述符 `env_deps` 里声明的、经 `EnvironmentRegistry` 解析出的二进制路径；未声明时回退 `app.utils.env` 的 `get_java_bin` / `get_python_bin` / `get_node_bin`。

**脚本类型有前置门禁**（`_ensure_script_env_available`，`descriptor_tool.py:602`）：`python_script` / `node_script` / `shell_script` 在拼命令之前必须确认运行器可用，否则直接抛 `ToolException`、不产生任何子进程；且解释器依赖**必须显式写在描述符的 `env_deps` 里**并解析成功，不沿用遗留 helper 兜底。`shell_script` 则要求能找到平台 shell。

### 描述符的声明内容

`ToolDescriptor`（`descriptor_tool.py:65-126`）把"工具是什么"与"工具怎么执行"全部做成数据：

- **位置**：`path` 支持绝对路径、相对路径（先相对描述符所在目录，再相对 runtime 目录）与按平台字典（`_resolve_tool_path`，`descriptor_tool.py:316`）。
- **依赖**：`env_deps` 声明运行所需的命名环境，逐个经 `EnvironmentRegistry` 解析（`_resolve_env_deps`）。
- **校验与版本**：`validate`（`cmd` / `expect_returncode` / `expect_contains` / `expect_in`）与 `version`（`cmd` / `regex` / `from_stream`）都是声明式命令，`is_valid` = env 依赖全部解析 + 二进制存在 + validate 通过（`descriptor_tool.py:363-369`）。
- **类型化出入参**：`inputs` / `outputs` 复用 `Port` 类型系统；`operations[]` 为每个命名操作声明自己的 ports 与 `args_map`（`{"param": name}` 代入输入值、`{"flag": name, "value": arg}` 布尔开关），并支持 per-operation `timeout` / `cwd` 覆盖（`$workdir`、`$inputs.<key>`）。
- **日志脱敏**：`sensitive_arg_patterns` 是 CommandExecutor 自带脱敏之外的扩展点。

### 设计含义

- **native = 在进程内写 Python**：可以触碰工作流引擎、模板库、流式回调等后端对象，代价是"零安装、但语言锁定 Python、且运行在后端进程里"。它适合编排逻辑、需要访问上下文的能力。
- **descriptor = 在进程边界外声明任意命令**：不写一行可执行代码，`type` 决定运行器，语言可以是 Java / Python / Node / shell / 任意二进制，后端只是拼命令、起子进程、按声明校验与取版本。它适合封装外部工具与脚本，缺点是无法访问后端对象，只能通过类型化 ports 交换数据。
- 两者共存于同一注册表、同一套 `list_tools` kind 体系（shipped-native / native / descriptor），工作流引擎对它们统一按 `get_tool` 解析、按 ports 校验、按 `execute(inputs, context)` 调用。
