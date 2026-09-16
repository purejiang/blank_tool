import { app } from 'electron';
import path from 'path';
import { promises as fs } from 'fs';
import log from 'electron-log';
import { APP_CONFIG_KEYS, PATH_CONFIG_DEFAULTS } from '../../shared/config/pathConfig';
import { toNonEmptyString } from '../utils/strings';

type AppStoreLike = { get(key: string): unknown };

export function getBaseDir(): string {
  return !app.isPackaged
    ? path.join(__dirname, '..', '..')
    : process.resourcesPath;
}

/**
 * Resolve a configured (usually relative) path against `baseDir`.
 * Absolute paths are returned untouched; a leading `./` or `.\` is stripped
 * before joining. An empty input short-circuits to an empty string so that
 * "path not configured" stays distinguishable from "resolved to baseDir".
 */
export function resolvePathFromBase(baseDir: string, targetPath: string): string {
  if (!targetPath) return targetPath;
  if (path.isAbsolute(targetPath)) return targetPath;
  const cleanPath = targetPath.replace(/^\.[\\/]/, '');
  return path.join(baseDir, cleanPath);
}

/**
 * Absolute path of the configured Python interpreter.
 *
 * ``runtimeExecutable`` is RELATIVE TO ``runtime/`` (that is how the spawn path
 * is built below): the bundled interpreter is ``runtime/python/python.exe``.
 * Resolving it against the app base instead yields ``<app>/python/python.exe``
 * — a path that cannot exist even in a packaged build, which is exactly the
 * phantom path the settings page used to display.
 *
 * An ABSOLUTE value (the user picked a system interpreter in the file dialog)
 * is returned untouched — ``path.join(runtimeDir, 'D:\\x\\python.exe')`` would
 * produce ``<runtime>/D:\x\python.exe`` and silently ignore the override.
 */
export function resolveRuntimeExecutablePath(baseDir: string, runtimeExecutable: string): string {
  if (!runtimeExecutable) return '';
  if (path.isAbsolute(runtimeExecutable)) return runtimeExecutable;
  const runtimeDir = resolvePathFromBase(baseDir, PATH_CONFIG_DEFAULTS.runtime);
  return path.join(runtimeDir, runtimeExecutable.replace(/^\.[\\/]/, ''));
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
  const runtimeExecutable = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.runtimeExecutable), PATH_CONFIG_DEFAULTS.runtimeExecutable);

  // The runtime dir is not configurable — runtime/ is the container of the
  // bundled tools and always resolves from the shared default.
  let pythonExecutable = 'python';
  const absRuntimeDir = resolvePathFromBase(baseDir, PATH_CONFIG_DEFAULTS.runtime);
  const candidate = resolveRuntimeExecutablePath(baseDir, runtimeExecutable);
  try {
    await fs.access(candidate);
    pythonExecutable = candidate;
    log.info(`Using Python Runtime: ${pythonExecutable}`);
  } catch {
    const defaultCandidate = resolveRuntimeExecutablePath(baseDir, PATH_CONFIG_DEFAULTS.runtimeExecutable);
    try {
      await fs.access(defaultCandidate);
      pythonExecutable = defaultCandidate;
      log.warn(`Configured runtime path invalid, fallback to: ${pythonExecutable}`);
    } catch {
      log.warn(`Python runtime not found at ${candidate}, falling back to system python`);
    }
  }
  return { pythonExecutable, absRuntimeDir };
}
