# App Update Detection & In-App Update — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add GitHub Releases-based auto-update to the Electron app using electron-updater

**Architecture:** electron-updater in main process with event-driven IPC to renderer. Pinia store + UpdateService + UpdateDialog for UI. NSIS silent install on Windows, manual prompt on macOS/Linux.

**Tech Stack:** electron-updater ^6.x, Vue 3, Pinia, Naive UI, vitest

---

### Task 0: Baseline check

**Files:** (none)

- [ ] **Step 1: Run full check suite**

```bash
npm run check
```

Expected: all existing checks pass. This confirms a clean baseline before making changes.

---

### Task 1: Install dependency & configure publish

**Files:**
- Modify: `package.json`

- [ ] **Step 1: Add publish config to build section**

In `package.json`, inside the `"build"` block, add after `"linux": { "target": "AppImage" }`:

```json
"publish": {
  "provider": "github",
  "owner": "purejiang",
  "repo": "blank_tool"
}
```

- [ ] **Step 2: Add electron-updater dependency**

In `"dependencies"`, add:

```json
"electron-updater": "^6.6.2"
```

- [ ] **Step 3: Install**

```bash
npm install
```

Expected: installs without errors.

- [ ] **Step 4: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: add electron-updater and github publish config"
```

---

### Task 2: Define IPC channels

**Files:**
- Modify: `src/shared/ipc/channels.ts`

- [ ] **Step 1: Add update channel entries**

In `IPC_CHANNELS`, add after the `respondQuitDialog` line:

```typescript
// Update — Renderer → Main
checkForUpdates: { name: 'check-for-updates', direction: 'renderer-to-main' },
quitAndInstall: { name: 'quit-and-install', direction: 'renderer-to-main' },

// Update — Main → Renderer
updateAvailable: { name: 'update-available', direction: 'main-to-renderer', payload: '{ version: string, releaseNotes: string, releaseDate: string }' },
updateNotAvailable: { name: 'update-not-available', direction: 'main-to-renderer', payload: '{ version: string }' },
downloadProgress: { name: 'download-progress', direction: 'main-to-renderer', payload: '{ percent: number, bytesPerSecond: number, transferred: number, total: number }' },
updateDownloaded: { name: 'update-downloaded', direction: 'main-to-renderer', payload: '{ version: string }' },
updateError: { name: 'update-error', direction: 'main-to-renderer', payload: '{ message: string }' },
```

- [ ] **Step 2: Commit**

```bash
git add src/shared/ipc/channels.ts
git commit -m "feat: add update IPC channel definitions"
```

---

### Task 3: Create updater core module

**Files:**
- Create: `src/main/updater/updater.ts`
- Create: `tests/unit/main/updater.test.ts`

- [ ] **Step 1: Write failing test for updater init**

Create `tests/unit/main/updater.test.ts`:

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'

const mockOn = vi.fn()
const mockAutoUpdater = {
  on: mockOn,
  checkForUpdates: vi.fn(),
  quitAndInstall: vi.fn(),
  logger: null as unknown,
  autoDownload: false,
  allowDowngrade: false,
  allowPrerelease: false,
}

vi.mock('electron-updater', () => ({
  autoUpdater: mockAutoUpdater,
}))

vi.mock('electron', () => ({
  app: { isPackaged: true },
  BrowserWindow: {
    getAllWindows: vi.fn(() => []),
  },
}))

describe('updater', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
  })

  describe('initAutoUpdater', () => {
    it('configures updater with correct settings', async () => {
      const { initAutoUpdater } = await import('@/main/updater/updater')
      initAutoUpdater()

      // Verify settings were applied
      expect(mockAutoUpdater.autoDownload).toBe(true)
      expect(mockAutoUpdater.allowDowngrade).toBe(false)
      expect(mockAutoUpdater.allowPrerelease).toBe(false)
    })

    it('registers all event listeners', async () => {
      const { initAutoUpdater } = await import('@/main/updater/updater')
      initAutoUpdater()

      const eventNames = mockOn.mock.calls.map((c: any[]) => c[0])
      expect(eventNames).toContain('update-available')
      expect(eventNames).toContain('update-not-available')
      expect(eventNames).toContain('download-progress')
      expect(eventNames).toContain('update-downloaded')
      expect(eventNames).toContain('error')
    })

    it('skips in dev mode', async () => {
      const { app: electronApp } = await import('electron')
      ;(electronApp as any).isPackaged = false

      const { initAutoUpdater } = await import('@/main/updater/updater')
      initAutoUpdater()

      // Should not register listeners in dev
      expect(mockOn).not.toHaveBeenCalled()
    })

    it('does not re-initialize if already initialized', async () => {
      const { initAutoUpdater } = await import('@/main/updater/updater')
      initAutoUpdater()
      const callCount = mockOn.mock.calls.length
      initAutoUpdater()
      expect(mockOn.mock.calls.length).toBe(callCount)
    })
  })

  describe('quitAndInstall', () => {
    it('calls autoUpdater.quitAndInstall', async () => {
      const { quitAndInstall } = await import('@/main/updater/updater')
      quitAndInstall()
      expect(mockAutoUpdater.quitAndInstall).toHaveBeenCalledWith(false, true)
    })
  })
})
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
npx vitest run tests/unit/main/updater.test.ts
```

Expected: FAIL — module `@/main/updater/updater` not found.

- [ ] **Step 3: Write updater module**

Create `src/main/updater/updater.ts`:

```typescript
import { autoUpdater } from 'electron-updater'
import { BrowserWindow, app } from 'electron'
import log from 'electron-log'
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels'

let initialized = false

function sendToAllWindows(channel: string, data: unknown): void {
  const wins = BrowserWindow.getAllWindows()
  for (const w of wins) {
    if (!w.isDestroyed()) {
      w.webContents.send(channel, data)
    }
  }
}

export function initAutoUpdater(): void {
  if (initialized) return
  initialized = true

  if (!app.isPackaged) {
    log.info('AutoUpdater: disabled in dev mode')
    return
  }

  autoUpdater.logger = log
  autoUpdater.autoDownload = true
  autoUpdater.allowDowngrade = false
  autoUpdater.allowPrerelease = false

  autoUpdater.on('checking-for-update', () => {
    log.info('AutoUpdater: checking for update...')
  })

  autoUpdater.on('update-available', (info) => {
    log.info('AutoUpdater: update available', info.version)
    sendToAllWindows(IPC_CHANNEL_NAMES.updateAvailable, {
      version: info.version,
      releaseNotes: (info.releaseNotes as string) || '',
      releaseDate: info.releaseDate || '',
    })
  })

  autoUpdater.on('update-not-available', (info) => {
    log.info('AutoUpdater: already up to date', info.version)
    sendToAllWindows(IPC_CHANNEL_NAMES.updateNotAvailable, { version: info.version })
  })

  autoUpdater.on('download-progress', (p) => {
    sendToAllWindows(IPC_CHANNEL_NAMES.downloadProgress, {
      percent: p.percent,
      bytesPerSecond: p.bytesPerSecond,
      transferred: p.transferred,
      total: p.total,
    })
  })

  autoUpdater.on('update-downloaded', (info) => {
    log.info('AutoUpdater: update downloaded', info.version)
    sendToAllWindows(IPC_CHANNEL_NAMES.updateDownloaded, { version: info.version })
  })

  autoUpdater.on('error', (err) => {
    log.error('AutoUpdater: error', err)
    sendToAllWindows(IPC_CHANNEL_NAMES.updateError, { message: err.message })
  })
}

export async function checkForUpdatesManual(): Promise<{
  updateAvailable: boolean
  version?: string
  releaseNotes?: string
}> {
  if (!app.isPackaged) {
    return { updateAvailable: false }
  }
  try {
    const result = await autoUpdater.checkForUpdates()
    if (result?.updateInfo) {
      return {
        updateAvailable: true,
        version: result.updateInfo.version,
        releaseNotes: (result.updateInfo.releaseNotes as string) || '',
      }
    }
    return { updateAvailable: false }
  } catch {
    return { updateAvailable: false }
  }
}

export async function autoCheckForUpdates(): Promise<void> {
  if (!app.isPackaged) return
  try {
    await autoUpdater.checkForUpdates()
  } catch {
    // "no update available" throws in electron-updater; silently ignore for auto-check
  }
}

export function quitAndInstall(): void {
  autoUpdater.quitAndInstall(false, true)
}
```

- [ ] **Step 4: Run test, confirm it passes**

```bash
npx vitest run tests/unit/main/updater.test.ts
```

Expected: PASS (all 5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/main/updater/updater.ts tests/unit/main/updater.test.ts
git commit -m "feat: add auto-updater core module with tests"
```

---

### Task 4: Create update IPC handlers

**Files:**
- Create: `src/main/ipc/updateHandlers.ts`
- Modify: `src/main/ipc/index.ts`
- Modify: `src/main/main.ts`

- [ ] **Step 1: Create update IPC handlers**

Create `src/main/ipc/updateHandlers.ts`:

```typescript
import { ipcMain } from 'electron'
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels'
import { checkForUpdatesManual, quitAndInstall } from '../updater/updater'

export function setupUpdateHandlers(): void {
  ipcMain.handle(IPC_CHANNEL_NAMES.checkForUpdates, async () => {
    return await checkForUpdatesManual()
  })

  ipcMain.handle(IPC_CHANNEL_NAMES.quitAndInstall, () => {
    quitAndInstall()
  })
}
```

- [ ] **Step 2: Wire update handlers into ipc/index.ts**

In `src/main/ipc/index.ts`, add import at top:

```typescript
import { setupUpdateHandlers } from './updateHandlers'
```

In `setupAllHandlers` body, add after `setupElectronHandlers();`:

```typescript
    setupUpdateHandlers()
```

- [ ] **Step 3: Init updater and trigger auto-check in main.ts**

In `src/main/main.ts`, add import at top:

```typescript
import { initAutoUpdater, autoCheckForUpdates } from './updater/updater'
```

In `app.whenReady().then(async () => {...})`, add after `createWindow();`:

```typescript
  // Auto-update check (3s delay to avoid impacting startup)
  setTimeout(() => {
    initAutoUpdater()
    autoCheckForUpdates()
  }, 3000)
```

- [ ] **Step 4: Commit**

```bash
git add src/main/ipc/updateHandlers.ts src/main/ipc/index.ts src/main/main.ts
git commit -m "feat: wire update IPC handlers and auto-check on startup"
```

---

### Task 5: Test-driven updateStore

**Files:**
- Create: `tests/unit/stores/updateStore.test.ts`
- Create: `src/renderer/stores/updateStore.ts`

- [ ] **Step 1: Write failing test for updateStore**

Create `tests/unit/stores/updateStore.test.ts`:

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

describe('updateStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.resetModules()
  })

  describe('initial state', () => {
    it('starts in idle status', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      expect(store.status).toBe('idle')
    })

    it('has null for version fields', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      expect(store.latestVersion).toBeNull()
      expect(store.releaseNotes).toBeNull()
      expect(store.currentVersion).toBe('')
    })

    it('has zero download progress', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      expect(store.downloadPercent).toBe(0)
      expect(store.downloadSpeed).toBeNull()
    })

    it('has null error', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      expect(store.error).toBeNull()
    })
  })

  describe('setStatus', () => {
    it('transitions status', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      store.setStatus('checking')
      expect(store.status).toBe('checking')
      store.setStatus('downloading')
      expect(store.status).toBe('downloading')
      store.setStatus('downloaded')
      expect(store.status).toBe('downloaded')
      store.setStatus('error')
      expect(store.status).toBe('error')
    })
  })

  describe('setUpdateInfo', () => {
    it('sets version and release notes', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      store.setUpdateInfo({
        version: '2.0.6',
        releaseNotes: '## Bug fixes\n- Fixed crash',
        releaseDate: '2026-06-20',
      })
      expect(store.latestVersion).toBe('2.0.6')
      expect(store.releaseNotes).toBe('## Bug fixes\n- Fixed crash')
    })
  })

  describe('setDownloadProgress', () => {
    it('updates progress values', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      store.setDownloadProgress({ percent: 54.2, bytesPerSecond: 12800000, transferred: 67108864, total: 134217728 })
      expect(store.downloadPercent).toBe(54.2)
      expect(store.downloadSpeed).toBe(12800000)
    })
  })

  describe('reset', () => {
    it('resets all state to initial', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      store.setStatus('downloading')
      store.setUpdateInfo({ version: '2.0.6', releaseNotes: 'test' })
      store.setDownloadProgress({ percent: 50, bytesPerSecond: 1000, transferred: 500, total: 1000 })
      store.reset()
      expect(store.status).toBe('idle')
      expect(store.latestVersion).toBeNull()
      expect(store.downloadPercent).toBe(0)
      expect(store.downloadSpeed).toBeNull()
    })
  })
})
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
npx vitest run tests/unit/stores/updateStore.test.ts
```

Expected: FAIL — module `@/renderer/stores/updateStore` not found.

- [ ] **Step 3: Write updateStore**

Create `src/renderer/stores/updateStore.ts`:

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'

export type UpdateStatus = 'idle' | 'checking' | 'available' | 'downloading' | 'downloaded' | 'error' | 'not-available'

export interface UpdateInfo {
  version: string
  releaseNotes?: string
  releaseDate?: string
}

export interface DownloadProgress {
  percent: number
  bytesPerSecond: number
  transferred: number
  total: number
}

export const useUpdateStore = defineStore('update', () => {
  const status = ref<UpdateStatus>('idle')
  const currentVersion = ref('')
  const latestVersion = ref<string | null>(null)
  const releaseNotes = ref<string | null>(null)
  const releaseDate = ref<string | null>(null)
  const downloadPercent = ref(0)
  const downloadSpeed = ref<number | null>(null)
  const error = ref<string | null>(null)

  function setStatus(s: UpdateStatus): void {
    status.value = s
  }

  function setUpdateInfo(info: UpdateInfo): void {
    latestVersion.value = info.version
    releaseNotes.value = info.releaseNotes || null
    releaseDate.value = info.releaseDate || null
  }

  function setDownloadProgress(progress: DownloadProgress): void {
    downloadPercent.value = progress.percent
    downloadSpeed.value = progress.bytesPerSecond
  }

  function setError(message: string): void {
    error.value = message
  }

  function setCurrentVersion(version: string): void {
    currentVersion.value = version
  }

  function reset(): void {
    status.value = 'idle'
    latestVersion.value = null
    releaseNotes.value = null
    releaseDate.value = null
    downloadPercent.value = 0
    downloadSpeed.value = null
    error.value = null
  }

  return {
    status,
    currentVersion,
    latestVersion,
    releaseNotes,
    releaseDate,
    downloadPercent,
    downloadSpeed,
    error,
    setStatus,
    setUpdateInfo,
    setDownloadProgress,
    setError,
    setCurrentVersion,
    reset,
  }
})
```

Add to `src/renderer/stores/index.ts`:

```typescript
export { useUpdateStore } from './updateStore'
```

- [ ] **Step 4: Run test, confirm it passes**

```bash
npx vitest run tests/unit/stores/updateStore.test.ts
```

Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/renderer/stores/updateStore.ts src/renderer/stores/index.ts tests/unit/stores/updateStore.test.ts
git commit -m "feat: add updateStore with tests"
```

---

### Task 6: Create UpdateService

**Files:**
- Create: `src/renderer/services/UpdateService.ts`
- Modify: `src/renderer/App.vue` (register service)

- [ ] **Step 1: Write UpdateService**

Create `src/renderer/services/UpdateService.ts`:

```typescript
import { useUpdateStore } from '@stores/updateStore'
import type { UpdateStatus } from '@stores/updateStore'
import unifiedApi from '../api/unifiedApi'

class UpdateService {
  private store: ReturnType<typeof useUpdateStore> | null = null
  private unsubscribers: Array<() => void> = []

  private get api() {
    return unifiedApi.getAPI()
  }

  private getStore(): ReturnType<typeof useUpdateStore> {
    if (!this.store) {
      this.store = useUpdateStore()
    }
    return this.store
  }

  async initialize(): Promise<void> {
    const store = this.getStore()

    // Fetch current version from electron
    try {
      const info = await this.api?.getAppInfo?.()
      if (info?.version) {
        store.setCurrentVersion(info.version)
      }
    } catch {}

    // Listen for main process events — use specific named preload methods
    const api = this.api
    if (api?.onUpdateAvailable) {
      this.unsubscribers.push(api.onUpdateAvailable((data: any) => {
        store.setUpdateInfo({
          version: data.version,
          releaseNotes: data.releaseNotes,
          releaseDate: data.releaseDate,
        })
        store.setStatus('available')
      }))
    }

    if (api?.onUpdateNotAvailable) {
      this.unsubscribers.push(api.onUpdateNotAvailable((_data: any) => {
        store.setStatus('not-available')
      }))
    }

    if (api?.onDownloadProgress) {
      this.unsubscribers.push(api.onDownloadProgress((data: any) => {
        if (store.status !== 'downloading') {
          store.setStatus('downloading')
        }
        store.setDownloadProgress(data)
      }))
    }

    if (api?.onUpdateDownloaded) {
      this.unsubscribers.push(api.onUpdateDownloaded((data: any) => {
        store.setStatus('downloaded')
        if (data.version) {
          store.setUpdateInfo({ version: data.version })
        }
      }))
    }

    if (api?.onUpdateError) {
      this.unsubscribers.push(api.onUpdateError((data: any) => {
        store.setError(data.message || 'Update failed')
        store.setStatus('error')
      }))
    }
  }

  async checkForUpdates(): Promise<{ updateAvailable: boolean; version?: string; releaseNotes?: string }> {
    const store = this.getStore()
    store.setStatus('checking')
    store.setError(null)

    try {
      if (this.api?.checkForUpdates) {
        const result = await this.api.checkForUpdates()
        if (result.updateAvailable) {
          store.setUpdateInfo({
            version: result.version || '',
            releaseNotes: result.releaseNotes,
          })
          store.setStatus('available')
        } else {
          store.setStatus('not-available')
        }
        return result
      }
      throw new Error('checkForUpdates not available')
    } catch (err: any) {
      store.setError(err.message || 'Check failed')
      store.setStatus('error')
      throw err
    }
  }

  async quitAndInstall(): Promise<void> {
    try {
      if (this.api?.quitAndInstall) {
        await this.api.quitAndInstall()
      }
    } catch (err: any) {
      console.error('quitAndInstall failed:', err)
    }
  }

  getStatus(): UpdateStatus {
    return this.getStore().status
  }

  destroy(): void {
    for (const unsub of this.unsubscribers) {
      try { unsub() } catch {}
    }
    this.unsubscribers = []
  }
}

export default UpdateService
```

- [ ] **Step 2: Register UpdateService in App.vue**

In `src/renderer/App.vue`, add import:

```typescript
import UpdateService from '@services/UpdateService'
```

In `registerServices()` function, add after the other registrations:

```typescript
  serviceManager.register('update', UpdateService)
```

- [ ] **Step 3: Commit**

```bash
git add src/renderer/services/UpdateService.ts src/renderer/App.vue
git commit -m "feat: add UpdateService with IPC event wiring"
```

---

### Task 7: Wire update API in preload

**Files:**
- Modify: `src/preload/index.ts`

- [ ] **Step 1: Update preload update API**

The preload already has a stub at line 245:
```typescript
checkForUpdates: () => ipcInvoke('check-for-updates'),
```

Replace that line and add additional update methods. In the `electronApi` object, replace the existing `checkForUpdates` line with:

```typescript
  // 更新相关 - 系统调用
  checkForUpdates: () => ipcInvoke(IPC_CHANNEL_NAMES.checkForUpdates),
  quitAndInstall: () => ipcInvoke(IPC_CHANNEL_NAMES.quitAndInstall),

  // 更新事件监听 (each returns unsubscribe function)
  onUpdateAvailable: (callback: (data: any) => void) => {
    const handler = (_event: any, data: any) => callback(data)
    ipcRenderer.on(IPC_CHANNEL_NAMES.updateAvailable, handler)
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.updateAvailable, handler)
  },
  onUpdateNotAvailable: (callback: (data: any) => void) => {
    const handler = (_event: any, data: any) => callback(data)
    ipcRenderer.on(IPC_CHANNEL_NAMES.updateNotAvailable, handler)
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.updateNotAvailable, handler)
  },
  onDownloadProgress: (callback: (data: any) => void) => {
    const handler = (_event: any, data: any) => callback(data)
    ipcRenderer.on(IPC_CHANNEL_NAMES.downloadProgress, handler)
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.downloadProgress, handler)
  },
  onUpdateDownloaded: (callback: (data: any) => void) => {
    const handler = (_event: any, data: any) => callback(data)
    ipcRenderer.on(IPC_CHANNEL_NAMES.updateDownloaded, handler)
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.updateDownloaded, handler)
  },
  onUpdateError: (callback: (data: any) => void) => {
    const handler = (_event: any, data: any) => callback(data)
    ipcRenderer.on(IPC_CHANNEL_NAMES.updateError, handler)
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.updateError, handler)
  },
```

- [ ] **Step 2: Commit**

```bash
git add src/preload/index.ts
git commit -m "feat: wire update IPC methods and event listener in preload"
```

---

### Task 8: Create UpdateDialog component

**Files:**
- Create: `src/renderer/components/UpdateDialog.vue`

- [ ] **Step 1: Write UpdateDialog component**

Create `src/renderer/components/UpdateDialog.vue`:

```vue
<template>
  <n-modal
    :show="visible"
    :mask-closable="false"
    preset="card"
    :title="dialogTitle"
    style="max-width: 440px"
    @close="handleClose"
  >
    <template #header>
      <div style="text-align: center; width: 100%">
        <div style="font-size: 32px; margin-bottom: 4px">{{ statusIcon }}</div>
        <div style="font-size: 16px; font-weight: 700">{{ dialogTitle }}</div>
      </div>
    </template>

    <!-- Available state -->
    <div v-if="store.status === 'available'" class="update-body">
      <div class="version-compare">
        <span class="ver-old">{{ store.currentVersion || $t('common.unknown') }}</span>
        <n-icon size="16"><ArrowRight /></n-icon>
        <span class="ver-new">{{ store.latestVersion }}</span>
        <n-tag type="success" size="small" round>Latest</n-tag>
      </div>
      <div v-if="store.releaseNotes" class="release-notes">
        <div class="rn-title">{{ $t('update.releaseNotes') }}</div>
        <div class="rn-body">{{ store.releaseNotes }}</div>
      </div>
      <div class="update-actions">
        <n-button quaternary @click="handleClose">{{ $t('update.later') }}</n-button>
        <n-button type="primary" @click="handleDownload">{{ $t('update.download') }}</n-button>
      </div>
    </div>

    <!-- Downloading state -->
    <div v-else-if="store.status === 'downloading'" class="update-body">
      <div class="download-info">
        <span>{{ store.downloadPercent.toFixed(0) }}%</span>
        <span v-if="store.downloadSpeed">{{ formatSpeed(store.downloadSpeed) }}</span>
      </div>
      <n-progress
        type="line"
        :percentage="store.downloadPercent"
        :height="6"
        :border-radius="3"
        color="#22C55E"
        rail-color="rgba(0,0,0,0.06)"
      />
    </div>

    <!-- Downloaded state -->
    <div v-else-if="store.status === 'downloaded'" class="update-body">
      <p style="text-align: center; color: var(--app-text-secondary); font-size: 14px">
        {{ $t('update.restartToInstall') }}
      </p>
      <div class="update-actions">
        <n-button quaternary @click="handleClose">{{ $t('update.later') }}</n-button>
        <n-button type="primary" @click="handleRestart">{{ $t('update.restartNow') }}</n-button>
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="store.status === 'error'" class="update-body">
      <n-alert type="error" :title="store.error || $t('update.error')" />
      <div class="update-actions" style="margin-top: 16px">
        <n-button quaternary @click="handleClose">{{ $t('update.later') }}</n-button>
        <n-button type="primary" @click="handleRetry">{{ $t('app.retry') }}</n-button>
      </div>
    </div>

    <!-- Checking state -->
    <div v-else class="update-body" style="text-align: center; padding: 32px 0">
      <n-spin size="medium" />
      <p style="margin-top: 12px; color: var(--app-text-muted); font-size: 13px">{{ $t('update.checking') }}</p>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NModal, NButton, NProgress, NTag, NIcon, NAlert, NSpin } from 'naive-ui'
import { ArrowRight } from 'lucide-vue-next'
import { useUpdateStore } from '@stores/updateStore'

const { t } = useI18n()
const store = useUpdateStore()

const emit = defineEmits<{
  close: []
  download: []
  restart: []
  retry: []
}>()

const visible = computed(() =>
  ['checking', 'available', 'downloading', 'downloaded', 'error'].includes(store.status)
)

const statusIcon = computed(() => {
  switch (store.status) {
    case 'checking': return '🔍'
    case 'available': return '🎉'
    case 'downloading': return '⬇️'
    case 'downloaded': return '✅'
    case 'error': return '❌'
    default: return ''
  }
})

const dialogTitle = computed(() => {
  switch (store.status) {
    case 'checking': return t('update.checking')
    case 'available': return t('update.newVersion')
    case 'downloading': return t('update.downloading', { version: store.latestVersion || '' })
    case 'downloaded': return t('update.downloaded')
    case 'error': return t('update.error')
    default: return ''
  }
})

function formatSpeed(bytesPerSecond: number): string {
  if (bytesPerSecond < 1024) return `${bytesPerSecond} B/s`
  if (bytesPerSecond < 1048576) return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`
  return `${(bytesPerSecond / 1048576).toFixed(1)} MB/s`
}

function handleClose(): void {
  if (store.status === 'downloading') return // prevent closing during download
  emit('close')
}

function handleDownload(): void {
  emit('download')
}

function handleRestart(): void {
  emit('restart')
}

function handleRetry(): void {
  emit('retry')
}
</script>

<style scoped>
.update-body { padding: 8px 0; }
.version-compare {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 16px;
}
.ver-old { font-size: 13px; color: var(--app-text-muted); font-family: monospace; }
.ver-new { font-size: 15px; font-weight: 700; color: #22C55E; font-family: monospace; }
.release-notes {
  background: var(--app-hover);
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 16px;
}
.rn-title { font-size: 12px; font-weight: 600; color: var(--app-text-muted); margin-bottom: 8px; }
.rn-body { font-size: 13px; color: var(--app-text-secondary); white-space: pre-wrap; line-height: 1.6; }
.update-actions { display: flex; gap: 10px; justify-content: flex-end; }
.download-info { display: flex; justify-content: space-between; font-size: 13px; color: var(--app-text-secondary); margin-bottom: 8px; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add src/renderer/components/UpdateDialog.vue
git commit -m "feat: add UpdateDialog component with multi-state support"
```

---

### Task 9: Add update progress bar and mount components in App.vue

**Files:**
- Modify: `src/renderer/App.vue`

- [ ] **Step 1: Add UpdateService initialization and update UI in App.vue**

In `src/renderer/App.vue`:

Add imports at top:
```typescript
import UpdateDialog from '@components/UpdateDialog.vue'
import UpdateService from '@services/UpdateService'
import { useUpdateStore } from '@stores/updateStore'
```

In `registerServices()`:
```typescript
  serviceManager.register('update', UpdateService)
```

Add after `loadApplicationData()` call in `initializeApplication()` (or in `prepareUI()`):
In the `prepareUI` function, add at the end:
```typescript
  // Initialize update service (event listeners only, no auto-check here)
  try {
    const updateService = await serviceManager.getService('update')
    if (updateService) {
      await updateService.initialize()
    }
  } catch {}
```

In the template, add UpdateDialog after `<QuitDialog />`:
```html
                <UpdateDialog
                  @close="handleUpdateClose"
                  @download="handleUpdateDownload"
                  @restart="handleUpdateRestart"
                  @retry="handleUpdateRetry"
                />
```

Add a download progress bar in the template, before `<router-view />` but inside `<n-layout-content>`:
```html
                <!-- Update download progress bar (non-blocking) -->
                <div v-if="updateStore.status === 'downloading' || updateStore.status === 'downloaded'" class="update-bar">
                  <div :class="['update-bar-inner', updateStore.status === 'downloaded' ? 'ready' : '']">
                    <span class="update-bar-icon">{{ updateStore.status === 'downloaded' ? '✅' : '⬇️' }}</span>
                    <div class="update-bar-content">
                      <div class="update-bar-title">
                        {{ updateStore.status === 'downloaded' ? $t('update.downloaded') : $t('update.downloading', { version: updateStore.latestVersion || '' }) }}
                      </div>
                      <div v-if="updateStore.status === 'downloading'" class="update-bar-sub">
                        {{ updateStore.downloadPercent.toFixed(0) }}% · {{ formatSpeed(updateStore.downloadSpeed || 0) }}
                      </div>
                      <div v-if="updateStore.status === 'downloading'" class="update-bar-track">
                        <div class="update-bar-fill" :style="{ width: updateStore.downloadPercent + '%' }"></div>
                      </div>
                    </div>
                    <n-button
                      v-if="updateStore.status === 'downloaded'"
                      size="small"
                      type="primary"
                      @click="handleUpdateRestart"
                    >
                      {{ $t('update.restartNow') }}
                    </n-button>
                  </div>
                </div>
```

In `<script setup>`, add the store and event handlers:
```typescript
const updateStore = useUpdateStore()

function formatSpeed(bytesPerSecond: number): string {
  if (!bytesPerSecond) return ''
  if (bytesPerSecond < 1024) return `${bytesPerSecond} B/s`
  if (bytesPerSecond < 1048576) return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`
  return `${(bytesPerSecond / 1048576).toFixed(1)} MB/s`
}

async function handleUpdateClose(): Promise<void> {
  updateStore.reset()
}

async function handleUpdateDownload(): Promise<void> {
  // Triggered from UpdateDialog; auto-download is already running
  // Just keep the dialog open to show progress
}

async function handleUpdateRestart(): Promise<void> {
  const updateService = await serviceManager.getService('update')
  if (updateService) {
    await updateService.quitAndInstall()
  }
}

async function handleUpdateRetry(): Promise<void> {
  const updateService = await serviceManager.getService('update')
  if (updateService) {
    await updateService.checkForUpdates()
  }
}
```

Add styles at the bottom:
```css
/* Update progress bar */
.update-bar {
  position: fixed;
  top: 0;
  left: 220px;
  right: 0;
  z-index: 100;
  padding: 0 24px;
}
.update-bar-inner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: #f0fdf4;
  border: 1px solid #86efac;
  border-radius: 0 0 10px 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.update-bar-inner.ready {
  background: #eff6ff;
  border-color: #93c5fd;
}
.update-bar-icon { font-size: 16px; flex-shrink: 0; }
.update-bar-content { flex: 1; min-width: 0; }
.update-bar-title { font-size: 13px; font-weight: 600; color: #166534; }
.update-bar-inner.ready .update-bar-title { color: #1e40af; }
.update-bar-sub { font-size: 12px; color: #15803d; margin-top: 2px; }
.update-bar-inner.ready .update-bar-sub { color: #2563eb; }
.update-bar-track { height: 3px; background: #dcfce7; border-radius: 2px; margin-top: 4px; }
.update-bar-fill { height: 100%; background: #22c55e; border-radius: 2px; transition: width 0.3s ease; }
```

- [ ] **Step 2: Commit**

```bash
git add src/renderer/App.vue
git commit -m "feat: integrate update progress bar and UpdateDialog in App.vue"
```

---

### Task 10: Add update button to AboutPage

**Files:**
- Modify: `src/renderer/views/AboutPage.vue`

- [ ] **Step 1: Add update section to AboutPage**

In `src/renderer/views/AboutPage.vue`, add the update section after the "构建信息" card content (after the `info-grid` div and before the closing `</n-card>`).

Add import at top of `<script setup>`:
```typescript
import { useUpdateStore } from '@stores/updateStore'
import { useMessage } from 'naive-ui'
```

Add store and message in script:
```typescript
const updateStore = useUpdateStore()
const message = useMessage()
```

Add the update status check function:
```typescript
const updateButtonText = computed(() => {
  if (updateStore.status === 'checking') return t('update.checking')
  if (updateStore.status === 'available') return t('update.newVersion')
  if (updateStore.status === 'downloaded') return t('update.restartNow')
  return t('update.checkUpdate')
})

const updateButtonDisabled = computed(() =>
  updateStore.status === 'checking' || updateStore.status === 'downloading'
)

const updateStatusText = computed(() => {
  if (updateStore.status === 'not-available') return t('update.upToDate')
  if (updateStore.status === 'error') return updateStore.error || t('update.error')
  if (updateStore.status === 'downloaded') return `${t('update.downloaded')} (v${updateStore.latestVersion})`
  if (updateStore.status === 'available') return `v${updateStore.latestVersion} ${t('update.newVersion')}`
  return ''
})

async function checkForUpdate(): Promise<void> {
  try {
    const result = await window.electronAPI.checkForUpdates()
    if (!result || !result.updateAvailable) {
      message.success(t('update.upToDate'))
    }
  } catch (err: any) {
    message.error(err.message || t('update.error'))
  }
}
```

In the template, add inside the "构建信息" card, after `</div>` (closing info-grid) and before `</n-card>`:

```html
          <div class="update-section">
            <div class="update-status">
              <span class="update-label">{{ t('update.title') }}</span>
              <span v-if="updateStatusText" class="update-status-text">{{ updateStatusText }}</span>
            </div>
            <n-button
              size="small"
              :disabled="updateButtonDisabled"
              :loading="updateStore.status === 'checking'"
              @click="checkForUpdate"
            >
              {{ updateButtonText }}
            </n-button>
          </div>
```

Add styles:
```css
.update-section { display: flex; align-items: center; justify-content: space-between; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--app-border); gap: 12px; }
.update-status { display: flex; flex-direction: column; gap: 2px; }
.update-label { font-size: 13px; font-weight: 600; color: var(--app-text-primary); }
.update-status-text { font-size: 12px; color: var(--app-text-muted); }
```

- [ ] **Step 2: Commit**

```bash
git add src/renderer/views/AboutPage.vue
git commit -m "feat: add check-for-update button to About page"
```

---

### Task 11: Add i18n strings

**Files:**
- Modify: `src/renderer/i18n/locales/zh-CN.ts`
- Modify: `src/renderer/i18n/locales/en-US.ts`

- [ ] **Step 1: Add Chinese strings**

In `src/renderer/i18n/locales/zh-CN.ts`, add a new top-level key `update`:

```typescript
  update: {
    title: '更新',
    checking: '正在检查...',
    upToDate: '当前已是最新版本',
    newVersion: '发现新版本',
    downloading: '正在下载 v{version}',
    downloaded: '更新已就绪',
    restartToInstall: '重启后将自动安装新版本',
    restartNow: '重启安装',
    later: '稍后再说',
    download: '立即下载',
    releaseNotes: '更新日志',
    checkUpdate: '检查更新',
    error: '更新失败',
    networkError: '网络连接失败，请稍后重试',
  },
```

- [ ] **Step 2: Add English strings**

In `src/renderer/i18n/locales/en-US.ts`, add the same key with English values:

```typescript
  update: {
    title: 'Update',
    checking: 'Checking...',
    upToDate: "You're up to date",
    newVersion: 'New version available',
    downloading: 'Downloading v{version}',
    downloaded: 'Update ready',
    restartToInstall: 'App will restart to install the update',
    restartNow: 'Restart & Install',
    later: 'Later',
    download: 'Download',
    releaseNotes: 'Release Notes',
    checkUpdate: 'Check for Updates',
    error: 'Update failed',
    networkError: 'Network error, please try again',
  },
```

- [ ] **Step 3: Commit**

```bash
git add src/renderer/i18n/locales/zh-CN.ts src/renderer/i18n/locales/en-US.ts
git commit -m "feat: add update i18n strings for zh-CN and en-US"
```

---

### Task 12: Run full verification

**Files:** (none)

- [ ] **Step 1: Run type check**

```bash
npm run typecheck
```

Expected: no new type errors.

- [ ] **Step 2: Run tests**

```bash
npm run test
```

Expected: all tests pass.

- [ ] **Step 3: Run full check**

```bash
npm run check
```

Expected: all checks pass.

- [ ] **Step 4: Commit any fixes if needed**

```bash
git add -A
git commit -m "fix: resolve type errors and test failures from update feature"
```

---

### Task 13: Manual verification (dev mode)

**Files:** (none)

- [ ] **Step 1: Start dev mode**

```bash
npm run dev
```

Expected: app starts normally in dev mode with no update-related errors. Verify:
- About page shows update section with "检查更新" button
- Clicking the button shows "当前已是最新版本" toast (dev mode returns updateAvailable: false)
- No console errors from update service

---

### Task 14: Production build test

**Files:** (none)

- [ ] **Step 1: Build Windows installer**

```bash
# Set GH_TOKEN to a token with repo scope (optional — only needed for auto-publish)
# set GH_TOKEN=ghp_xxxxxxxxxxxx
npm run build:win
```

Expected: 
- Build succeeds
- `build/Blank Tool Setup X.Y.Z.exe` is created
- If GH_TOKEN is set, the release is auto-published to GitHub

- [ ] **Step 2: Verify publish config is correct**

Check that `package.json` → `build.publish` matches the GitHub repo. Verify the electron-builder output includes "publishing" step (if GH_TOKEN is set).

- [ ] **Step 3: Install and verify update flow**

Install the built .exe. For a real update test:
1. Build and publish v2.0.5 to GitHub Release
2. Bump version to 2.0.6 in package.json
3. Build and publish v2.0.6
4. Install v2.0.5, start it — should detect v2.0.6 and auto-download

---

### Summary

| Task | Files Created | Files Modified |
|------|--------------|----------------|
| 1 | — | `package.json` |
| 2 | — | `src/shared/ipc/channels.ts` |
| 3 | `src/main/updater/updater.ts`, `tests/unit/main/updater.test.ts` | — |
| 4 | `src/main/ipc/updateHandlers.ts` | `src/main/ipc/index.ts`, `src/main/main.ts` |
| 5 | `src/renderer/stores/updateStore.ts`, `tests/unit/stores/updateStore.test.ts` | `src/renderer/stores/index.ts` |
| 6 | `src/renderer/services/UpdateService.ts` | `src/renderer/App.vue` |
| 7 | — | `src/preload/index.ts` |
| 8 | `src/renderer/components/UpdateDialog.vue` | — |
| 9 | — | `src/renderer/App.vue` |
| 10 | — | `src/renderer/views/AboutPage.vue` |
| 11 | — | `src/renderer/i18n/locales/zh-CN.ts`, `src/renderer/i18n/locales/en-US.ts` |
| 12–14 | — | — (verification only) |

**Total: 5 new files, 4 test files, 9 modified files**
