# Blank Tool 文档中心

Blank Tool（本地工作流编排应用）的工程文档入口。旧文档（`BACKEND_API.md`、`ARCHITECTURE_OPTIMIZATION_PROPOSAL.md` 等）已**删除**，如需追溯请从 git 历史恢复；请以本目录下的新文档为准。

## 文档导航

| 文档 | 一句话说明 | 适合谁 |
|---|---|---|
| [01-产品概述](./01-产品概述.md) | 产品定位、功能特性、技术栈与目标用户 | 产品经理、新同学快速了解产品全貌 |
| [02-系统架构](./02-系统架构.md) | Renderer / Main / Python 三进程架构、IPC 与数据流 | 想搞懂全链路的人、架构评审 |
| [03-数据模型](./03-数据模型.md) | 工具描述符、环境描述符、WorkflowDefinition、Port 类型系统等核心数据模型 | 做后端/引擎/编辑器开发的工程师 |
| [04-开发指南](./04-开发指南.md) | 常用命令、测试体系、如何新增 handler / 工具 / 环境 / 工作流、排障手册 | 所有在仓库里写代码的人（必读） |
| [05-分期开发计划](./05-分期开发计划.md) | Phase 0~6 的开发阶段划分、任务清单与验收要点 | 制定排期、领取任务、验收的人 |
| [06-后续路线图](./06-后续路线图.md) | 已确认延后的功能清单（DAG 分支/并行、动态参数源等）及前置依赖 | 产品决策、远期规划 |
| [07-UI设计规范](./07-UI设计规范.md) | 界面重设计的功能契约与 Stitch 设计产出指引（提示词全集） | 做 UI 设计/前端实现的人 |

> 说明：01~07 均为当前有效文档，导航表链接均可直接打开。旧文档已删除，需要时从 git 历史恢复。

## 一句话概览

Blank Tool 是本地工作流编排桌面应用（Electron + Vue3 + Python 三进程）：把本地命令行工具、脚本与运行时封装为**带类型化出入参的工具**，用**线性工作流**编排成可保存、可复用的模板，在任务中心或无头 CLI 中执行；模型通用、领域无关，后端同时是一个**无状态 CLI**（`cli/cli.py`），可脱离 Electron 单独跑工作流。**应用本体零领域内容**：工作流、工具描述符与二进制均不内置；仓库 `examples/` 提供可导入示例包：通用示例工作流（`examples/workflows/generic/`，仅内置原子工具、零外部依赖、导入即跑）与 Android 示例包（工作流 + 工具描述符），经工作流/工具导入功能引入，二进制由用户自备。该调整**已完成**（T21，2026-08-04）。

## 当前状态速览

### 已具备

- **工作流引擎**：`cli/app/workflow/`，线性执行（`node.next` 驱动），内置 23 个原子工具 + 描述符工具，支持 `on_failure`（fail / skip / retry:N）与节点级流式事件。
- **模板 CRUD + 执行**：`template.save / load / list / delete / execute`，落盘到 `<output_dir>/templates`（可被 `BT_TEMPLATES_DIR` 覆盖）。
- **工具/环境描述符发现**：工具描述符不再内置，`cli/registry/tools/` 已清空（仅 README）；Android 描述符（12 个）已迁至 `examples/tools/android/`，经工具管理导入后进入可写注册表（T15/T21）；`cli/registry/environments/*.json`（java / python / node 3 个环境，保持内置）自动加载。
- **统一工具「操作」模型（T3-T5）**：描述符增加 `operations[]`，每个操作带类型化 inputs/outputs + args 映射；引擎按 operation 校验输入、拼命令、返回类型化输出（`engine.py` 的 `_execute_operation_tool`）；APK 链路工具（apktool / adb / bundletool）已迁移为范例。
- **单选/多选入参（T2）**：`Port` 已支持 `options`（单选下拉）与 `multi`（多选）字段，贯穿 schema、序列化与校验。
- **脚本作为工具（T17）**：脚本可经 `*_script` 类型封装为"可导入的依赖环境的工具/节点"（如 `examples/tools/android/apk-audit.json`）；CLI 新增 `tool <name>` 子命令（T18）。
- **遗留模块退役（T22/T23）**：Android 专属页面（PackagePage / DevicePage / APK 工具）与其服务/store/组件、签名配置区，以及对应后端 handler（apk./aab./device./install./download 等）与契约测试均已删除。
- **任务中心**：`taskStore` + `TaskStreamService`，任务本地持久化、流式日志、取消。
- **工作流编辑器**：`/workflow-editor`（vue-flow 画布），节点拖拽、连边、序列化/反序列化、模板保存。

### 已解决

- **`cli/app/protocol.py` 与 `cli/app/protocol/` 包同名冲突（已修复）**：包目录曾遮蔽同名模块，导致 `from app.protocol import ...`（`api_handler.py`、`main.py`）导入失败、后端无法启动。现已修复：`cli/app/protocol/__init__.py` 统一导出消息类与类型系统（当前为 `BackendSuccessPayload`/`BackendErrorPayload`/`ErrorCode` + `BaseType`/`TypeAnnotation`/`Port`/`PortSet`），后端可正常启动；`cli.py` 亦从 `main` 导入复用 `bootstrap`（`from main import bootstrap`），无需各自维护。

### 规划中

- **新四模块 IA（模块与界面重设计，部分完成）**：Android 遗留模块已退役删除（T22/T23，见上）；新 IA 的目标形态为 工作流 `/workflows`、任务 `/tasks`、工具 `/tools`、设置 `/settings` 四个一级模块——其中 设置 `/settings`、关于 `/about`、诊断 `/diagnostics` 与工作流编辑器 `/workflow-editor` 已就位，工作流列表页、任务页、工具页仍**规划中**（结构/交互重设计；视觉以用户确认的 Stitch 设计稿为准，见 [01-产品概述](./01-产品概述.md#6-现状-vs-规划)）。
- 工作流模块 `/workflows`（管理列表 + 二级编辑器 `/workflows/editor/:name?`；导入/导出）。
- 任务模块 `/tasks`（选模板 → 动态表单 → 实时进度/日志 → 历史筛选）。
- 工具与环境模块 `/tools`（描述符导入/删除、自定义路径）。
- **冷启动与 UX 基调（部分完成）**：通用示例工作流 `examples/workflows/generic/` 已随外部化落地；新模块空状态引导（工作流空 → 导入示例/新建，任务空 → 去创建工作流，工具空 → 从 examples/ 导入描述符）、任务历史状态/名称筛选、任务完成/失败应用内提示 + 可选系统通知仍**规划中**。

详见 [05-分期开发计划](./05-分期开发计划.md) 与 [06-后续路线图](./06-后续路线图.md)。
