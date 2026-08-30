import path from 'path';
import { spawn, ChildProcessWithoutNullStreams } from 'child_process';
import log from 'electron-log';
import { appStore } from '../stores/index';
import { getAppLocalDataPath, ensureDir } from '../utils/appPaths';
import {
  getPythonProcess, setPythonProcess,
  getStartPythonPromise, setStartPythonPromise,
  getIsAppQuitting
} from '../state';
import { getBaseDir, resolveServerPath, resolvePythonExecutable } from './paths';
import { createStderrCapturer } from './stderrCapture';
import { isProcessWritable } from './processWritable';

export async function startPythonService(): Promise<ChildProcessWithoutNullStreams | null> {
  if (getIsAppQuitting()) {
    return null;
  }
  const baseDir = getBaseDir();
  const { scriptPath } = await resolveServerPath(appStore, baseDir);
  const { pythonExecutable, absRuntimeDir } = await resolvePythonExecutable(appStore, baseDir);

  try {
    const localDataPath = getAppLocalDataPath();
    const cacheDir = path.join(localDataPath, 'cache');
    const outputDir = path.join(localDataPath, 'output');
    const tasksDir = path.join(localDataPath, 'tasks');
    const logsDir = path.join(localDataPath, 'logs');
    ensureDir(cacheDir);
    ensureDir(outputDir);
    ensureDir(tasksDir);
    ensureDir(logsDir);

    const logsConfig = appStore.get('logs') as { level?: string } | undefined;
    const logLevel = logsConfig?.level || 'info';

    const env = {
        ...process.env,
        BT_RUNTIME_DIR: absRuntimeDir || '',
        BT_CACHE_DIR: cacheDir,
        BT_TASKS_DIR: tasksDir,
        BT_OUTPUT_DIR: outputDir,
        BT_LOG_DIR: logsDir,
        BT_LOG_LEVEL: logLevel
    };
    log.info(`Spawning Python process with: ${pythonExecutable} ${scriptPath}`);
    const proc = spawn(pythonExecutable, [scriptPath], { env });
    setPythonProcess(proc);
  } catch (e) {
    log.error('启动 Python 进程失败:', e);
    setPythonProcess(null);
    return null;
  }

  const proc = getPythonProcess()!;
  proc.on('error', (err) => {
    log.error('Python 进程错误:', err);
  });

  // Ring buffer for Python stderr — forensic record, only dumped on crash.
  // Python's own logger (StreamHandler→stderr + DailyRotatingFileHandler→cli-*.log)
  // already records every line; relaying it again here was the source of duplication.
  const capturer = createStderrCapturer(proc);

  proc.on('close', (code, signal) => {
    capturer.dumpOnClose(code, signal);
    setPythonProcess(null);
  });
  return proc;
}

export async function ensurePythonService(): Promise<ChildProcessWithoutNullStreams | null> {
  if (getIsAppQuitting()) {
    return null;
  }
  if (isProcessWritable(getPythonProcess())) {
    return getPythonProcess();
  }
  if (!getStartPythonPromise()) {
    setStartPythonPromise(startPythonService().finally(() => {
      setStartPythonPromise(null);
    }));
  }
  return await getStartPythonPromise()!;
}
