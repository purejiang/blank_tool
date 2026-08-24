import { ChildProcessWithoutNullStreams } from 'child_process';
import log from 'electron-log';

const STDERR_RING_MAX = 200;
const PYTHON_ERROR_LEVEL = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - .* - (ERROR|CRITICAL) -/;
const PYTHON_TRACEBACK = /Traceback \(most recent call last\):/;

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
    } else if (PYTHON_ERROR_LEVEL.test(chunk)) {
      log.error(`Python: ${chunk.trimEnd()}`);
    }
  });

  return {
    dumpOnClose: (code: number | null, signal: NodeJS.Signals | null) => {
      if (code !== 0 && code !== null) {
        const tail = ring.join('\n');
        log.error(`Python process crashed (exit code ${code}). Last ${ring.length} lines of stderr:\n${tail}`);
      } else {
        log.info(`Python process exited (code ${code}, signal ${signal})`);
      }
      ring.length = 0;
    }
  };
}
