# 后端服务最佳实践（纯服务端）

## 总览与原则
- 目标：高可靠、安全、可维护、可观测；在桌面环境/本地工具中作为独立后端进程运行。
- 原则：最小权限、显式依赖、配置外置、日志结构化、错误明确、协议稳定。
- 面向对象：后端开发、测试、运维与架构设计者。

## 运行模型
- 进程：单独后端进程，负责处理请求与产生事件；必要时使用线程/子进程隔离 CPU/IO 密集任务。
- 输入/输出：按“行分隔的 JSON”协议进行通信；每一行是一个完整的 JSON 对象。
- 生命周期：启动→运行→优雅退出；支持中断信号处理（如 `SIGTERM`），设定最大退出等待时间与强制清理策略。
- 背压：对输入请求设定队列与并发上限；输出采用分帧与批量策略，避免一次性大量写入导致阻塞。

## API 设计规范
- 命名：`命名空间.动作`（如 `adb.devices`、`log.preview`），统一使用 `snake_case` 字段。
- 版本：为接口定义版本（如 `v1`），稳定期内仅做兼容变更；不兼容变更通过新版本发布。
- 幂等：查询类接口必须幂等；变更类接口需支持幂等键（如 `idempotency_key`）。
- 资源 vs 动作：优先资源化（列表/详情/创建/删除），动作场景明确使用动词（如 `reboot`、`sign`）。

## 请求与响应协议
- 请求：`{ "id": string|number, "method": string, "params": object }`
- 成功响应：`{ "id": <id>, "result": <object> }`
- 失败响应：`{ "id": <id|null>, "error": { "code": <int>, "message": <string>, "data": <optional> } }`
- 错误码建议：
  - `-32700` 解析错误（JSON 语法错误）
  - `-32601` 方法不存在
  - `-32602` 参数无效（验证失败）
  - `-32603` 内部错误（未分类异常）
  - `-32001` 权限不足
  - `-32002` 资源不可用/不存在
  - `-32003` 超时/取消
- 分页与过滤：对于列表接口统一支持 `page`, `page_size`, `sort`, `filter` 字段；默认边界与最大值限制。

### 错误码目录（扩展说明）
- 结构：错误码需稳定且文档化，错误消息面向开发者，`data` 可包含上下文（如验证失败字段列表）。
- 建议扩展：
  - `-32010` 配置错误（非法路径、超出上限）
  - `-32020` 外部依赖不可用（工具缺失/版本不匹配）
  - `-32030` 背压触发（队列满/并发超限）
  - `-32040` 资源冲突（锁竞争失败/已占用）

示例失败响应：
```json
{"id":"req-9","error":{"code":-32602,"message":"Invalid params","data":{"field_errors":[{"field":"device_id","reason":"required"}]}}}
```

## 流式与事件（异步输出）
- 事件格式：`{ "type": "event", "event": "domain.event", "data": { ... } }`
- 命名规则：`domain.event`（如 `logcat.output`, `logcat.finished`, `device.change`）。
- 流式任务：
  - 启动接口返回 `stream_id`；任务状态为 `starting`→`running`→`stopped|finished`。
  - 事件负载包含 `stream_id` 与必要上下文（如 `process_id`, `line`, `return_code`）。
  - 停止接口接受 `stream_id`，实现优雅终止与资源释放。
- 健康与心跳：长流任务周期性发送心跳事件（如 `heartbeat`）或在空闲时维持连接标记。

### 事件契约示例
- 事件命名：`logcat.output` | `logcat.finished` | `logcat.error` | `heartbeat`
- 负载示例：
```json
// 日志输出
{"type":"event","event":"logcat.output","data":{"stream_id":"s-1","process_id":"p-1","line":"...","ts":1731400000}}
// 结束
{"type":"event","event":"logcat.finished","data":{"stream_id":"s-1","process_id":"p-1","return_code":0}}
// 错误
{"type":"event","event":"logcat.error","data":{"stream_id":"s-1","message":"adb not found"}}
// 心跳
{"type":"event","event":"heartbeat","data":{"stream_id":"s-1","interval_ms":5000}}
```

事件负载字段建议：统一包含 `stream_id`；可选 `process_id`、`ts`（Unix 毫秒时间戳）。

## 安全
- 输入验证：所有 `params` 做模式验证（类型、范围、枚举、必填/可选），拒绝未知字段（可配置）。
- 命令执行安全：避免 shell 拼接；使用参数数组传递；固定/受控工作目录；对路径与文件名进行白名单或正则校验。
- 最小权限：进程仅访问必要资源；环境变量与机密不落盘；敏感数据脱敏日志。
- 隔离策略：IO 与 CPU 密集型任务隔离到受控线程/子进程；对外部工具交互设定超时与黑/白名单。

## 资源管理
- 并发与队列：设定最大并发与排队策略（FIFO/优先级）；可配置拒绝策略（如队列满返回错误）。
- 子进程与线程：统一管理表；支持状态查询与终止；泄漏检测与超时回收。
- 句柄与临时文件：统一临时目录；生命周期管理（创建→使用→清理）；异常路径也必须清理。
- 超时与重试：为关键操作设定可配置超时；幂等的外部操作可有限次数重试（指数回退）。
- 锁与竞争：对共享资源加锁；`stdout` 写入使用互斥；避免长时间持锁。

## 日志与可观测性
- 结构化日志：统一 JSON 日志格式；字段包括 `timestamp`, `level`, `module`, `message`, `context`, `trace_id`。
- 指标：暴露核心计数器（请求量、错误量、超时量）、直方图（耗时分布）、当前并发与队列长度。
- 追踪：为每个请求/事件分配 `trace_id`/`span_id`，贯穿日志与事件。
- 告警：针对错误率、超时率、资源水位设定阈值；提供本地告警或与系统托盘/日志查看器集成。

## 配置管理
- 层级：默认值 < 环境变量 < 配置文件 < 命令行参数；明确优先级与覆盖规则。
- 热更新：支持在安全范围内的配置热更新（如并发/缓冲上限），提供回滚机制。
- 安全配置：路径白名单、最大缓冲、最大并发、超时、重试次数等关键参数默认审慎。

### 配置项建议（键与默认值）
- `server.max_concurrency`: 8（总并发上限）
- `server.queue.max_size`: 1000（请求队列最大长度）
- `server.stdout.max_line_length`: 16384（单行最大长度）
- `server.stdout.flush_interval_ms`: 0（0 表示即时刷新）
- `server.process.default_timeout_ms`: 60000（外部工具默认超时）
- `server.stream.heartbeat_interval_ms`: 5000（心跳事件间隔）
- `server.retry.max_attempts`: 2（幂等操作最大重试）
- `server.paths.temp_dir`: 系统临时目录（存在性与权限必须校验）

热更新注意：仅允许无安全风险的参数热更新（并发、队列、缓冲大小），涉及路径/权限的参数需重启生效。

## 性能与扩展性
- 并发模型选择：IO 密集优先异步/线程池；CPU 密集优先子进程/进程池；混合模型需边界清晰。
- 缓存与重用：对热路径（工具探测、设备列表）做结果缓存；设置过期与主动刷新。
- 大输出处理：分块/分帧输出；定义帧边界与最大行长度；必要时使用压缩与抽样。

### 分帧策略示例
- 分帧字段：`frame_id`, `seq`, `eof`，每帧数据包含 `payload_chunk`，接收端按 `seq` 重组，`eof`=true 表示结束。
- 使用场景：超长日志导出、批量结果传输。

## 测试与质量保障
- 单元测试：参数验证、错误码、边界条件；外部依赖使用桩/模拟。
- 集成测试：请求-响应链路与事件流；并发与背压场景；超时/重试与清理。
- 契约测试：请求/响应/事件的 schema 校验；版本升级的兼容性保障。
- 压力与稳定：长时间流任务、海量事件、资源水位与泄漏检测。

### 契约测试 Schema 示例（JSON Schema）
- `adb.devices` 入参：
```json
{"type":"object","additionalProperties":false}
```
- `adb.logcat` 入参：
```json
{"type":"object","properties":{"device_id":{"type":"string","minLength":1}},"required":["device_id"],"additionalProperties":false}
```
- `adb.stop_logcat` 入参：
```json
{"type":"object","properties":{"stream_id":{"type":"string","minLength":1}},"required":["stream_id"],"additionalProperties":false}
```

事件负载（`logcat.output`）：
```json
{"type":"object","properties":{"stream_id":{"type":"string"},"process_id":{"type":"string"},"line":{"type":"string"},"ts":{"type":"number"}},"required":["stream_id","line"],"additionalProperties":false}
```

## 运维与故障处理
- 运行手册：启动参数、日志路径、常见故障与排查步骤；核心告警项与响应策略。
- 僵死与崩溃：心跳与看门狗；自动重启策略（带冷却时间与上限）；异常报告与转储。
- 健康检查：暴露内部健康状态与最近错误；可脚本化查询。

### 运维 SOP（示例）
- 症状：请求无响应
  - 检查队列与并发水位；查看错误日志与未捕获异常；重启后端并观察恢复情况。
- 症状：事件积压
  - 检查消费者订阅与广播路径；增大缓冲或降低事件速率；确认心跳是否正常。
- 症状：外部工具不可用
  - 校验工具路径与版本；降级/回退策略；记录错误并告警。
- 症状：内存/句柄水位高
  - 开启采样与限速；清理临时文件；检查泄漏与长生命周期对象；设定并发与缓冲上限。

## 版本与兼容
- 语义化版本：`MAJOR.MINOR.PATCH`；不兼容变更在 MAJOR；MINOR 新增兼容功能；PATCH 修复。
- 弃用策略：标记、过渡期、移除计划；文档与告警提示；提供替代方案。
- 兼容窗：保留旧事件名/方法名的路由；新旧并行一段时间后通过配置切换。

## 文档规范
- 统一术语和字段命名；每个接口提供示例请求/响应/事件；错误码目录集中维护。
- 变更日志：记录协议与行为变更；标注版本与影响范围；提供迁移指南。

## 示例片段
- 示例请求：
```json
{"id":"req-123","method":"adb.devices","params":{}}
```
- 示例成功响应：
```json
{"id":"req-123","result":{"type":"success","payload":["emulator-5554"]}}
```
- 示例失败响应：
```json
{"id":"req-123","error":{"code":-32601,"message":"Method not found"}}
```
- 示例事件：
```json
{"type":"event","event":"logcat.output","data":{"stream_id":"s-1","process_id":"p-1","line":"..."}}
```

---

附录：
- 术语表：`stream_id`（流任务唯一标识）、`process_id`（子进程标识）、`heartbeat`（心跳事件）
- 约定速记：所有字段使用 `snake_case`；时间统一为 Unix 毫秒；布尔型字段仅使用 `true/false`。
