# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm run dev          # Start dev mode (Vite HMR + Electron)
npm run build:win    # Build Windows installer (.exe)
npm run build:mac    # Build macOS .dmg
npm run build:linux  # Build Linux AppImage
npm run lint         # Type-check Vue/TS (vue-tsc --noEmit --pretty false)
npm run typecheck    # Full type-check with verbose output
npm run test         # Run contract tests (node --test)
npm run check        # Run lint + typecheck + test
```

No Python-specific dev commands are defined; the backend runs as a child process spawned by Electron, using `python backend/main.py`.

## Architecture

This is a **three-process desktop application** for Android development tools (ADB, Apktool, bundletool, etc.):

```
┌─────────────────────────────────────────────────────────┐
│  Renderer (Vue 3 + Pinia + Vue Router)                  │
│  window.electronAPI  ← contextBridge.exposeInMainWorld  │
├─────────────────────────────────────────────────────────┤
│  Main Process (Electron)                                │
│  IPC handlers → spawn Python child process              │
├─────────────────────────────────────────────────────────┤
│  Python Backend (stdin/stdout JSON-RPC)                 │
│  ApiHandler → tool_manager / handlers / plugins          │
└─────────────────────────────────────────────────────────┘
```

### Communication flow

1. **Renderer → Main**: Renderer calls `window.electronAPI.*` methods (defined in `src/preload/index.ts`). These route through `contextBridge` to IPC handlers in `src/main/ipc/`.

2. **Main → Python**: IPC `commandHandlers.ts` sends JSON-RPC requests to the Python child process via `stdin`, reads responses from `stdout`. Each request has a unique `id`; responses are matched via a callback map. Timeout is 30 seconds.

3. **Python request handling**: `backend/main.py` reads lines from stdin, dispatches to `ApiHandler.handle_request()`. The handler auto-discovers API methods by scanning `app/handlers/` for modules with an `API_MAP` dict (mapping method names like `"adb.devices"` to handler functions).

4. **Streaming responses**: Handler functions decorated with `@streaming` (from `app/common/decorators.py`) run in a thread and emit multiple responses with `"finished": false` until completion. The main process routes streaming events (logcat output, etc.) to the renderer via named IPC channels.

### Backend auto-discovery

- **Handlers**: Any `.py` file in `backend/app/handlers/` exporting `API_MAP` is automatically registered. The key is the method name (e.g., `"adb.devices"`), the value is the handler function.
- **Tools**: Any `BaseTool` subclass in `backend/app/tools/` is auto-discovered by `ToolManager`. Tool subclasses are: `BinaryTool`, `JavaTool` (.jar), `PythonTool` (.py), `NodeTool` (.js).
- **Plugins**: Any `.py` file in `backend/plugins/` with a `run(context, **params)` function is auto-loaded.

### Renderer service layer

`ServiceManager` (`src/renderer/services/ServiceManager.ts`) is a DI container: services register with a constructor + dependencies, then lazily instantiated on first `getService()`. Services are registered in `App.vue`'s `registerServices()`.

Pinia stores (`src/renderer/stores/`) use a custom localStorage persistence plugin (defined in `src/renderer/main.ts`). Stores with `persist: true` or `persist: { key }` options auto-sync to localStorage.

### Configuration

- **App config**: `electron-store` in main process (`src/main/stores/appStore.ts`), with JSON schema validation and versioned migrations. Renderer accesses via `window.electronAPI.appConfig.get/set/getAll`.
- **Backend config**: `.env` file + `server.config.json` in the backend directory, loaded by `app/utils/env.py`. Key env vars: `BT_RUNTIME_DIR` (bundled tools path), `BT_CACHE_DIR`, `BT_OUTPUT_DIR`, `BT_JAVA_BIN`.
- **Shared path config**: `src/shared/config/pathConfig.ts` defines defaults for runtime/server/preload paths used by both main and renderer processes.

### Path resolution

The app runs in two modes:
- **Dev** (`!app.isPackaged`): paths resolve relative to the project root
- **Production** (`app.isPackaged`): paths resolve relative to `process.resourcesPath` (where `extraResources` are placed by electron-builder — see `package.json` build config)

### Tools bundled in `runtime/`

The `runtime/` directory contains bundled binaries structured like:
```
runtime/
  adb/adb.exe
  aapt/aapt2.exe
  apktool/apktool.jar
  bundletool/bundletool.jar
  android/zipalign.exe, apksigner.jar
  jre/bin/java.exe, jarsigner.exe
  python/python.exe
```
