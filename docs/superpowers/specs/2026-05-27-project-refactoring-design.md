# Project Refactoring Design

**Date**: 2026-05-27
**Status**: In Progress
**Branch**: dev

## Overview

Comprehensive refactoring of the Android development tools desktop app (Electron + Vue 3 + Python). Five goals: complete JS→TS migration, backend modularization, frontend design & component restructure, communication layer type-safety unification, and full test coverage with reporting.

## Strategy

**Phase order**: Communication layer first → Backend + Frontend in parallel → Full test coverage

The communication protocol is the contract between all three processes. Locking it first prevents rework in backend and frontend phases.

---

## Team Structure (4 agents + 3 review checkpoints)

All agents use **sonnet** model.

```
Phase 1: Protocol Architect (Plan agent) ──→ shared/ipc/ types + Python adapter guide ──→ 🔍 review
Phase 2: Backend Engineer ║ Frontend Engineer (general-purpose, parallel) ──────────────→ 🔍 review
Phase 3: Test Engineer (general-purpose) ──→ framework + cases + reports ────────────────→ 🔍 review
```

Reviews are on-demand at each phase gate using `feature-dev:code-reviewer` agent.

---

## Phase 1 — Protocol Architect

**Agent**: Plan agent, model: sonnet
**Scope**: `src/shared/ipc/`

### Tasks

1. **Audit existing protocol** — Compare `protocol.ts` types against actual Python JSON-RPC message format in `backend/main.py` and `api_handler.py`. Document mismatches.
2. **Generic request/response types** — Define `BackendApiRequest<TParams>` and `BackendResponse<TResult>` generics so each API method gets its own typed params/result pair.
3. **Typed channel map** — Refactor `channels.ts` with direction annotations (main→renderer / renderer→main) and payload types per channel.
4. **Type-safe ElectronAPI** — Redesign `electronApi.ts` so `callBackendAPI('adb.devices')` auto-infers return type from a method-to-type mapping table.
5. **Python protocol model** — Create `backend/app/protocol.py` with dataclasses/Pydantic models matching TS types for request/response validation.

### Output

- Updated `src/shared/ipc/protocol.ts`
- Updated `src/shared/ipc/channels.ts`
- Updated `src/shared/ipc/electronApi.ts`
- New `backend/app/protocol.py`
- Adapter guide (inline comments in above files)

### Review Gate

Trigger `code-reviewer` on protocol files. Confirm with user before Phase 2.

---

## Phase 2 — Backend Engineer

**Agent**: general-purpose, model: sonnet
**Scope**: `backend/`

### Tasks

1. **Split `base_executor.py`** — Current 100+ line incremental changes. Extract:
   - `BaseExecutor`: template method pattern (prepare → execute → cleanup)
   - `ProcessExecutor`: subprocess lifecycle (spawn, monitor, kill)
   - `TimeoutPolicy`: configurable timeout with graceful → force kill escalation
2. **Refactor `tool_manager.py`** — Introduce `ToolRegistry` class:
   - Lazy tool instantiation
   - Dependency injection for executor/runtime paths
   - Group tools by type (binary/jar/python) for discovery
3. **Reorganize handlers** — Create `handlers/` sub-packages:
   - `handlers/base.py`: common request validation, param extraction, error formatting
   - `handlers/device.py`: ADB device commands (extract from current scattered handlers)
   - `handlers/package.py`: APK/AAB parsing and management
   - `handlers/install.py`: installation workflows
   - Eliminate cross-handler duplicated try/except and param parsing
4. **Unified error handling** — Add middleware layer in `api_handler.py`:
   - Handler functions throw typed business exceptions only
   - Middleware catches and formats into `BackendResponse` error shape
   - Standard JSON-RPC error codes (parse error, method not found, internal error)
5. **Robustness** — Add:
   - Health check: heartbeat ping from main process to Python, restart on unresponsive
   - Reconnection: detect broken stdin/stdout, attempt reconnect with backoff
   - Graceful shutdown: SIGTERM → wait 5s → SIGKILL
   - Request timeout per-method (configurable, default 10min)
6. **Protocol adaptation** — Import and use `protocol.py` models for all response formatting. Every handler response must match TS `BackendResponse<T>` shape.

---

## Phase 2 — Frontend Engineer

**Agent**: general-purpose, model: sonnet
**Scope**: `src/renderer/` `src/main/` `src/preload/`

### Tasks

1. **TS migration completion** — Verify functional parity between all new `.ts` files and deleted `.js` files. Fix all type errors (`vue-tsc --noEmit` must pass). Remove any remaining JS import references.
2. **Component splitting**:
   - `DeviceManager.vue` → `DeviceList.vue` + `DeviceDetail.vue` + `DeviceActionBar.vue`
   - `SettingsPage.vue` → `GeneralSettings.vue` + `PathSettings.vue` + `AdvancedSettings.vue` (tab-based)
   - `PackagePage.vue` → keep as orchestrator, extract `PackageInfo.vue` + `SignatureForm.vue` sub-components
3. **UI layout optimization**:
   - Define CSS variable tokens (spacing, colors, radius, shadow) in a shared `variables.css`
   - Fix alignment/consistency issues in `Notification.vue`, `StatusBar.vue`, `Header.vue`
   - Replace inline styles in `DevicePage.vue` and `PackagePage.vue` with CSS modules or scoped styles
   - Responsive minimum width enforcement, scroll behavior normalization
4. **Service layer consolidation**:
   - Merge `StoreService.ts` + `SettingsService.ts` → `ConfigService.ts` (both operate on config, different sources)
   - Remove `PluginService.ts` (only used by deleted `hello_world.py` plugin, no active consumers)
   - Result: 10 services instead of 12
5. **Protocol adaptation** — Refactor `unifiedApi.ts` to use Phase 1's typed `electronApi.ts`. All `callBackendAPI` calls get return type inference. Update `ServiceManager.ts` to inject the typed API.

### Review Gate

Trigger `code-reviewer` on backend + frontend changes. Confirm with user before Phase 3.

---

## Phase 3 — Test Engineer

**Agent**: general-purpose, model: sonnet
**Scope**: `tests/` `src/tests/` project root config

### Tasks

1. **Setup vitest** — Create `vitest.config.ts` reusing Vite aliases, add `@vue/test-utils`, `jsdom` environment, `@vitest/coverage-v8` for coverage. Wire into `npm run test` and `npm run check`.
2. **Backend contract tests** — One test per `API_MAP` method across all handlers. Each test sends a valid JSON-RPC request and asserts response structure matches `protocol.ts` types. Mock subprocess calls. Focus: request→response shape correctness, error format compliance.
3. **Service unit tests** — Cover all 10 services. Mock `window.electronAPI`. Test: correct param transformation, error propagation, edge cases (null/undefined params, empty responses, timeout).
4. **Store unit tests** — Cover all 7 Pinia stores. Test: action state transitions, getter derivations, localStorage persistence plugin behavior (save/load/clear).
5. **Vue component tests** — Mount tests for all split components. Verify: props rendering, event emission, conditional rendering (loading/empty/error states if applicable). Reuse existing `InteractionTest.vue` and `NotificationTest.vue`.
6. **IPC integration tests** — Verify main↔renderer channel names match `channels.ts` constants. Test config handlers (get/set/reset) with real `electron-store` instance. Test command handler request/response round-trip with mock Python process.
7. **E2E smoke tests** — Playwright-based, covering critical workflows: device list load → APK parsing → AAB install → signature configuration → settings save/restore.
8. **Test report generation** — Integrate `vitest-html-reporter`. Output to `tests/reports/` with: coverage %, failed test details, execution time per suite. Add `npm run test:report` script.

### Pass Criteria

- All `API_MAP` methods have contract test coverage (100%)
- Service + Store unit test coverage ≥ 80%
- All E2E smoke tests pass
- HTML report generated at `tests/reports/index.html`

---

## Dependencies

```
Phase 1 (Protocol) ── no dependencies
    │
    ▼
Phase 2 (Backend ║ Frontend) ── depends on Phase 1 protocol lock
    │
    ▼
Phase 3 (Testing) ── depends on Phase 2 code complete
```

Backend and Frontend in Phase 2 have no mutual dependency — they communicate only through the protocol contract defined in Phase 1.

---

## Files Summary

| Phase | Files Created | Files Modified |
|-------|-------------|---------------|
| 1 | `backend/app/protocol.py` | `src/shared/ipc/protocol.ts`, `channels.ts`, `electronApi.ts` |
| 2 (Backend) | `backend/app/executors/base.py`, `process.py`, `timeout.py` | `base_executor.py`, `tool_manager.py`, `api_handler.py`, all handlers |
| 2 (Frontend) | `DeviceList.vue`, `DeviceDetail.vue`, `DeviceActionBar.vue`, `GeneralSettings.vue`, `PathSettings.vue`, `AdvancedSettings.vue`, `PackageInfo.vue`, `SignatureForm.vue`, `ConfigService.ts`, `variables.css` | All existing `.vue` files, `ServiceManager.ts`, `unifiedApi.ts`, deleted `StoreService.ts`, `SettingsService.ts`, `PluginService.ts` |
| 3 | `vitest.config.ts`, `tests/reports/`, `tests/contracts/`, `tests/unit/`, `tests/integration/`, `tests/e2e/` | `package.json` (scripts), `tsconfig.json` (test includes) |
