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

> 说明：01~06 均为当前有效文档，导航表链接均可直接打开。旧文档已删除，需要时从 git 历史恢复。

## 一句话概览

Blank Tool 是本地工作流编排桌面应用（Electron + Vue3 + Python 三进程）：把本地命令行工具、脚本与运行时封装为**带类型化出入参的工具**，用**线性工作流**编排成可保存、可复用的模板，在任务中心或无头 CLI 中执行；模型通用、领域无关，后端同时是一个**无状态 CLI**（`backend/cli.py`），可脱离 Electron 单独跑工作流。**应用本体零领域内容**：工作流、工具描述符与二进制均不内置；仓库 `examples/` 提供可导入的 Android 示例包（工作流 + 工具描述符），经工作流/工具导入功能引入，二进制由用户自备。该调整**已决策、分期实施**（见 [05-分期开发计划](./05-分期开发计划.md#phase-1-基础模型)）。

## 当前状态速览

### 已具备

- **工作流引擎**：`backend/app/workflow/`，线性执行（`node.next` 驱动），内置 18 个原子工具 + 描述符工具，支持 `on_failure`（fail / skip / retry:N）与节点级流式事件。
- **模板 CRUD + 执行**：`template.save / load / list / delete / execute`，落盘到 `<output_dir>/templates`（可被 `BT_TEMPLATES_DIR` 覆盖）。
- **工具/环境描述符发现**：`backend/registry/tools/*.json`（当前 7 个 Android 描述符内置；**已决策**外部化至 `examples/tools/android/`，见 [05-分期开发计划](./05-分期开发计划.md#phase-1-基础模型)）与 `backend/registry/environments/*.json`（java / python / node 3 个环境，保持内置）自动加载。
- **任务中心**：`taskStore` + `TaskStreamService`，任务本地持久化、流式日志、取消。
- **工作流编辑器**：`/workflow-editor`（vue-flow 画布），节点拖拽、连边、序列化/反序列化、模板保存。

### 关键待修（阻塞项）

- **`backend/app/protocol.py` 与 `backend/app/protocol/` 包同名冲突**：包目录遮蔽同名模块，导致 `from app.protocol import BackendResponse`（`api_handler.py:19`）与 `from app.protocol import ErrorCode`（`main.py:26`）在导入期抛 `ImportError`，后端启动即崩溃，所有请求被拒（"后端服务已退出"）。这是 Phase 0 的阻塞项，修法见 [04-开发指南#排障](./04-开发指南.md#排障) 与 [05-分期开发计划#Phase-0](./05-分期开发计划.md#phase-0-稳定性阻塞项)。

### 规划中

- 统一工具「操作」模型（operations，每个操作带类型化 inputs/outputs + args 映射）。
- **领域内容外部化（已决策）**：Android 工作流与工具描述符迁至 `examples/`，应用零内置领域内容；工作流经管理页/编辑器导入、描述符经工具管理页导入，二进制由用户自备（见 [05-分期开发计划](./05-分期开发计划.md#phase-1-基础模型)）。
- 工作流管理列表页（一级路由 `/workflow`）。
- 工具/环境管理页（描述符 CRUD + 导入/删除）。
- 脚本执行（脚本作为"可导入的依赖环境的工具/节点"）。

详见 [05-分期开发计划](./05-分期开发计划.md) 与 [06-后续路线图](./06-后续路线图.md)。
