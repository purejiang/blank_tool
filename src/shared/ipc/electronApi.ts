import type { ApiMethodMap, BackendApiRequest, JsonObject } from './protocol'

type MethodParams<M extends keyof ApiMethodMap> = ApiMethodMap[M]['params']
type MethodResult<M extends keyof ApiMethodMap> = ApiMethodMap[M]['result']

export interface TypedCallBackendAPI {
  <M extends keyof ApiMethodMap>(method: M, params: MethodParams<M>): Promise<MethodResult<M>>
  <M extends string>(method: M, params?: JsonObject): Promise<unknown>
}

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
  onDeviceChange: (callback: (devices: unknown[]) => void) => () => void
  onLogUpdate: (callback: (message: string) => void) => () => void
  onLogcatOutput: (callback: (output: string) => void) => () => void
  onLogcatStarted: (callback: () => void) => () => void
  onLogcatFinished: (callback: () => void) => () => void
  onLogcatError: (callback: (error: string) => void) => () => void
  removeLogcatListener: () => void
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
