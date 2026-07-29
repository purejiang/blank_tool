import { ChildProcessWithoutNullStreams } from 'child_process';
import { BrowserWindow } from 'electron';
import log from 'electron-log';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

const STDERR_RING_MAX = 200;
const PYTHON_ERROR_LEVEL = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - .* - (ERROR|CRITICAL) -/;
const PYTHON_TRACEBACK = /Traceback \(most recent call last\):/;

function broadcastStderrTail(lines: string[], reason: 'crash' | 'traceback') {
  BrowserWindow.getAllWindows().forEach(win => {
    if (!win.isDestroyed()) {
      win.webContents.send(IPC_CHANNEL_NAMES.backendStderrTail, { lines, reason });
    }
  });
}

export function createStderrCapturer(proc: ChildProcessWithoutNullStreams) {
  const ring: string[] = [];

  proc.stderr.on('data', (data) => {
    const chunk = data.toString();
    for (const line of chunk.split('\n').filter(l => l.length > 0)) {
      ring.push(line);
      if (ring.length > STDERR_RING_MAX) ring.shift();
    }
    if (PYTHON_TRACEBACK.test(chunk)) {
      log.error(`Python: ${chunk.trimEnd()}`);
      // Real-time traceback broadcast — does not wait for process exit
      broadcastStderrTail([chunk], 'traceback');
    } else if (PYTHON_ERROR_LEVEL.test(chunk)) {
      log.error(`Python: ${chunk.trimEnd()}`);
    }
  });

  return {
    getBuffer: () => ring,
    getTail: (maxLines: number = 50): string[] => ring.slice(-maxLines),
    dumpOnClose: (code: number | null, signal: NodeJS.Signals | null) => {
      if (code !== 0 && code !== null) {
        const tail = ring.join('\n');
        log.error(`Python process crashed (exit code ${code}). Last ${ring.length} lines of stderr:\n${tail}`);
        broadcastStderrTail(ring.slice(-50), 'crash');
      } else {
        log.info(`Python process exited (code ${code}, signal ${signal})`);
      }
      ring.length = 0;
    }
  };
}
