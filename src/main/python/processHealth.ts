import { ChildProcessWithoutNullStreams } from 'child_process';

/**
 * True when the Python child process is alive *and* its stdin can still
 * accept a JSON-RPC request. Every write path (request dispatch, ensure) must
 * agree on this predicate — keep it in one place.
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
