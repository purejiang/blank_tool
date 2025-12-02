# Blank Tool 架构优化建议 v2.0

## 1. 概述

本文档旨在对 Blank Tool 的现有架构进行深入分析，并提出一套系统性的、可落地的优化方案。当前架构（Electron + Python）在实现跨平台桌面应用与复用现有 Android 工具链上具备优势，但在**进程通信效率**、**后端服务可用性**、**代码可维护性**和**整体稳定性**方面存在显著瓶颈。

本次优化的核心目标是：
- **提升性能:** 解决因频繁创建进程导致的性能损耗。
- **增强稳定性:** 确保长时间运行服务的可靠性，如设备监控。
- **提高可维护性:** 优化代码结构，使其更易于扩展和维护。
- **明确架构边界:** 重新定义前后端及主进程的职责，实现关注点分离。

## 2. 核心问题分析

当前架构最主要的问题在于 Electron 主进程与 Python 后端之间的通信方式。

- **现状:** 每次调用后端 API 都通过 `child_process.spawn` 启动一个新的 Python 进程，执行 `main.py` 脚本并传递命令行参数。
- **后果:**
    1.  **性能开销巨大:** 频繁创建和销毁进程的成本非常高，导致 UI 响应慢，操作延迟。
    2.  **无法维持状态:** 每个请求都是无状态的。像 `device.monitor.start` 这样的长时任务，其状态无法在后续请求中（如 `device.monitor.stop`）被管理，导致功能失效和资源泄漏（僵尸进程）。
    3.  **通信能力有限:** 仅支持简单的“请求-响应”模式，无法实现服务端主动推送（如设备插拔事件、实时日志）。
    4.  **可靠性差:** 缺乏心跳或健康检查机制，主进程无法感知 Python 服务是否异常。

## 3. 优化方案：引入常驻 Python 服务与 IPC/HTTP 通信

为了从根本上解决上述问题，建议将 Python 后端改造为一个**常驻后台服务**，并通过更高效的进程间通信（IPC）方式或本地 HTTP 服务与 Electron 主进程交互。

### 3.1. 方案对比

| 通信方式 | 优点 | 缺点 | 推荐场景 |
| :--- | :--- | :--- | :--- |
| **标准输入/输出 (Stdio)** | 实现简单，无需端口，跨平台性好。 | 协议需要自行设计（如定界符、消息格式），不易调试。 | **首选方案**。简单、高效，能满足双向通信需求。 |
| **本地 HTTP (Flask/FastAPI)** | 技术成熟，易于调试（可用浏览器/工具访问），可支持 WebSocket。 | 需要管理端口，有端口冲突风险，相比 Stdio 略重。 | 备选方案。如果未来需要更复杂的 API 或对外部开放时可考虑。 |

**结论:** 推荐采用 **Stdio** 作为主要的 IPC 机制，因为它足够轻量、高效，且能完美解决当前所有痛点。

### 3.2. 拟议的新架构

![New Architecture Diagram](https://i.imgur.com/example.png)  *（这是一个示例图链接，实际应替换为描绘新架构的图）*

1.  **Electron 主进程:**
    - 在应用启动时，仅**一次** `spawn` Python 服务进程。
    - 监听 Python 进程的 `stdout` 以接收消息，通过 `stdin` 发送指令。
    - 维护与 Python 服务的连接状态，实现心跳检测和断线重连。
    - 扮演**消息中间件**的角色，将 Python 推送的事件（如 `device-change`）转发给渲染进程。

2.  **Python 后端服务:**
    - 改造为**循环监听模式**，从标准输入读取指令。
    - 指令格式采用 JSON-RPC 或自定义的 JSON 结构（如 `{"id": 1, "method": "device.list", "params": {}}`）。
    - 将执行结果或事件通过标准输出打印（每条消息以换行符分隔）。
    - 启动时开启设备监控等常驻任务，并可在整个生命周期内管理它们。

3.  **渲染进程:**
    - API 调用方式**保持不变** (`electronAPI.callBackendAPI(...)`)。
    - `preload.js` 和主进程的 IPC 处理逻辑将内部实现从“每次 `spawn`”改为“向已存在的 Python 进程发送消息”。

## 4. 详细实施步骤

### 步骤 1: 重构 Python 后端 (`backend/`)

#### 1.1. 创建新的服务入口 (`backend/server.py`)

这个新文件将作为常驻服务的入口，取代 `main.py` 的单次执行模式。

```python
# backend/server.py
import sys
import json
import asyncio
from api_handler import APIHandler # 下一步创建

async def main():
    """
    主循环，监听标准输入并处理请求。
    """
    handler = APIHandler()
    # 初始化需要常驻的服务，例如设备监控
    await handler.initialize_services()
    
    loop = asyncio.get_event_loop()
    
    async def read_requests():
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while not reader.at_eof():
            line = await reader.readline()
            if not line:
                continue
            
            request_str = line.decode('utf-8').strip()
            if not request_str:
                continue

            try:
                request_data = json.loads(request_str)
                # 异步处理请求，不阻塞主循环
                asyncio.create_task(handler.handle_request(request_data))
            except json.JSONDecodeError:
                # 处理无效的JSON
                response = {
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"}
                }
                sys.stdout.write(json.dumps(response) + '\n')
                sys.stdout.flush()

    await read_requests()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 在退出时执行清理操作
        pass
```

#### 1.2. 创建请求处理器 (`backend/api_handler.py`)

将 `main.py` 中巨大的 `if/elif` 结构重构到一个专门的处理器类中。

```python
# backend/api_handler.py
import json
import sys
from services.device_service import DeviceService
# ... 其他服务

class APIHandler:
    def __init__(self):
        # 初始化所有服务
        self.device_service = DeviceService(self.send_event)
        # ... 其他服务
        
        # 将方法名映射到处理函数
        self.method_map = {
            "device.list": self.device_service.get_devices,
            "device.monitor.start": self.device_service.start_device_monitoring,
            "device.monitor.stop": self.device_service.stop_device_monitoring,
            # ... 其他所有方法
        }

    async def initialize_services(self):
        # 在这里启动常驻任务
        await self.device_service.start_device_monitoring()

    def send_event(self, event_name, data):
        """供服务内部调用，向主进程发送事件。"""
        event = {
            "type": "event",
            "event": event_name,
            "data": data
        }
        sys.stdout.write(json.dumps(event) + '\n')
        sys.stdout.flush()

    async def handle_request(self, request: dict):
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        response = {"id": req_id}
        
        if method in self.method_map:
            try:
                # 支持同步和异步方法
                handler = self.method_map[method]
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(**params)
                else:
                    result = handler(**params)
                response['result'] = result
            except Exception as e:
                response['error'] = {"code": -32000, "message": str(e)}
        else:
            response['error'] = {"code": -32601, "message": "Method not found"}
            
        sys.stdout.write(json.dumps(response) + '\n')
        sys.stdout.flush()
```

#### 1.3. 改造服务 (`backend/services/device_service.py`)

服务需要被改造成可以被常驻进程管理的形式。

```python
# backend/services/device_service.py (部分修改)

class DeviceService:
    def __init__(self, event_callback):
        self.event_callback = event_callback # 用于向上传递事件
        self.monitoring_task = None

    async def start_device_monitoring(self):
        if self.monitoring_task and not self.monitoring_task.done():
            return {"success": True, "message": "Monitoring is already running."}

        async def monitor():
            known_devices = set()
            while True:
                # 这里是实际的设备检测逻辑
                current_devices = self._get_current_devices() 
                
                added = current_devices - known_devices
                removed = known_devices - current_devices

                if added or removed:
                    self.event_callback("device-change", {
                        "all": list(current_devices),
                        "added": list(added),
                        "removed": list(removed)
                    })
                
                known_devices = current_devices
                await asyncio.sleep(5) # 每5秒检查一次

        self.monitoring_task = asyncio.create_task(monitor())
        return {"success": True, "message": "Device monitoring started."}

    async def stop_device_monitoring(self):
        if self.monitoring_task:
            self.monitoring_task.cancel()
            self.monitoring_task = None
        return {"success": True, "message": "Device monitoring stopped."}
    
    # ... 其他方法保持或按需改为异步
```

### 步骤 2: 更新 Electron 主进程 (`src/main/`)

#### 2.1. 创建 Python 服务管理器 (`src/main/pythonService.js`)

封装与 Python 子进程的交互逻辑。

```javascript
// src/main/pythonService.js
import { spawn } from 'child_process';
import { BrowserWindow } from 'electron';
import path from 'path';

let pythonProcess = null;
const pendingRequests = new Map();
let requestIdCounter = 0;

function startPythonService() {
    // 注意：路径需要根据实际打包结构调整
    const scriptPath = path.join(__dirname, '../../backend/server.py');
    pythonProcess = spawn('python', [scriptPath]);

    pythonProcess.stdout.on('data', (data) => {
        const messages = data.toString().split('\n').filter(Boolean);
        messages.forEach(message => {
            try {
                const parsed = JSON.parse(message);
                if (parsed.type === 'event') {
                    // 是事件，广播给所有窗口
                    BrowserWindow.getAllWindows().forEach(win => {
                        win.webContents.send(parsed.event, parsed.data);
                    });
                } else if (parsed.id !== undefined) {
                    // 是响应，解析并完成对应的 Promise
                    if (pendingRequests.has(parsed.id)) {
                        const { resolve, reject } = pendingRequests.get(parsed.id);
                        if (parsed.error) {
                            reject(new Error(parsed.error.message));
                        } else {
                            resolve(parsed.result);
                        }
                        pendingRequests.delete(parsed.id);
                    }
                }
            } catch (e) {
                console.error("Error parsing message from Python:", e, message);
            }
        });
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`Python stderr: ${data}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`Python service exited with code ${code}`);
        pythonProcess = null;
        // 可在此处添加重连逻辑
    });
}

function callPythonAPI(method, params = {}) {
    return new Promise((resolve, reject) => {
        if (!pythonProcess) {
            return reject(new Error("Python service is not running."));
        }

        const requestId = requestIdCounter++;
        const request = {
            id: requestId,
            method: method,
            params: params,
        };

        pendingRequests.set(requestId, { resolve, reject });
        
        // 设置超时
        setTimeout(() => {
            if (pendingRequests.has(requestId)) {
                pendingRequests.delete(requestId);
                reject(new Error(`Request ${requestId} (${method}) timed out.`));
            }
        }, 30000); // 30秒超时

        pythonProcess.stdin.write(JSON.stringify(request) + '\n');
    });
}

export { startPythonService, callPythonAPI };
```

#### 2.2. 修改主进程入口 (`src/main/main.js`)

集成 `pythonService`。

```javascript
// src/main/main.js (部分修改)
import { startPythonService, callPythonAPI } from './pythonService.js';

// ...

// 替换旧的 commandHandlers
ipcMain.handle('call-backend-api', async (event, method, params) => {
    try {
        const result = await callPythonAPI(method, params);
        return { success: true, data: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

app.whenReady().then(() => {
    startPythonService(); // 启动 Python 服务
    createWindow();
    // ...
});

app.on('before-quit', () => {
    if (pythonProcess) {
        pythonProcess.kill(); // 确保退出时杀死子进程
    }
    // ...
});
```

### 步骤 3: 简化 `preload.js`

`preload.js` 的职责变得非常纯粹，只需暴露一个统一的调用函数和事件监听接口。

```javascript
// src/main/preload.js (简化后)
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  // 统一的后端API调用接口
  callBackend: (method, params) => ipcRenderer.invoke('call-backend-api', method, params),

  // 监听从主进程转发来的后端事件
  on: (eventName, callback) => {
    const subscription = (event, ...args) => callback(...args);
    ipcRenderer.on(eventName, subscription);
    
    // 返回一个取消订阅的函数
    return () => {
      ipcRenderer.removeListener(eventName, subscription);
    };
  }
});
```

## 5. 建议的项目结构调整

```
backend/
│
├── server.py             # 新增：常驻服务主入口
├── api_handler.py        # 新增：API 请求处理器
├── services/             # 服务层（保持不变，但内部实现需调整）
│   ├── device_service.py # 示例：改造为可管理状态
│   └── ...
├── commands/             # 命令行工具封装（保持不变）
└── common/               # 公共模块（保持不变）
```

`backend/main.py` 文件可以被废弃或保留作为备用的命令行工具入口。

## 6. 风险与应对

- **Python 环境问题:** 用户的 Python 环境可能不一致。
  - **应对:** 在打包时，考虑使用 `PyInstaller` 将 Python 后端及其依赖打包成一个独立的可执行文件，由 Electron 主进程直接调用这个可执行文件，从而消除对用户本地 Python 环境的依赖。
- **进程管理复杂性:** 需要处理 Python 进程异常退出、重启等情况。
  - **应对:** 在 `pythonService.js` 中实现一个简单的重试机制。当检测到 `close` 事件时，可以等待几秒后尝试重启服务。
- **重构工作量:** 对现有代码的改动较大。
  - **应对:** 可以分阶段进行。
    1.  **阶段一 (兼容模式):** 先实现常驻服务和 `server.py`，但 `api_handler.py` 内部仍然通过调用 `main.py` 的方式执行命令。这能快速解决通信问题。
    2.  **阶段二 (完全重构):** 逐步将 `main.py` 中的逻辑迁移到各个 `services` 中，实现完全的状态化管理。

## 7. 总结

通过将 Python 后端从“一次性脚本”重构为“常驻服务”，并采用 Stdio 进行高效的进程间通信，我们可以从根本上解决当前架构存在的性能、稳定性和功能限制问题。这一改变将为应用的未来发展奠定坚实的基础，使得添加更复杂、更可靠的功能（如实时同步、远程管理等）成为可能。