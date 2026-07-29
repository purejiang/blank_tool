/**
 * Error thrown by the preload layer when the backend (or main-process IPC bridge)
 * returns an error envelope `{ type: 'error', payload: { code, message } }`.
 *
 * The `code` field carries the JSON-RPC-style error code:
 * - `-32001` backend-not-running
 * - `-32002` send-failed
 * - `-32003` timeout
 * - `-32004` backend-exit
 * - `-32603` internal-error (default)
 * - backend-defined codes (positive integers, handler-specific)
 *
 * Renderer code can switch on `code` to react differently to distinct failures:
 * ```ts
 * try { await window.electronAPI.callBackendAPI('adb.devices') }
 * catch (e) {
 *   if (e instanceof BackendError && e.code === -32001) { /* backend down, show retry *\/ }
 * }
 * ```
 */
export class BackendError extends Error {
  readonly code: number;

  constructor(message: string, code: number = -32603) {
    super(message);
    this.name = 'BackendError';
    this.code = code;
  }
}
