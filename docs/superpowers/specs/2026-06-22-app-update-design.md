# App Update Detection & In-App Update — Design Spec

**Date**: 2026-06-22  
**Author**: Claude (brainstorming session)  
**Branch**: dev  

## Overview

Add GitHub Releases-based update detection and in-app auto-update to Blank Tool, an Electron + Vue 3 desktop app. Uses `electron-updater` with GitHub provider, electron-builder auto-publish, and NSIS silent install.

## Requirements

- **Update source**: GitHub Releases (`purejiang/blank_tool`), stable releases only (no pre-release/draft)
- **Check trigger**: Auto-check on app start (3s delay) + manual button in About page
- **Update strategy**: Auto-download silently → notify on completion → user clicks to restart & install
- **Platform priority**: Windows (NSIS silent `/S`), macOS (prompt to open .dmg), Linux (prompt to replace AppImage)
- **Publishing**: electron-builder auto-upload with `GH_TOKEN` env var
- **Dev mode**: Disable update checks in dev (`!app.isPackaged`)

## Architecture

### New Files

| File | Purpose |
|------|---------|
| `src/main/updater/updater.ts` | Core auto-update logic: init, check, event wiring |
| `src/main/ipc/updateHandlers.ts` | IPC handlers for update operations |
| `src/renderer/components/UpdateDialog.vue` | Full update dialog (version info, release notes, download) |
| `src/renderer/stores/updateStore.ts` | Pinia store for update state |
| `src/renderer/services/UpdateService.ts` | Renderer-side update service |

### Modified Files

| File | Changes |
|------|---------|
| `package.json` | Add `publish` config, add `electron-updater` dependency |
| `src/main/main.ts` | Init updater after app ready |
| `src/main/ipc/index.ts` | Register update IPC handlers |
| `src/main/ipc/electronHandlers.ts` | Add `check-for-updates` + `quit-and-install` handlers |
| `src/preload/index.ts` | Wire up update API methods |
| `src/shared/ipc/channels.ts` | Add 6 new IPC channel definitions |
| `src/renderer/views/AboutPage.vue` | Add check-for-update button + status text |
| `src/renderer/App.vue` | Register UpdateService, mount UpdateDialog + download progress bar |
| `src/renderer/i18n/locales/en-US.ts` | Update i18n strings |
| `src/renderer/i18n/locales/zh-CN.ts` | Update i18n strings |

## IPC Channels

### Renderer → Main (invoke)

| Channel | Payload | Response |
|---------|---------|----------|
| `check-for-updates` | — | `{ updateAvailable: boolean, version?: string, releaseNotes?: string }` |
| `quit-and-install` | — | void |
| `get-update-status` | — | `{ status: 'idle' \| 'checking' \| 'downloading' \| 'downloaded' \| 'error', progress?: number, version?: string }` |

### Main → Renderer (send)

| Channel | Payload |
|---------|---------|
| `update-available` | `{ version: string, releaseNotes: string, releaseDate: string, size: number }` |
| `download-progress` | `{ percent: number, bytesPerSecond: number, transferred: number, total: number }` |
| `update-downloaded` | `{ version: string }` |
| `update-error` | `{ message: string }` |
| `update-not-available` | `{ version: string }` |

## Data Flow

```
App Start (main.ts)
  └─ !isPackaged → skip
  └─ isPackaged → setTimeout(3000) → autoUpdater.checkForUpdates()
       ├─ no update → IPC: update-not-available → (nothing shown)
       └─ update found → autoUpdater.downloadUpdate()
            ├─ IPC: download-progress → renderer shows progress bar
            ├─ IPC: update-downloaded → renderer shows "restart" prompt
            └─ user clicks restart → autoUpdater.quitAndInstall()

Manual Check (About page)
  └─ renderer: IPC check-for-updates
       └─ main: autoUpdater.checkForUpdates()
            ├─ no update → resolve { updateAvailable: false } → toast "最新版本"
            └─ update found → show UpdateDialog → user clicks download
                 └─ same flow as auto-download
```

## UI Components

### About Page — Update Section

- Location: Bottom of "构建信息" card, separated by a divider
- Text: "更新" + status text ("当前已是最新版本" / "发现新版本 v2.0.6" / "正在检查...")
- Button: "检查更新" (secondary style), disabled while checking
- Click: triggers `updateStore.checkForUpdates()` → shows loading → result in toast or dialog

### Download Progress Bar (App.vue level)

- Green-tinted info banner at top of main content area
- Shows: "正在下载 v2.0.6" + percentage + speed + progress bar
- Non-blocking: user can continue using the app
- Auto-hides on completion or error

### Update Dialog (UpdateDialog.vue)

- Triggered by: manual check finding an update
- Shows: version comparison (current → new), "Latest" badge, release notes, file size
- Buttons: "稍后再说" (dismiss) / "立即下载" (download)
- During download: switches to progress state within the dialog

### Download Complete Prompt

- Non-blocking prompt bar: "更新已就绪" + "重启后将自动安装 vX.Y.Z"
- Button: "重启安装" → calls `quit-and-install`

## Configuration

### package.json additions

```json
{
  "build": {
    "publish": {
      "provider": "github",
      "owner": "purejiang",
      "repo": "blank_tool"
    }
  },
  "dependencies": {
    "electron-updater": "^6.x"
  }
}
```

### Publishing workflow

```bash
# Set GitHub personal access token (needs repo scope)
export GH_TOKEN=ghp_xxxxxxxxxxxx

# Build + auto-publish to GitHub Release
npm run build:win   # Creates draft release + uploads .exe
npm run build:mac   # Uploads .dmg
npm run build:linux # Uploads .AppImage
```

The tag version is read from `package.json` → `version`. electron-builder creates the tag and release automatically.

## Error Handling

| Scenario | Handling |
|----------|----------|
| No network | Silent fail on startup check; toast error on manual check |
| GitHub API rate limit | Retry after 60s with backoff |
| Download interrupted | electron-updater auto-resumes (range requests) |
| Insufficient disk space | Error message with space requirement |
| Install fails (permissions) | Prompt user to manually run installer |
| macOS Gatekeeper block | Inform user to open .dmg manually from Finder |
| Dev mode | Skip all update logic, log "updates disabled in dev" |

## State Management (updateStore)

```typescript
interface UpdateState {
  status: 'idle' | 'checking' | 'available' | 'downloading' | 'downloaded' | 'error' | 'not-available'
  currentVersion: string
  latestVersion: string | null
  releaseNotes: string | null
  releaseDate: string | null
  downloadPercent: number
  downloadSpeed: number | null
  error: string | null
}
```

## i18n Keys (新增)

| Key | zh-CN | en-US |
|-----|-------|-------|
| `update.title` | 更新 | Update |
| `update.checking` | 正在检查... | Checking... |
| `update.upToDate` | 当前已是最新版本 | You're up to date |
| `update.newVersion` | 发现新版本 | New version available |
| `update.downloading` | 正在下载 v{version} | Downloading v{version} |
| `update.downloaded` | 更新已就绪 | Update ready |
| `update.restartToInstall` | 重启后将自动安装 | Restart to install |
| `update.restartNow` | 重启安装 | Restart & Install |
| `update.later` | 稍后再说 | Later |
| `update.download` | 立即下载 | Download |
| `update.releaseNotes` | 更新日志 | Release Notes |
| `update.checkUpdate` | 检查更新 | Check for Updates |
| `update.error` | 更新失败 | Update failed |
| `update.networkError` | 网络连接失败，请稍后重试 | Network error, please try again |

## Testing Strategy

- **Unit**: UpdateService, updateStore state transitions
- **Integration**: Mock GitHub API responses for check/different version scenarios
- **Manual**: Build with `GH_TOKEN`, publish a test release, verify full flow
- **Edge cases**: Offline mode, rate limit, already-latest, download cancel

## Out of Scope (for now)

- Pre-release channel support
- Differential/delta updates (binary diff)
- Custom update server
- Auto-update interval (just startup check)
- Windows code signing
- macOS notarization
