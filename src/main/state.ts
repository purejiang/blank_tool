import { BrowserWindow, Tray } from 'electron';
import { ChildProcessWithoutNullStreams } from 'child_process';

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let pythonProcess: ChildProcessWithoutNullStreams | null = null;
let startPythonPromise: Promise<ChildProcessWithoutNullStreams | null> | null = null;
let isAppQuitting = false;

// mainWindow
export const getMainWindow = () => mainWindow;
export const setMainWindow = (w: BrowserWindow | null) => { mainWindow = w; };

// tray
export const getTray = () => tray;
export const setTray = (t: Tray | null) => { tray = t; };

// pythonProcess
export const getPythonProcess = () => pythonProcess;
export const setPythonProcess = (p: ChildProcessWithoutNullStreams | null) => { pythonProcess = p; };

// startPythonPromise
export const getStartPythonPromise = () => startPythonPromise;
export const setStartPythonPromise = (p: Promise<ChildProcessWithoutNullStreams | null> | null) => { startPythonPromise = p; };

// isAppQuitting
export const getIsAppQuitting = () => isAppQuitting;
export const setIsAppQuitting = (v: boolean) => { isAppQuitting = v; };
