/**
 * Shared shape for app-config store accessors.
 *
 * This is the union of the prior 3 local definitions
 * (SettingsService.ts, StoreService.ts, electronApi.ts AppConfigApi).
 * The actual Pinia store at src/renderer/stores/appConfigStore.ts must
 * satisfy this interface.
 *
 * For the IPC contract, see src/shared/ipc/electronApi.ts AppConfigApi.
 */
export interface AppConfigStoreLike {
  config: Record<string, unknown>
  /** Pinia store default config (optional — only some store wrappers expose it) */
  defaultConfig?: Record<string, unknown>
  /** Batch-update multiple keys (Pinia store returns Promise<boolean>) */
  update?: (updates: Record<string, unknown>) => Promise<unknown> | void
  /** Reset store to defaults */
  reset?: () => Promise<unknown> | void
  /** Atomically replace the entire config object */
  replaceAll?: (cfg: Record<string, unknown>) => void
}
