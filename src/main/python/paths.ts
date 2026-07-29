import { app } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import { promises as fs } from 'fs';
import log from 'electron-log';
import { APP_CONFIG_KEYS, PATH_CONFIG_DEFAULTS } from '../../shared/config/pathConfig';

type AppStoreLike = { get(key: string): unknown };

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export function getBaseDir(): string {
  return !app.isPackaged
    ? path.join(__dirname, '..', '..')
    : process.resourcesPath;
}

export function toNonEmptyString(value: unknown, fallback: string): string {
  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }
  return fallback;
}

export function resolvePathFromBase(baseDir: string, targetPath: string): string {
  if (path.isAbsolute(targetPath)) return targetPath;
  const cleanPath = targetPath.replace(/^\.[\\/]/, '');
  return path.join(baseDir, cleanPath);
}

export async function resolveServerPath(
  appStore: AppStoreLike,
  baseDir: string
): Promise<{ scriptPath: string; absServerDir: string }> {
  const serverDir = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.server), PATH_CONFIG_DEFAULTS.server);
  const serverEntry = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.serverEntry), PATH_CONFIG_DEFAULTS.serverEntry);

  let absServerDir = resolvePathFromBase(baseDir, serverDir);
  let scriptPath = path.join(absServerDir, serverEntry);
  try {
    await fs.access(scriptPath);
  } catch {
    const fallbackServerDir = resolvePathFromBase(baseDir, PATH_CONFIG_DEFAULTS.server);
    const fallbackScriptPath = path.join(fallbackServerDir, PATH_CONFIG_DEFAULTS.serverEntry);
    log.warn(`Configured server path invalid, fallback to: ${fallbackScriptPath}`);
    absServerDir = fallbackServerDir;
    scriptPath = fallbackScriptPath;
  }
  log.info(`Python Script Path: ${scriptPath}`);
  return { scriptPath, absServerDir };
}

export async function resolvePythonExecutable(
  appStore: AppStoreLike,
  baseDir: string
): Promise<{ pythonExecutable: string; absRuntimeDir: string }> {
  const runtimeDir = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.runtime), PATH_CONFIG_DEFAULTS.runtime);
  const runtimeExecutable = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.runtimeExecutable), PATH_CONFIG_DEFAULTS.runtimeExecutable);

  let pythonExecutable = 'python';
  let absRuntimeDir = resolvePathFromBase(baseDir, runtimeDir);
  const candidate = path.join(absRuntimeDir, runtimeExecutable);
  try {
    await fs.access(candidate);
    pythonExecutable = candidate;
    log.info(`Using Python Runtime: ${pythonExecutable}`);
  } catch {
    const defaultRuntimeDir = resolvePathFromBase(baseDir, PATH_CONFIG_DEFAULTS.runtime);
    const defaultCandidate = path.join(defaultRuntimeDir, PATH_CONFIG_DEFAULTS.runtimeExecutable);
    try {
      await fs.access(defaultCandidate);
      absRuntimeDir = defaultRuntimeDir;
      pythonExecutable = defaultCandidate;
      log.warn(`Configured runtime path invalid, fallback to: ${pythonExecutable}`);
    } catch {
      log.warn(`Python runtime not found at ${candidate}, falling back to system python`);
    }
  }
  return { pythonExecutable, absRuntimeDir };
}
