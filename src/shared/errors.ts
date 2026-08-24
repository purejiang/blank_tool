/**
 * Error thrown by the preload layer when the backend (or main-process IPC bridge)
 * returns an error envelope `{ type: 'error', payload: { code, message } }`.
 *
 * Two distinct error-code spaces coexist, and they must not collide:
 *
 * 1. Main-process bridge codes (this file — emitted by commandHandlers.ts when
 *    the bridge itself fails, i.e. before/without a Python response):
 *    - `-32001` backend-not-running
 *    - `-32002` send-failed
 *    - `-32003` timeout
 *    - `-32004` backend-exit (reserved; the close handler currently rejects a plain Error)
 *    - `-32603` internal-error (default)
 *
 * 2. Python backend codes (`cli/app/protocol/messages.py` `ErrorCode`), which use
 *    the standard JSON-RPC range and are carried INSIDE the `result.payload.code`
 *    of a success-shaped envelope:
 *    - `-32700` parse-error
 *    - `-32601` method-not-found
 *    - `-32603` internal-error
 *    (plus handler-specific positive codes)
 *
 * Renderer code can switch on `code` to react differently to distinct failures:
 * ```ts
 * try { await window.electronAPI.callBackendAPI('adb.devices') }
 * catch (e) {
 *   if (e instanceof BackendError && e.code === -32001) { /* backend down, show retry *\/ }
 * }
 * ```
 */
export const MAIN_BRIDGE_ERROR_CODES = {
  BACKEND_NOT_RUNNING: -32001,
  SEND_FAILED: -32002,
  TIMEOUT: -32003,
  BACKEND_EXIT: -32004,
  INTERNAL_ERROR: -32603,
} as const

export class BackendError extends Error {
  readonly code: number;

  constructor(message: string, code: number = -32603) {
    super(message);
    this.name = 'BackendError';
    this.code = code;
  }
}
