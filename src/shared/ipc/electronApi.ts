import type { ApiMethodMap, BackendApiRequest, JsonObject } from './protocol'

type MethodParams<M extends keyof ApiMethodMap> = ApiMethodMap[M]['params']
type MethodResult<M extends keyof ApiMethodMap> = ApiMethodMap[M]['result']

export interface TypedCallBackendAPI {
  <M extends keyof ApiMethodMap>(method: M, params: MethodParams<M>): Promise<MethodResult<M>>
  <M extends string>(method: M, params?: JsonObject): Promise<unknown>
}

/** See also src/shared/stores/appConfigStore.ts for the broader AppConfigStoreLike used inside renderer services. */
export interface AppConfigApi {
  get: (key?: string) => Promise<unknown>
  set: (key: string, value: unknown) => Promise<unknown>
  setMany: (updates: Record<string, unknown>) => Promise<unknown>
  getAll: () => Promise<Record<string, unknown>>
  reset: () => Promise<unknown>
}

export interface UserConfigApi {
  get: (key?: string) => Promise<unknown>
  set: (key: string, value: unknown) => Promise<unknown>
  getAll: () => Promise<Record<string, unknown>>
  reset: () => Promise<unknown>
}

export interface SettingsViewModel {
  settings: Record<string, unknown>
  displayPaths: { runtime: string; server: string }
}

export interface SettingsApi {
  getViewModel: () => Promise<SettingsViewModel>
  resolvePaths: (paths: { runtime?: unknown; server?: unknown }) => Promise<{ runtime: string; server: string }>
}

export interface ElectronApi {
  callBackendAPI: TypedCallBackendAPI
  callBackendByRequest: (request: BackendApiRequest) => Promise<unknown>
  appConfig: AppConfigApi
  userConfig: UserConfigApi
  settings: SettingsApi
  getBackendHealth?: () => Promise<{ healthy: boolean; uptime_s?: number }>
  logsTail?: (lines?: number) => Promise<{ lines: string[]; truncated?: boolean }>
  readElectronLogTail?: (lines?: number) => Promise<{ lines: string[]; truncated?: boolean }>
  onQuitDialog?: (callback: () => void) => () => void
  respondQuitDialog?: (action: string) => void
  rendererLog: (level: 'error' | 'warn' | 'info', message: string) => Promise<unknown>
  setToolCustomPath?: (toolName: string, path: string) => Promise<unknown>
  resetToolCustomPath?: (toolName: string) => Promise<unknown>
  getToolCustomPaths?: () => Promise<Record<string, string>>
  [key: string]: unknown
}

declare global {
  interface Window {
    electronAPI: ElectronApi
  }
}
