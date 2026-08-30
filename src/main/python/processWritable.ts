import { ChildProcessWithoutNullStreams } from 'child_process';

/**
 * Dependency-free check of whether the Python backend process can still
 * receive stdin commands.
 *
 * It lives in its own module so both `service.ts` (which imports
 * electron-store) and `commandHandlers.ts` can share the logic without
 * pulling electron-store into the command-handler unit tests.  Previously
 * `commandHandlers.ts` kept an inline copy (`isBackendWritable`) purely to
 * avoid importing `service.ts` — extracting here removes that duplication.
 */
export function isProcessWritable(proc: ChildProcessWithoutNullStreams | null): boolean {
  return Boolean(
    proc &&
      !proc.killed &&
      proc.exitCode === null &&
      proc.stdin &&
      !proc.stdin.destroyed &&
      !proc.stdin.writableEnded &&
      proc.stdin.writable
  );
}
