# Project Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete JS→TS migration, backend modularization, frontend component restructuring, communication layer unification, and full test coverage.

**Architecture:** 3-phase team execution — Phase 1 (Protocol Architect) defines shared protocol types; Phase 2 (Backend + Frontend Engineers) run in parallel after protocol lock; Phase 3 (Test Engineer) adds comprehensive coverage after code freeze. All agents use sonnet model.

**Tech Stack:** Electron + Vue 3 + Pinia + TypeScript (frontend), Python 3.12 (backend), vitest + Playwright (testing)

**Spec:** `docs/superpowers/specs/2026-05-27-project-refactoring-design.md`

---

## File Structure Map

### Phase 1 — Protocol
| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/shared/ipc/protocol.ts` | Generic request/response types, method-to-type mapping |
| Modify | `src/shared/ipc/channels.ts` | Direction-annotated typed channels |
| Modify | `src/shared/ipc/electronApi.ts` | Type-safe API interface with method result inference |
| Create | `backend/app/protocol.py` | Python dataclass models matching TS protocol types |

### Phase 2 — Backend
| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/common/base_executor.py` | Split into template method + timeout policy |
| Create | `backend/app/common/executor.py` | ProcessExecutor — subprocess lifecycle |
| Modify | `backend/app/tools/tool_manager.py` | ToolRegistry with lazy loading + DI |
| Modify | `backend/app/tools/base_tool.py` | Updated tool base with new executor interface |
| Modify | `backend/app/api_handler.py` | Error middleware + protocol adaptation |
| Create | `backend/app/common/exceptions.py` | Typed business exceptions |
| Modify | `backend/app/handlers/aab_handler.py` | Cleanup + protocol compliance |
| Modify | `backend/app/handlers/apk_handler.py` | Cleanup + protocol compliance |
| Modify | `backend/app/handlers/install_handler.py` | Cleanup + protocol compliance |
| Modify | `backend/app/handlers/app_handler.py` | Cleanup + protocol compliance |
| Modify | `backend/app/handlers/adb_handler.py` | Cleanup + protocol compliance |
| Modify | `backend/app/handlers/tool_handler.py` | Cleanup + protocol compliance |
| Modify | `backend/app/handlers/cache_handler.py` | Cleanup + protocol compliance |
| Modify | `backend/app/handlers/plugin_handler.py` | Cleanup + protocol compliance |
| Modify | `backend/main.py` | Health check + reconnection + graceful shutdown |
| Modify | `backend/app/utils/env.py` | Already modified, review consistency |

### Phase 2 — Frontend
| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/renderer/components/device/DeviceList.vue` | Device list with selection |
| Create | `src/renderer/components/device/DeviceDetail.vue` | Single device detail view |
| Create | `src/renderer/components/device/DeviceActionBar.vue` | Action buttons for selected device |
| Modify | `src/renderer/components/DeviceManager.vue` | Orchestrator using sub-components |
| Modify | `src/renderer/components/DeviceActions.vue` | Adapt to split |
| Create | `src/renderer/components/settings/GeneralSettings.vue` | General app preferences |
| Create | `src/renderer/components/settings/PathSettings.vue` | Path configuration |
| Create | `src/renderer/components/settings/AdvancedSettings.vue` | Advanced/tools config |
| Modify | `src/renderer/views/SettingsPage.vue` | Tab container using sub-components |
| Create | `src/renderer/components/package/PackageInfo.vue` | Package metadata display |
| Modify | `src/renderer/components/package/SignatureEditModal.vue` | Already modified, review |
| Modify | `src/renderer/views/PackagePage.vue` | Orchestrator with sub-components |
| Create | `src/renderer/assets/variables.css` | CSS token definitions |
| Modify | `src/renderer/components/common/Notification.vue` | Style alignment |
| Modify | `src/renderer/components/common/Header.vue` | Style alignment |
| Modify | `src/renderer/components/common/StatusBar.vue` | Style alignment |
| Modify | `src/renderer/views/DevicePage.vue` | Remove inline styles |
| Modify | `src/renderer/App.vue` | Import variables.css |
| Create | `src/renderer/services/ConfigService.ts` | Merge StoreService + SettingsService |
| Modify | `src/renderer/services/ServiceManager.ts` | Register ConfigService, remove PluginService |
| Delete | `src/renderer/services/StoreService.ts` | Migrated to ConfigService |
| Delete | `src/renderer/services/SettingsService.ts` | Migrated to ConfigService |
| Delete | `src/renderer/services/PluginService.ts` | No active consumers |
| Modify | `src/renderer/api/unifiedApi.ts` | Typed API with method inference |
| Modify | `src/preload/index.ts` | Protocol type alignment |
| Modify | `src/main/ipc/commandHandlers.ts` | Protocol type alignment |
| Modify | `src/main/main.ts` | Protocol type alignment |

### Phase 3 — Testing
| Action | File | Responsibility |
|--------|------|----------------|
| Create | `vitest.config.ts` | Vitest configuration |
| Create | `tests/contracts/test_adb_handler.py` | ADB handler contract tests |
| Create | `tests/contracts/test_apk_handler.py` | APK handler contract tests |
| Create | `tests/contracts/test_aab_handler.py` | AAB handler contract tests |
| Create | `tests/contracts/test_install_handler.py` | Install handler contract tests |
| Create | `tests/contracts/test_tool_handler.py` | Tool handler contract tests |
| Create | `tests/contracts/test_cache_handler.py` | Cache handler contract tests |
| Create | `tests/unit/services/ApkService.test.ts` | ApkService unit tests |
| Create | `tests/unit/services/DeviceService.test.ts` | DeviceService unit tests |
| Create | `tests/unit/services/ConfigService.test.ts` | ConfigService unit tests |
| Create | `tests/unit/services/ServiceManager.test.ts` | ServiceManager unit tests |
| Create | `tests/unit/stores/deviceStore.test.ts` | deviceStore unit tests |
| Create | `tests/unit/stores/packageStore.test.ts` | packageStore unit tests |
| Create | `tests/unit/stores/systemStore.test.ts` | systemStore unit tests |
| Create | `tests/unit/components/DeviceList.test.ts` | DeviceList mount tests |
| Create | `tests/unit/components/SettingsPage.test.ts` | SettingsPage mount tests |
| Create | `tests/unit/components/Notification.test.ts` | Notification mount tests |
| Create | `tests/integration/ipc-channels.test.ts` | IPC channel name verification |
| Create | `tests/integration/config-handlers.test.ts` | Config handler round-trip |
| Create | `tests/e2e/critical-flows.spec.ts` | Playwright E2E smoke tests |
| Modify | `package.json` | Add test scripts + vitest deps |
| Modify | `tsconfig.json` | Add test includes |

---

## Phase 1: Protocol Architect

### Task 1.1: Audit current protocol

**Files:**
- Review: `src/shared/ipc/protocol.ts`
- Review: `backend/app/api_handler.py`
- Review: `backend/main.py`

- [ ] **Step 1: Read all protocol-related files to identify mismatches**

Read `src/shared/ipc/protocol.ts`, `backend/app/api_handler.py:25-62`, and `backend/main.py:19-23`. Document differences:

| Aspect | TypeScript (`protocol.ts`) | Python (`api_handler.py`) |
|--------|---------------------------|---------------------------|
| Request format | `{ id, method, params }` | `{ id, method, params }` — aligned |
| Success response | `{ id, result: { type, payload }, finished }` | `{ id, result: { type: 'success', payload }, finished }` — aligned |
| Error response | `{ id, error: { code, message } }` | Exception caught → `{ id, result: { type: 'error', payload: { message } } }` — **MISMATCH**: Python wraps errors in `result` instead of top-level `error` |
| Streaming | `{ id, result, stream_id, finished: false }` | Same — aligned |
| Event message | `{ type: 'event', event, data }` | Python `send_json` doesn't emit events — **GAP**: TS expects events but Python doesn't use this type |

Key findings:
1. Python puts errors in `result.error` while TS expects top-level `error` field
2. `BackendEventMessage` type is unused — Python never sends `type: 'event'`
3. `BackendStdioMessage` union is used but no discriminator for event vs response

### Task 1.2: Define generic protocol types

**Files:**
- Modify: `src/shared/ipc/protocol.ts`

- [ ] **Step 1: Rewrite protocol.ts with proper generics and method map**

```typescript
// ---- Request ----
export type JsonObject = Record<string, unknown>

export interface BackendApiRequest<M extends string = string, P extends JsonObject = JsonObject> {
  id: string | number
  method: M
  params: P
}

// ---- Response ----
export type BackendResultType = 'success' | 'error'

export interface BackendSuccessPayload<T = unknown> {
  type: 'success'
  payload: T
}

export interface BackendErrorPayload {
  type: 'error'
  payload: {
    code?: number
    message: string
  }
}

export type BackendResult<T = unknown> = BackendSuccessPayload<T> | BackendErrorPayload

export interface BackendResponse<T = unknown> {
  id: string | number
  result: BackendResult<T>
  finished: boolean
  stream_id?: string
}

// ---- Streaming ----
export interface BackendStreamEvent<T = unknown> {
  id: string | number
  result: BackendResult<T>
  stream_id: string
  finished: false
}

// ---- Method-to-Type Map ----
export interface ApiMethodMap {
  'adb.devices': { params: Record<string, never>; result: AdbDevice[] }
  'adb.shell': { params: { command: string; serial?: string }; result: string }
  'adb.install': { params: { apkPath: string; serial?: string }; result: InstallResult }
  'adb.uninstall': { params: { packageName: string; serial?: string }; result: void }
  'apk.parse': { params: { apkPath: string }; result: ApkInfo }
  'apk.extract': { params: { apkPath: string; outputDir: string }; result: void }
  'aab.install': { params: { aabPath: string; serial?: string }; result: InstallResult }
  'tool.list': { params: Record<string, never>; result: ToolInfo[] }
  'cache.clear': { params: { target?: string }; result: CacheClearResult }
  'app.info': { params: { packageName: string; serial?: string }; result: AppInfo }
}

// ---- Placeholder types (replace with actual domain types) ----
export interface AdbDevice { serial: string; state: string; model: string; product: string }
export interface InstallResult { success: boolean; message: string }
export interface ApkInfo { packageName: string; versionName: string; versionCode: number; label: string }
export interface ToolInfo { name: string; version: string; path: string; available: boolean }
export interface CacheClearResult { cleared: string[]; freedBytes: number }
export interface AppInfo { packageName: string; versionName: string; installTime: string }
```

- [ ] **Step 2: Verify type consistency**

Run: `npx vue-tsc --noEmit --pretty false`
Expected: No new errors from protocol.ts changes.

### Task 1.3: Typed channels

**Files:**
- Modify: `src/shared/ipc/channels.ts`

- [ ] **Step 1: Add direction and payload type annotations**

```typescript
export interface IpcChannelDefinition {
  name: string
  direction: 'renderer-to-main' | 'main-to-renderer'
  payload?: string // TypeScript type name as string for documentation
}

export const IPC_CHANNELS = {
  // Renderer → Main (invoke)
  callBackendApi: { name: 'call-backend-api', direction: 'renderer-to-main', payload: 'BackendApiRequest' },
  getAppConfig: { name: 'get-app-config', direction: 'renderer-to-main', payload: 'string | undefined' },
  getAllAppConfig: { name: 'app-config-getAll', direction: 'renderer-to-main' },
  setAppConfig: { name: 'set-app-config', direction: 'renderer-to-main', payload: '{ key: string, value: unknown }' },
  setManyAppConfig: { name: 'set-app-config-batch', direction: 'renderer-to-main', payload: 'Record<string, unknown>' },
  resetAppConfig: { name: 'reset-app-config', direction: 'renderer-to-main' },
  getUserConfig: { name: 'get-user-config', direction: 'renderer-to-main', payload: 'string | undefined' },
  setUserConfig: { name: 'set-user-config', direction: 'renderer-to-main', payload: '{ key: string, value: unknown }' },
  getAllUserConfig: { name: 'user-config-getAll', direction: 'renderer-to-main' },
  resetUserConfig: { name: 'reset-user-config', direction: 'renderer-to-main' },
  getSettingsViewModel: { name: 'get-settings-view-model', direction: 'renderer-to-main' },
  resolveSettingsPaths: { name: 'resolve-settings-paths', direction: 'renderer-to-main', payload: '{ runtime?, server? }' },

  // Main → Renderer (send/on)
  appConfigChanged: { name: 'app-config-changed', direction: 'main-to-renderer', payload: '{ key: string, value: unknown }' },
  userConfigChanged: { name: 'user-config-changed', direction: 'main-to-renderer', payload: '{ key: string, value: unknown }' },
  deviceChange: { name: 'device-change', direction: 'main-to-renderer', payload: 'AdbDevice[]' },
  logUpdate: { name: 'log-update', direction: 'main-to-renderer', payload: 'string' },
  logcatOutput: { name: 'logcat-output', direction: 'main-to-renderer', payload: 'string' },
  logcatStarted: { name: 'logcat-started', direction: 'main-to-renderer' },
  logcatFinished: { name: 'logcat-finished', direction: 'main-to-renderer' },
  logcatError: { name: 'logcat-error', direction: 'main-to-renderer', payload: 'string' },
  streamEvent: { name: 'stream-event', direction: 'main-to-renderer', payload: 'BackendStreamEvent' },
} as const satisfies Record<string, IpcChannelDefinition>

// Legacy flat accessor for backward compat during migration
export const IPC_CHANNEL_NAMES = Object.fromEntries(
  Object.entries(IPC_CHANNELS).map(([key, def]) => [key, def.name])
) as Record<keyof typeof IPC_CHANNELS, string>
```

- [ ] **Step 2: Update consumers to use new channel structure**

Run: `npx vue-tsc --noEmit --pretty false`
Check for any code referencing `IPC_CHANNELS.xxx` as a string — these need `IPC_CHANNELS.xxx.name` or use `IPC_CHANNEL_NAMES.xxx`.

### Task 1.4: Type-safe ElectronAPI

**Files:**
- Modify: `src/shared/ipc/electronApi.ts`

- [ ] **Step 1: Add typed callBackendAPI with method inference**

```typescript
import type { ApiMethodMap, BackendApiRequest, JsonObject } from './protocol'

type MethodParams<M extends keyof ApiMethodMap> = ApiMethodMap[M]['params']
type MethodResult<M extends keyof ApiMethodMap> = ApiMethodMap[M]['result']

export interface TypedCallBackendAPI {
  <M extends keyof ApiMethodMap>(method: M, params: MethodParams<M>): Promise<MethodResult<M>>
  <M extends string>(method: M, params?: JsonObject): Promise<unknown>
}

export interface AppConfigApi {
  get: (key?: string) => Promise<unknown>
  set: (key: string, value: unknown) => Promise<unknown>
  setMany: (updates: Record<string, unknown>) => Promise<unknown>
  getAll: () => Promise<Record<string, unknown>>
  reset: () => Promise<unknown>
}

export interface UserConfigApi {
  get: (key?: string) => Promise<unknown>
  set: (key: string, value: unknown) => Promise<unknown>
  getAll: () => Promise<Record<string, unknown>>
  reset: () => Promise<unknown>
}

export interface SettingsViewModel {
  settings: Record<string, unknown>
  displayPaths: { runtime: string; server: string }
}

export interface SettingsApi {
  getViewModel: () => Promise<SettingsViewModel>
  resolvePaths: (paths: { runtime?: unknown; server?: unknown }) => Promise<{ runtime: string; server: string }>
}

export interface ElectronApi {
  callBackendAPI: TypedCallBackendAPI
  callBackendByRequest: (request: BackendApiRequest) => Promise<unknown>
  appConfig: AppConfigApi
  userConfig: UserConfigApi
  settings: SettingsApi
  onDeviceChange: (callback: (devices: unknown[]) => void) => () => void
  onLogUpdate: (callback: (message: string) => void) => () => void
  onLogcatOutput: (callback: (output: string) => void) => () => void
  onLogcatStarted: (callback: () => void) => () => void
  onLogcatFinished: (callback: () => void) => () => void
  onLogcatError: (callback: (error: string) => void) => () => void
  removeLogcatListener: () => void
}

declare global {
  interface Window {
    electronAPI: ElectronApi
  }
}
```

- [ ] **Step 2: Verify type compilation**

Run: `npx vue-tsc --noEmit --pretty false`
Expected: No errors.

### Task 1.5: Python protocol model

**Files:**
- Create: `backend/app/protocol.py`

- [ ] **Step 1: Write Python protocol models**

```python
from dataclasses import dataclass, field, asdict
from typing import Any, Generic, TypeVar, Optional, Union
import json

T = TypeVar('T')

@dataclass
class BackendSuccessPayload:
    type: str = 'success'
    payload: Any = None

    def to_dict(self) -> dict:
        return {'type': self.type, 'payload': self.payload}

@dataclass
class BackendErrorPayload:
    message: str
    code: Optional[int] = None

    def to_dict(self) -> dict:
        result: dict = {'type': 'error', 'payload': {'message': self.message}}
        if self.code is not None:
            result['payload']['code'] = self.code
        return result

@dataclass
class BackendResponse:
    id: Any
    result: Union[BackendSuccessPayload, BackendErrorPayload, dict]
    finished: bool = True
    stream_id: Optional[str] = None

    def to_json(self) -> str:
        data = {
            'id': self.id,
            'result': self.result.to_dict() if isinstance(self.result, (BackendSuccessPayload, BackendErrorPayload)) else self.result,
            'finished': self.finished,
        }
        if self.stream_id:
            data['stream_id'] = self.stream_id
        return json.dumps(data)

@dataclass
class BackendStreamEvent:
    id: Any
    result: Union[BackendSuccessPayload, BackendErrorPayload, dict]
    stream_id: str

    def to_json(self) -> str:
        return json.dumps({
            'id': self.id,
            'result': self.result.to_dict() if isinstance(self.result, (BackendSuccessPayload, BackendErrorPayload)) else self.result,
            'stream_id': self.stream_id,
            'finished': False,
        })

@dataclass
class BackendApiRequest:
    id: Any
    method: str
    params: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict) -> 'BackendApiRequest':
        return cls(
            id=data.get('id'),
            method=data.get('method', ''),
            params=data.get('params', {})
        )

# Standard JSON-RPC error codes
class ErrorCode:
    PARSE_ERROR = -32700
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    TIMEOUT = -32000
    TOOL_ERROR = -32001
```

### Task 1.6: Commit Phase 1

- [ ] **Step 1: Commit all Phase 1 files**

```bash
git add src/shared/ipc/protocol.ts src/shared/ipc/channels.ts src/shared/ipc/electronApi.ts backend/app/protocol.py
git commit -m "feat: unified communication protocol with end-to-end type safety"
```

---

## Phase 2a: Backend Engineer

### Task 2a.1: Split base_executor.py

**Files:**
- Modify: `backend/app/common/base_executor.py`
- Create: `backend/app/common/executor.py`
- Create: `backend/app/common/exceptions.py`

- [ ] **Step 1: Create exceptions module**

`backend/app/common/exceptions.py`:
```python
class ToolException(Exception):
    """Base exception for tool execution errors."""
    def __init__(self, message: str, code: int = -32001):
        super().__init__(message)
        self.code = code
        self.message = message

class TimeoutException(ToolException):
    """Raised when tool execution exceeds the timeout."""
    def __init__(self, message: str = "Tool execution timed out"):
        super().__init__(message, code=-32000)

class ToolNotFoundError(ToolException):
    """Raised when a requested tool is not found."""
    def __init__(self, tool_name: str):
        super().__init__(f"Tool not found: {tool_name}", code=-32002)
```

- [ ] **Step 2: Create executor.py with ProcessExecutor**

`backend/app/common/executor.py`:
```python
import subprocess
import threading
from typing import Optional, Callable
from app.common.exceptions import TimeoutException

class ProcessExecutor:
    """Manages subprocess lifecycle: spawn, monitor, kill."""

    def __init__(self, timeout: int = 600):
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None

    def run(self, cmd: list[str], cwd: Optional[str] = None,
            env: Optional[dict] = None, on_output: Optional[Callable[[str], None]] = None) -> tuple[int, str, str]:
        """Execute command and return (returncode, stdout, stderr)."""
        self.process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        try:
            stdout, stderr = self.process.communicate(timeout=self.timeout)
            return self.process.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            self._kill()
            raise TimeoutException(f"Command timed out after {self.timeout}s: {' '.join(cmd)}")

    def _kill(self):
        """Graceful shutdown: SIGTERM → 5s wait → SIGKILL."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None
```

- [ ] **Step 3: Trim base_executor.py to template method**

Remove subprocess management details from `base_executor.py`, keeping only the template method pattern (`prepare → execute → cleanup`). The `execute` step delegates to `ProcessExecutor`.

### Task 2a.2: Refactor tool_manager.py

**Files:**
- Modify: `backend/app/tools/tool_manager.py`

- [ ] **Step 1: Implement ToolRegistry**

```python
class ToolRegistry:
    """Lazy-loading tool registry with dependency injection."""

    def __init__(self, runtime_dir: str, executor_factory=None):
        self._runtime_dir = runtime_dir
        self._tools: dict[str, 'BaseTool'] = {}
        self._discovered: dict[str, type] = {}
        self._executor_factory = executor_factory or ProcessExecutor

    def discover(self, tool_package: str = 'app.tools'):
        """Auto-discover BaseTool subclasses in package."""
        import importlib, pkgutil
        package = importlib.import_module(tool_package)
        for _, name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
            module = importlib.import_module(name)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseTool) and attr is not BaseTool:
                    self._discovered[attr.name] = attr

    def get(self, name: str) -> 'BaseTool':
        """Lazy-instantiate and return tool by name."""
        if name not in self._tools:
            tool_cls = self._discovered.get(name)
            if not tool_cls:
                raise ToolNotFoundError(name)
            executor = self._executor_factory()
            self._tools[name] = tool_cls(self._runtime_dir, executor)
        return self._tools[name]

    def list_all(self) -> list[str]:
        """Return names of all discovered tools."""
        return list(self._discovered.keys())
```

### Task 2a.3: Add error middleware to api_handler.py

**Files:**
- Modify: `backend/app/api_handler.py`

- [ ] **Step 1: Wrap handler execution in middleware**

Replace the try/except in `handle_request()` with:

```python
from app.protocol import BackendResponse, BackendSuccessPayload, BackendErrorPayload, ErrorCode

def handle_request(self, request_data):
    req_id = request_data.get("id")
    method = request_data.get("method")
    params = request_data.get("params", {})

    handler = self.api_map.get(method)
    if not handler:
        return BackendResponse(
            id=req_id,
            result=BackendErrorPayload(message=f"Method '{method}' not found", code=ErrorCode.METHOD_NOT_FOUND),
        ).to_json()

    try:
        raw_result = handler(params, None)
        if isinstance(raw_result, dict):
            result = raw_result
        else:
            result = BackendSuccessPayload(payload=raw_result).to_dict()
        return BackendResponse(id=req_id, result=result).to_json()
    except Exception as e:
        self.logger.error(f"Handler error (method={method}): {e}")
        return BackendResponse(
            id=req_id,
            result=BackendErrorPayload(message=str(e), code=ErrorCode.INTERNAL_ERROR),
        ).to_json()
```

### Task 2a.4: Add health check and reconnection to main.py

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add heartbeat handler**

Add to the API_MAP in a handler or directly in main.py:

```python
# In main.py bootstrap, register a health check
def handle_health(params, context):
    return {"status": "ok", "uptime": time.time() - start_time}
```

- [ ] **Step 2: Add stdin EOF reconnection logic**

```python
# In main(), after the for line in sys.stdin loop:
for line in sys.stdin:
    executor.submit(process_request, line)

# After loop exits (EOF), attempt reconnect:
self.logger.warning("stdin closed, attempting reconnect...")
time.sleep(1)
# Re-enter loop — new stdin pipe will be connected by main process
```

### Task 2a.5: Commit Phase 2a

```bash
git add backend/
git commit -m "refactor(backend): modularize executor, tool registry, error handling"
```

---

## Phase 2b: Frontend Engineer

### Task 2b.1: Complete TS migration

**Files:**
- Modify: Various `.ts` files

- [ ] **Step 1: Remove remaining references to deleted JS files**

Run: `git status --porcelain | grep "^D" | grep "\.js$"` to list deleted JS files.
For each, check no TS file still imports it.

- [ ] **Step 2: Run type check and fix errors**

```bash
npx vue-tsc --noEmit --pretty false 2>&1 | head -50
```

Fix each error. Main expected issues:
- Missing import paths after JS→TS rename
- `require()` calls that should be `import`
- Unresolved `@/` path aliases

### Task 2b.2: Create CSS variables

**Files:**
- Create: `src/renderer/assets/variables.css`
- Modify: `src/renderer/App.vue`

- [ ] **Step 1: Define token file**

`src/renderer/assets/variables.css`:
```css
:root {
  /* Spacing */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;

  /* Colors */
  --color-bg: #f5f5f5;
  --color-bg-card: #ffffff;
  --color-bg-sidebar: #1e1e2e;
  --color-text: #1a1a2e;
  --color-text-secondary: #6c6c80;
  --color-text-sidebar: #cdd6f4;
  --color-primary: #3b82f6;
  --color-primary-hover: #2563eb;
  --color-success: #22c55e;
  --color-warning: #f59e0b;
  --color-error: #ef4444;
  --color-border: #e2e2e8;

  /* Radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;

  /* Shadow */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.07);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);

  /* Font */
  --font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-size-sm: 12px;
  --font-size-base: 14px;
  --font-size-lg: 16px;
  --font-size-xl: 20px;
}
```

- [ ] **Step 2: Import in App.vue**

Add to `<style>` block or `<script setup>`:
```typescript
import './assets/variables.css'
```

### Task 2b.3: Split DeviceManager.vue

**Files:**
- Create: `src/renderer/components/device/DeviceList.vue`
- Create: `src/renderer/components/device/DeviceDetail.vue`
- Create: `src/renderer/components/device/DeviceActionBar.vue`
- Modify: `src/renderer/components/DeviceManager.vue`

- [ ] **Step 1: Create DeviceList.vue**

```vue
<script setup lang="ts">
import type { AdbDevice } from '@/shared/ipc/protocol'

defineProps<{
  devices: AdbDevice[]
  selectedSerial: string | null
}>()

const emit = defineEmits<{
  select: [serial: string]
}>()
</script>

<template>
  <div class="device-list">
    <div
      v-for="device in devices"
      :key="device.serial"
      class="device-item"
      :class="{ active: device.serial === selectedSerial }"
      @click="emit('select', device.serial)"
    >
      <span class="device-model">{{ device.model }}</span>
      <span class="device-serial">{{ device.serial }}</span>
      <span class="device-state" :class="device.state">{{ device.state }}</span>
    </div>
    <div v-if="devices.length === 0" class="empty-state">
      No devices connected
    </div>
  </div>
</template>

<style scoped>
.device-list { display: flex; flex-direction: column; gap: var(--space-xs); }
.device-item { padding: var(--space-sm) var(--space-md); cursor: pointer; border-radius: var(--radius-sm); }
.device-item.active { background: var(--color-primary); color: white; }
.device-model { font-weight: 600; }
.device-serial { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-left: var(--space-sm); }
.device-state.device { color: var(--color-success); }
.device-state.offline { color: var(--color-error); }
.empty-state { padding: var(--space-lg); text-align: center; color: var(--color-text-secondary); }
</style>
```

- [ ] **Step 2: Create DeviceDetail.vue**

```vue
<script setup lang="ts">
import type { AdbDevice } from '@/shared/ipc/protocol'

defineProps<{
  device: AdbDevice | null
}>()
</script>

<template>
  <div class="device-detail" v-if="device">
    <h3>{{ device.model }}</h3>
    <dl>
      <dt>Serial</dt><dd>{{ device.serial }}</dd>
      <dt>Status</dt><dd>{{ device.state }}</dd>
      <dt>Product</dt><dd>{{ device.product }}</dd>
    </dl>
  </div>
  <div class="device-detail empty" v-else>
    Select a device to view details
  </div>
</template>

<style scoped>
.device-detail { padding: var(--space-md); }
.device-detail.empty { color: var(--color-text-secondary); text-align: center; padding: var(--space-xl); }
dl { display: grid; grid-template-columns: 80px 1fr; gap: var(--space-xs) var(--space-md); }
dt { font-weight: 600; color: var(--color-text-secondary); }
</style>
```

- [ ] **Step 3: Create DeviceActionBar.vue**

```vue
<script setup lang="ts">
defineProps<{
  hasSelection: boolean
  selectedState: string | null
}>()

const emit = defineEmits<{
  refresh: []
  install: []
  shell: []
  reboot: []
}>()
</script>

<template>
  <div class="action-bar">
    <button @click="emit('refresh')" class="btn">Refresh</button>
    <button @click="emit('install')" class="btn" :disabled="!hasSelection">Install APK</button>
    <button @click="emit('shell')" class="btn" :disabled="!hasSelection">Shell</button>
    <button @click="emit('reboot')" class="btn" :disabled="!hasSelection">Reboot</button>
  </div>
</template>

<style scoped>
.action-bar { display: flex; gap: var(--space-sm); padding: var(--space-sm) 0; }
.btn { padding: var(--space-xs) var(--space-md); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg-card); cursor: pointer; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn:not(:disabled):hover { background: var(--color-primary); color: white; border-color: var(--color-primary); }
</style>
```

- [ ] **Step 4: Refactor DeviceManager.vue to use sub-components**

Replace existing template content with composition of the three new components, passing props and handling emitted events.

### Task 2b.4: Split SettingsPage.vue

**Files:**
- Create: `src/renderer/components/settings/GeneralSettings.vue`
- Create: `src/renderer/components/settings/PathSettings.vue`
- Create: `src/renderer/components/settings/AdvancedSettings.vue`
- Modify: `src/renderer/views/SettingsPage.vue`

- [ ] **Step 1: Extract tab content into sub-components**

Move each tab's template and logic into its own component. SettingsPage.vue becomes a tab container:

```vue
<script setup lang="ts">
import { ref } from 'vue'
import GeneralSettings from '@/renderer/components/settings/GeneralSettings.vue'
import PathSettings from '@/renderer/components/settings/PathSettings.vue'
import AdvancedSettings from '@/renderer/components/settings/AdvancedSettings.vue'

const activeTab = ref('general')
const tabs = [
  { key: 'general', label: 'General' },
  { key: 'paths', label: 'Paths' },
  { key: 'advanced', label: 'Advanced' },
]
</script>

<template>
  <div class="settings-page">
    <nav class="settings-tabs">
      <button v-for="tab in tabs" :key="tab.key"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key">{{ tab.label }}</button>
    </nav>
    <GeneralSettings v-if="activeTab === 'general'" />
    <PathSettings v-if="activeTab === 'paths'" />
    <AdvancedSettings v-if="activeTab === 'advanced'" />
  </div>
</template>
```

### Task 2b.5: Consolidate services — ConfigService

**Files:**
- Create: `src/renderer/services/ConfigService.ts`
- Modify: `src/renderer/services/ServiceManager.ts`
- Delete: `src/renderer/services/StoreService.ts`
- Delete: `src/renderer/services/SettingsService.ts`
- Delete: `src/renderer/services/PluginService.ts`

- [ ] **Step 1: Create ConfigService.ts**

```typescript
import type { AppConfigApi, UserConfigApi } from '@/shared/ipc/electronApi'

export class ConfigService {
  constructor(
    private appConfig: AppConfigApi,
    private userConfig: UserConfigApi
  ) {}

  // App config
  async getAppConfig(key?: string) { return this.appConfig.get(key) }
  async setAppConfig(key: string, value: unknown) { return this.appConfig.set(key, value) }
  async getAllAppConfig() { return this.appConfig.getAll() }
  async resetAppConfig() { return this.appConfig.reset() }

  // User config
  async getUserConfig(key?: string) { return this.userConfig.get(key) }
  async setUserConfig(key: string, value: unknown) { return this.userConfig.set(key, value) }
  async getAllUserConfig() { return this.userConfig.getAll() }
  async resetUserConfig() { return this.userConfig.reset() }
}
```

- [ ] **Step 2: Update ServiceManager registrations**

In `ServiceManager.ts`:
- Replace `StoreService` and `SettingsService` registrations with `ConfigService`
- Remove `PluginService` registration
- `ConfigService` depends on `AppConfigApi` and `UserConfigApi` from `window.electronAPI`

### Task 2b.6: Adapt unifiedApi.ts to typed protocol

**Files:**
- Modify: `src/renderer/api/unifiedApi.ts`

- [ ] **Step 1: Refactor to use typed callBackendAPI**

```typescript
import type { ApiMethodMap } from '@/shared/ipc/protocol'

type MethodParams<M extends keyof ApiMethodMap> = ApiMethodMap[M]['params']
type MethodResult<M extends keyof ApiMethodMap> = ApiMethodMap[M]['result']

export async function callApi<M extends keyof ApiMethodMap>(
  method: M,
  params: MethodParams<M>
): Promise<MethodResult<M>> {
  return window.electronAPI.callBackendAPI(method, params)
}
```

- [ ] **Step 2: Update all callers**

Search for `callBackendAPI(` calls across the renderer and replace with `callApi(` where appropriate.

### Task 2b.7: Align preload and main with protocol

**Files:**
- Modify: `src/preload/index.ts`
- Modify: `src/main/ipc/commandHandlers.ts`
- Modify: `src/main/main.ts`

- [ ] **Step 1: Update preload contextBridge**

Ensure `callBackendAPI` in `contextBridge.exposeInMainWorld` matches the `TypedCallBackendAPI` signature.

- [ ] **Step 2: Update main process command handlers**

Ensure Python process request/response handling uses the new protocol types for validation.

### Task 2b.8: Remove inline styles from DevicePage and PackagePage

**Files:**
- Modify: `src/renderer/views/DevicePage.vue`
- Modify: `src/renderer/views/PackagePage.vue`

- [ ] **Step 1: Replace inline styles with scoped CSS**

Remove `style="..."` attributes from template elements. Add corresponding rules to `<style scoped>` blocks using CSS variables.

### Task 2b.9: Commit Phase 2b

```bash
git add src/renderer/ src/preload/ src/main/ipc/ src/main/main.ts
git commit -m "refactor(frontend): component splitting, TS migration complete, typed API, ConfigService"
```

---

## Phase 3: Test Engineer

### Task 3.1: Setup vitest

**Files:**
- Create: `vitest.config.ts`
- Modify: `package.json`

- [ ] **Step 1: Install dependencies**

```bash
npm install -D vitest @vue/test-utils jsdom @vitest/coverage-v8 vitest-html-reporter happy-dom
```

- [ ] **Step 2: Create vitest.config.ts**

```typescript
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      reportsDirectory: 'tests/reports/coverage',
    },
    reporters: ['default', 'html'],
    outputFile: 'tests/reports/index.html',
  },
})
```

- [ ] **Step 3: Update package.json scripts**

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "test:report": "vitest run --reporter=html --outputFile=tests/reports/index.html"
  }
}
```

### Task 3.2: Backend contract tests

**Files:**
- Create: `tests/contracts/test_adb_handler.py`
- Create: `tests/contracts/test_apk_handler.py`
- Create: `tests/contracts/test_aab_handler.py`
- Create: `tests/contracts/test_install_handler.py`
- Create: `tests/contracts/test_tool_handler.py`
- Create: `tests/contracts/test_cache_handler.py`
- Create: `tests/contracts/conftest.py`

- [ ] **Step 1: Create conftest.py with mock fixtures**

```python
import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend')))

from app.api_handler import ApiHandler

@pytest.fixture
def api_handler():
    responses = []
    def capture_response(data):
        responses.append(data)
    handler = ApiHandler(send_response=capture_response)
    handler._responses = responses
    return handler
```

- [ ] **Step 2: Write contract test for adb.devices**

```python
import json
from app.protocol import BackendResponse, BackendSuccessPayload, BackendErrorPayload

def test_adb_devices_contract(api_handler):
    request = {"id": 1, "method": "adb.devices", "params": {}}
    response = api_handler.handle_request(request)

    assert response is not None
    data = json.loads(response) if isinstance(response, str) else response
    assert data["id"] == 1
    assert "result" in data
    assert data["finished"] == True
```

- [ ] **Step 3: Verify all contract tests run**

```bash
pytest tests/contracts/ -v
```
Expected: All pass.

### Task 3.3: Service unit tests

**Files:**
- Create: `tests/unit/services/ApkService.test.ts`
- Create: `tests/unit/services/DeviceService.test.ts`
- Create: `tests/unit/services/ConfigService.test.ts`
- Create: `tests/unit/services/ServiceManager.test.ts`

- [ ] **Step 1: Write ConfigService.test.ts**

```typescript
import { describe, it, expect, vi } from 'vitest'
import { ConfigService } from '@/renderer/services/ConfigService'

describe('ConfigService', () => {
  const mockAppConfig = {
    get: vi.fn().mockResolvedValue('value'),
    set: vi.fn().mockResolvedValue(undefined),
    getAll: vi.fn().mockResolvedValue({ key: 'value' }),
    reset: vi.fn().mockResolvedValue(undefined),
  }
  const mockUserConfig = {
    get: vi.fn().mockResolvedValue('user-value'),
    set: vi.fn().mockResolvedValue(undefined),
    getAll: vi.fn().mockResolvedValue({}),
    reset: vi.fn().mockResolvedValue(undefined),
  }

  const service = new ConfigService(mockAppConfig, mockUserConfig)

  it('getAppConfig delegates to appConfig.get', async () => {
    const result = await service.getAppConfig('theme')
    expect(mockAppConfig.get).toHaveBeenCalledWith('theme')
    expect(result).toBe('value')
  })

  it('setAppConfig delegates to appConfig.set', async () => {
    await service.setAppConfig('theme', 'dark')
    expect(mockAppConfig.set).toHaveBeenCalledWith('theme', 'dark')
  })

  it('getAllAppConfig delegates to appConfig.getAll', async () => {
    const result = await service.getAllAppConfig()
    expect(result).toEqual({ key: 'value' })
  })
})
```

- [ ] **Step 2: Verify tests pass**

```bash
npx vitest run tests/unit/services/
```

### Task 3.4: Store unit tests

**Files:**
- Create: `tests/unit/stores/deviceStore.test.ts`
- Create: `tests/unit/stores/packageStore.test.ts`
- Create: `tests/unit/stores/systemStore.test.ts`

- [ ] **Step 1: Write deviceStore.test.ts**

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDeviceStore } from '@/renderer/stores/deviceStore'

describe('deviceStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('initial state has empty devices array', () => {
    const store = useDeviceStore()
    expect(store.devices).toEqual([])
  })

  it('setDevices updates devices', () => {
    const store = useDeviceStore()
    const devices = [{ serial: 'abc', state: 'device', model: 'Pixel', product: 'sargo' }]
    store.setDevices(devices)
    expect(store.devices).toEqual(devices)
  })
})
```

### Task 3.5: Vue component tests

**Files:**
- Create: `tests/unit/components/DeviceList.test.ts`
- Create: `tests/unit/components/SettingsPage.test.ts`
- Create: `tests/unit/components/Notification.test.ts`

- [ ] **Step 1: Write DeviceList.test.ts**

```typescript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DeviceList from '@/renderer/components/device/DeviceList.vue'

describe('DeviceList', () => {
  it('renders device items', () => {
    const devices = [
      { serial: 'abc', state: 'device', model: 'Pixel 6', product: 'oriole' },
      { serial: 'def', state: 'offline', model: 'Nexus 5', product: 'hammerhead' },
    ]
    const wrapper = mount(DeviceList, { props: { devices, selectedSerial: null } })
    const items = wrapper.findAll('.device-item')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('Pixel 6')
  })

  it('emits select on click', async () => {
    const devices = [{ serial: 'abc', state: 'device', model: 'Pixel', product: 'sargo' }]
    const wrapper = mount(DeviceList, { props: { devices, selectedSerial: null } })
    await wrapper.find('.device-item').trigger('click')
    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')![0]).toEqual(['abc'])
  })

  it('shows empty state when no devices', () => {
    const wrapper = mount(DeviceList, { props: { devices: [], selectedSerial: null } })
    expect(wrapper.find('.empty-state').text()).toBe('No devices connected')
  })

  it('applies active class to selected device', () => {
    const devices = [{ serial: 'abc', state: 'device', model: 'Pixel', product: 'sargo' }]
    const wrapper = mount(DeviceList, { props: { devices, selectedSerial: 'abc' } })
    expect(wrapper.find('.device-item.active').exists()).toBe(true)
  })
})
```

### Task 3.6: IPC integration tests

**Files:**
- Create: `tests/integration/ipc-channels.test.ts`
- Create: `tests/integration/config-handlers.test.ts`

- [ ] **Step 1: Write channel name verification test**

```typescript
import { describe, it, expect } from 'vitest'
import { IPC_CHANNELS } from '@/shared/ipc/channels'
import { IPC_CHANNELS as MAIN_CHANNELS } from '@/main/ipc/index'

describe('IPC Channel Consistency', () => {
  it('all main process channels exist in shared channel map', () => {
    const sharedNames = Object.values(IPC_CHANNELS).map(c => c.name)
    const mainNames = Object.values(MAIN_CHANNELS)
    for (const name of mainNames) {
      expect(sharedNames).toContain(name)
    }
  })
})
```

### Task 3.7: E2E smoke tests

**Files:**
- Create: `tests/e2e/critical-flows.spec.ts`

- [ ] **Step 1: Install Playwright**

```bash
npm install -D @playwright/test
npx playwright install chromium
```

- [ ] **Step 2: Write E2E test for device flow**

```typescript
import { test, expect } from '@playwright/test'

test.describe('Critical Flows', () => {
  test('device page loads and shows empty state', async ({ page }) => {
    await page.goto('http://localhost:5173')
    // Navigate to device page
    await page.click('text=Devices')
    await expect(page.locator('.device-list')).toBeVisible()
  })

  test('settings page loads and tabs work', async ({ page }) => {
    await page.goto('http://localhost:5173')
    await page.click('text=Settings')
    await page.click('text=Paths')
    await expect(page.locator('.settings-page')).toBeVisible()
  })

  test('package page loads', async ({ page }) => {
    await page.goto('http://localhost:5173')
    await page.click('text=Package')
    await expect(page.locator('.package-page')).toBeVisible()
  })
})
```

### Task 3.8: Commit Phase 3

```bash
git add vitest.config.ts tests/ package.json
git commit -m "test: full coverage with vitest, contract tests, unit tests, E2E"
```

---

## Execution Order & Dependencies

```
Phase 1 (Protocol) ── no deps, blocks Phase 2
    │
    ├── Phase 2a (Backend) ── can start after Phase 1 commit
    │
    ├── Phase 2b (Frontend) ── can start after Phase 1 commit (parallel with 2a)
    │
    └── Phase 3 (Testing) ── starts after Phase 2a + 2b complete
```

Phase 2a and 2b have no mutual dependency — they only share the protocol contract from Phase 1.

---

## Post-Implementation Verification

- [ ] `npx vue-tsc --noEmit` passes with 0 errors
- [ ] `npm run test` passes all test suites
- [ ] `npm run test:coverage` shows ≥ 80% for services/stores
- [ ] `npm run dev` starts without errors
- [ ] Contract test report shows 100% API_MAP method coverage
