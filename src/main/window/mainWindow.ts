import { BrowserWindow, Menu, app } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import { existsSync } from 'fs';
import { appStore } from '../stores/index';
import { APP_CONFIG_KEYS, PATH_CONFIG_DEFAULTS } from '../../shared/config/pathConfig';
import { setMainWindow } from '../state';
import { createTray } from './tray';
import { setupQuitDialog } from './quitDialog';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const __iconPath = path.join(__dirname, 'assets', 'images', 'icon.png');

function toNonEmptyString(value: unknown, fallback: string): string {
  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }
  return fallback;
}

// At runtime (vite-plugin-electron bundle) __dirname is dist/main/; the '..' ascends to dist/,
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

  if (!app.isPackaged && process.env.VITE_DEV_SERVER_URL) {
    window.loadURL(process.env.VITE_DEV_SERVER_URL);
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
