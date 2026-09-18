/**
 * Typed accessors for the preload bridge.
 *
 * `unifiedApi.getAPI()` returns `Partial<ElectronApi>` on purpose: in browser
 * mode there is no Electron preload at all, and in unit tests the bridge is a
 * hand-written stub. Every service therefore has to decide what a *missing*
 * preload method means, and that decision used to be spelled out by hand ~55
 * times as
 *
 *     const api = unifiedApi.getAPI()
 *     if (api && typeof api.x === 'function') { return await api.x(...) }
 *     throw new Error('x API not implemented')
 *
 * with three different error strings across services (`x API not implemented`,
 * `x 方法未实现`, `x not available`). These two helpers encode the only two
 * sensible answers:
 *
 *   - `requireApiMethod` — the method is essential; absence is an error.
 *   - `optionalApiMethod` — absence is normal (an event subscription that never
 *     fires outside Electron, a dialog wrapper in a browser); callers skip.
 *
 * Kept in its own module rather than on `unifiedApi` so that the many tests
 * which mock the bridge as `{ default: { getAPI } }` do not have to re-stub
 * these too.
 */
import unifiedApi from './unifiedApi'
import type { ElectronApi } from '../../shared/ipc/electronApi'

/** Callable shape of an `ElectronApi` member, preserving parameter/return types. */
type ApiMethod<K extends keyof ElectronApi> =
  ElectronApi[K] extends (...args: infer A) => infer R ? (...args: A) => R : never

/**
 * Resolve a preload method the caller cannot work without. Unlike
 * `unifiedApi.safeCall()`, which reports absence as a `{ success: false }`
 * value, this throws — which is what the services' existing `try/catch` and
 * `.rejects` contracts expect.
 *
 * @throws Error `<method> API not implemented` when the bridge is absent
 *   (browser mode, partial mock) or the named method is missing.
 */
export function requireApiMethod<K extends keyof ElectronApi>(method: K): ApiMethod<K> {
  const candidate = unifiedApi.getAPI()?.[method]
  if (typeof candidate !== 'function') {
    throw new Error(`${String(method)} API not implemented`)
  }
  return candidate as unknown as ApiMethod<K>
}

/**
 * Resolve an optional preload method. Returns `null` when the bridge or the
 * method is missing, instead of throwing — for feature-detection paths where
 * "not supported in this environment" is a perfectly good outcome.
 */
export function optionalApiMethod<K extends keyof ElectronApi>(method: K): ApiMethod<K> | null {
  const candidate = unifiedApi.getAPI()?.[method]
  return typeof candidate === 'function' ? (candidate as unknown as ApiMethod<K>) : null
}
