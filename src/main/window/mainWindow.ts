import { BrowserWindow, Menu, app, nativeTheme } from 'electron';
import path from 'path';
import { existsSync } from 'fs';
import { appStore } from '../stores/index';
import { APP_CONFIG_KEYS, PATH_CONFIG_DEFAULTS } from '../../shared/config/pathConfig';
import { setMainWindow } from '../state';
import { createTray } from './tray';
import { setupQuitDialog } from './quitDialog';
import { toNonEmptyString } from '../utils/strings';

// electron-vite 的 ESM shim 注入 __dirname/__filename（指向 bundle 所在的 dist/main/）
const __iconPath = path.join(__dirname, 'assets', 'images', 'icon.png');

// 原生窗口底色，必须与 themes.css 的 --app-body-bg 一致：不设置时 Electron 用默认
// 白色，暗色用户冷启动会看到一帧白闪（renderer 的 data-theme 尚未生效时）。
const WINDOW_BG = { light: '#F1F5F9', dark: '#0F172A' } as const;

function resolveWindowBackground(): string {
  const mode = appStore.get('theme') || 'auto';
  const dark = mode === 'dark' || (mode === 'auto' && nativeTheme.shouldUseDarkColors);
  return dark ? WINDOW_BG.dark : WINDOW_BG.light;
}

// At runtime (electron-vite bundle) __dirname is dist/main/; the '..' ascends to dist/,
// so candidates like 'preload\index.mjs' resolve to dist/preload/index.mjs.
function resolvePathFromMainDir(targetPath: string): string {
  if (path.isAbsolute(targetPath)) return targetPath;
  return path.join(__dirname, '..', targetPath);
}

function resolvePreloadPath(): string {
  const configured = appStore.get(APP_CONFIG_KEYS.preloadCandidates);
  const rawCandidates = Array.isArray(configured) && configured.length > 0
    ? configured.map((item) => toNonEmptyString(item, ''))
    : PATH_CONFIG_DEFAULTS.preloadCandidates;
  const candidates = rawCandidates
    .filter(Boolean)
    .map((candidate) => resolvePathFromMainDir(candidate));
  const found = candidates.find((candidate) => existsSync(candidate));
  if (found) return found;
  return candidates[0];
}

export function createMainWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1200,
    height: 800,
    // 三栏布局（minmax 栅格）的最小可用宽度；低于该值列会互相挤压
    minWidth: 960,
    minHeight: 640,
    backgroundColor: resolveWindowBackground(),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      sandbox: false,
      preload: resolvePreloadPath()
    },
    icon: __iconPath
  });

  Menu.setApplicationMenu(null);

  if (!app.isPackaged && process.env.ELECTRON_RENDERER_URL) {
    window.loadURL(process.env.ELECTRON_RENDERER_URL);
    window.webContents.openDevTools();
  } else if (!app.isPackaged) {
    const devServerUrl = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.devServerUrl), PATH_CONFIG_DEFAULTS.devServerUrl);
    window.loadURL(devServerUrl);
    window.webContents.openDevTools();
  } else {
    const rendererEntry = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.rendererEntry), PATH_CONFIG_DEFAULTS.rendererEntry);
    const indexPath = resolvePathFromMainDir(rendererEntry);
    window.loadFile(indexPath).catch(err => {
      // log is not imported here; the caller (main.ts) already configured logging.
      // Errors from loadFile are terminal — electron will render an error page.
      console.error('Failed to load index.html:', err);
      console.error('Attempted path:', indexPath);
    });
  }

  setMainWindow(window);
  createTray();
  setupQuitDialog(window);

  window.on('closed', () => {
    setMainWindow(null);
  });

  return window;
}
