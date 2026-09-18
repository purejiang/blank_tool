import { BrowserWindow, Tray } from 'electron';
import { ChildProcessWithoutNullStreams } from 'child_process';

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let pythonProcess: ChildProcessWithoutNullStreams | null = null;
let startPythonPromise: Promise<ChildProcessWithoutNullStreams | null> | null = null;
let isAppQuitting = false;
// 当前 pythonProcess 的启动时刻（epoch ms）。诊断页的「运行时间」靠它算——
// 主进程知道 spawn 时刻，就不用为了拿 uptime 去发一次 stdin 往返。
// 崩溃后 ensure 重启会换进程对象，这里跟着重置，显示的时间永远属于当前进程。
let pythonStartedAt: number | null = null;

// mainWindow
export const getMainWindow = () => mainWindow;
export const setMainWindow = (w: BrowserWindow | null) => { mainWindow = w; };

// tray
export const getTray = () => tray;
export const setTray = (t: Tray | null) => { tray = t; };

// pythonProcess
export const getPythonProcess = () => pythonProcess;
export const setPythonProcess = (p: ChildProcessWithoutNullStreams | null) => {
  // 只在「进程对象真的换了」时才重置计时，重复 set 同一个进程不会把时间清零。
  if (p !== pythonProcess) {
    pythonStartedAt = p ? Date.now() : null;
  }
  pythonProcess = p;
};
export const getPythonStartedAt = () => pythonStartedAt;

// startPythonPromise
export const getStartPythonPromise = () => startPythonPromise;
export const setStartPythonPromise = (p: Promise<ChildProcessWithoutNullStreams | null> | null) => { startPythonPromise = p; };

// isAppQuitting
export const getIsAppQuitting = () => isAppQuitting;
export const setIsAppQuitting = (v: boolean) => { isAppQuitting = v; };
