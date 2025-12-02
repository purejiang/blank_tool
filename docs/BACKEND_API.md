# 后端服务端文档

## 概述
- 进程入口：`backend/main.py`，负责从 `stdin` 逐行读取 JSON 请求并写入 JSON 响应与事件到 `stdout`（backend/main.py:31-49）。
- 事件发送：使用 `send_event(event_name, data)` 输出事件（backend/main.py:23-26）。
- Electron 主进程启动与桥接：在 `src/main/main.js` 启动 Python 进程并解析 `stdout`，将事件广播到所有窗口（src/main/main.js:94-127）。

## 进程生命周期
- 启动：`spawn('python', [backend/main.py])`（src/main/main.js:94-99）。
- 输出处理：按行拆分并 `JSON.parse`；遇到事件进行广播（src/main/main.js:100-113）。
- 错误输出：`stderr` 打印到控制台（src/main/main.js:119-121）。
- 退出与清理：`close` 事件重置引用；`before-quit` 杀掉后端进程（src/main/main.js:123-127,174-183）。

## 通信协议
- 请求格式：
  - `id`: 字符串或数字（请求标识）
  - `method`: 字符串（方法名，如 `adb.devices`）
  - `params`: 字典对象（方法参数）
- 响应格式：
  - 成功：`{"id": <id>, "result": <任意对象>}`（backend/main.py:37-39；backend/app/api_handler.py:41-42）
  - 失败：`{"id": <id|null>, "error": {"code": <int>, "message": <string>}}`
    - `-32700` 解析错误（backend/main.py:41-44）
    - `-32603` 内部错误（backend/main.py:46-49）
    - `-32601` 方法未找到（backend/app/api_handler.py:33-34）
    - `-32000` 服务端错误（backend/app/api_handler.py:44-46）
- 事件格式：
  - 后端输出：`{"type":"event","event":"stream.event","data":{...}}`（backend/main.py:23-26；backend/app/api_handler.py:53-55）
  - 主进程路由：将 `stream.event` 映射为语义化事件并广播（src/main/main.js:100-113）：
    - `logcat-output` → `{stream_id, process_id, line}`
    - `logcat-finished` → `{stream_id, process_id, return_code}`
    - `logcat-error` → `{stream_id, message}`

## API 列表
### adb.devices
- 方法名：`adb.devices`
- 入参：`{}`
- 返回：`{"type":"success","payload":["<device_id>", ...]}`（backend/app/handlers/adb_handler.py:8-22）
- 工具调用：`AdbTool.get_devices()`（backend/app/tools/command/adb_tool.py:64-84）

### adb.logcat
- 方法名：`adb.logcat`
- 入参：`{"device_id":"<id>"}`（backend/app/handlers/adb_handler.py:23-43）
- 返回：`{"stream_id":"<id>"}`（backend/app/api_handler.py:70-71）
- 事件：
  - 日志输出：`logcat-output`（主进程路由，src/main/main.js:100-113）
  - 进程结束：`logcat-finished`
  - 错误：`logcat-error`
- 实现要点：后端通过 `execute_stream` 启动流式日志（backend/app/handlers/adb_handler.py:37-38）。

### adb.stop_logcat
- 方法名：`adb.stop_logcat`
- 入参：`{"process_id":"<id>"}`（backend/app/handlers/adb_handler.py:60-78）
- 返回：`{"type":"success"|"warning"|"error","payload":{"message":<string>}}`
- 说明：当前使用 `process_id`；可演进为使用 `stream_id` 来统一标识。

## 分发与工具层
- 分发器：`ApiHandler` 自动加载 `app.handlers` 下的 `API_MAP` 并按方法分发（backend/app/api_handler.py:14-22,30-31）。
- 参数协议：已统一为字典；非流式调用 `handler(params)`（backend/app/api_handler.py:25-46）。
- 流式包装：`stream_handler` 启动线程并将消息封装为事件（backend/app/api_handler.py:48-72）。
- 工具管理：`ToolManager.get_tool('adb')` 获取 ADB 工具实例（backend/app/handlers/adb_handler.py:10-12）。
- ADB 工具：
  - 设备列表：`get_devices()`（backend/app/tools/command/adb_tool.py:64-84）
  - 启动日志：`execute_stream(...)`（backend/app/tools/command/adb_tool.py:96-99）
  - 停止日志：`stop_process(process_id)`（backend/app/tools/command/adb_tool.py:101-110）

## 错误与日志
- 错误事件：统一使用 `{type:'error', payload:{message}}`（backend/app/api_handler.py:62-66）。
- 服务端错误码：见“通信协议”。
- 主进程容错：解析失败 `try/catch` 并忽略异常（src/main/main.js:100-116）；未知事件保留原通道回退广播（src/main/main.js:100-113）。

## 安全与资源管理
- 写入锁：`stdout_lock` 保证事件与响应写入的原子性（backend/main.py:14-22）。
- 退出清理：主进程在退出前销毁托盘并杀掉 Python 进程（src/main/main.js:174-183）。
- Electron 安全：`nodeIntegration:false`、`contextIsolation:true`（src/main/main.js:21-22）。

## 端到端调用示例
### 获取设备列表
请求（一行 JSON）：
```json
{"id":"req-1","method":"adb.devices","params":{}}
```
响应：
```json
{"id":"req-1","result":{"type":"success","payload":["emulator-5554"]}}
```

### 启动 logcat 并接收事件
请求：
```json
{"id":"req-2","method":"adb.logcat","params":{"device_id":"emulator-5554"}}
```
响应：
```json
{"id":"req-2","result":{"stream_id":"adb_logcat-1"}}
```
事件（主进程路由后）：
```json
{"type":"event","event":"logcat-output","data":{"stream_id":"adb_logcat-1","process_id":"123","line":"11-12 10:00:00 I/ActivityManager..."}}
```

## 与 Electron 对接
- 预加载统一入口：`callBackendAPI(action, params)`（src/main/preload.js:4-12）。
- 主通道：`ipcMain.handle('call-backend-api', ...)`（src/main/ipc/commandHandlers.js:34-39）。
- 事件订阅建议：渲染层使用预加载暴露的 `onLogcatOutput` 等方法（src/main/preload.js:141-148）。

## 兼容性与演进
- 命名空间对齐：建议统一使用 `adb.*` 方法名；若需兼容旧的 `device.*`，可在 `API_MAP` 中增加别名。
- 流标识统一：建议将 `adb.stop_logcat` 入参统一为 `stream_id`，并在工具层维护映射。

## 变更记录（首次撰写）
- 统一 `params` 为字典；事件路由为语义化通道；渲染层使用统一后端入口。

