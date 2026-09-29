/**
 * Structured-clone-safe payloads for the IPC boundary.
 *
 * The renderer talks to the main process through `contextBridge`, and every
 * argument of a bridged call is copied with structured-clone semantics. A Vue
 * **reactive proxy is NOT cloneable**, so handing one over throws
 * `DataCloneError: An object could not be cloned.` — with no hint about which
 * field was at fault.
 *
 * That is easy to hit by accident, because reading a nested value out of a
 * `reactive()` object yields another proxy:
 *
 *   const form = reactive({ tags: [] })   // n-select multiple 绑的就是这种字段
 *   const payload = { tags: form.tags }    // ← payload.tags 是 Proxy，不是数组
 *
 * The backend protocol is JSON-RPC, so a JSON round trip is exactly the right
 * normalization: it strips proxies, functions and symbols, and guarantees the
 * result cannot fail the clone again. Callers must therefore send the value
 * this function returns — never the live reactive object.
 *
 * JSON semantics apply: `undefined` object values and functions disappear,
 * `Date` becomes an ISO string, `NaN`/`Infinity` become `null`.
 */

/** Deep-copy `value` into plain, structured-clone-safe JSON data. */
export function toJsonPayload<T>(value: T): T {
  if (value === undefined || value === null) return value
  try {
    const encoded = JSON.stringify(value)
    // JSON.stringify returns undefined for functions/symbols at the top level.
    if (encoded === undefined) {
      throw new TypeError(`a ${typeof value} value has no JSON representation`)
    }
    return JSON.parse(encoded) as T
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    throw new Error(`payload is not JSON-serializable: ${reason}`)
  }
}
