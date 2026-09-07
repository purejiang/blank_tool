import type { ApiMethodMap, BackendApiRequest, JsonObject } from '../../shared/ipc/protocol';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';
import { ipcInvoke } from './ipcInvoke';
import { unwrapBackendResponse } from './unwrapBackendResponse';

type MethodParams<M extends keyof ApiMethodMap> = ApiMethodMap[M]['params'];
type MethodResult<M extends keyof ApiMethodMap> = ApiMethodMap[M]['result'];

/**
 * Vue reactive proxies are not structured-cloneable, so a params object that
 * holds a reactive array (e.g. automation steps straight out of a Pinia/Vue
 * state) makes `ipcRenderer.invoke` reject with "could not be cloned".
 * The backend speaks JSON-RPC anyway, so normalizing to plain JSON data here
 * is always safe and keeps every caller cloneable.
 */
function toPlainParams<T>(params: T): T {
  if (params === undefined || params === null) return params
  try {
    return JSON.parse(JSON.stringify(params)) as T
  } catch {
    return params
  }
}

// 统一的后端API调用函数
export const callBackendByRequest = async (request: BackendApiRequest) => {
  return await ipcInvoke(IPC_CHANNEL_NAMES.callBackendApi, request);
};

// Typed overload: when callers pass a literal ApiMethodMap key, TypeScript enforces params/result types.
export function callBackendAPI<M extends keyof ApiMethodMap>(
  method: M,
  params?: MethodParams<M>,
): Promise<MethodResult<M>>;
// String fallback: for unknown methods (status, monitor, etc.) or string-variable callers.
export function callBackendAPI<M extends string>(
  method: M,
  params?: JsonObject,
): Promise<unknown>;
export async function callBackendAPI(method: string, params: JsonObject = {}): Promise<unknown> {
  const requestId = `${Date.now()}-${Math.random()}`;
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.debug(`[trace ${requestId}] → ${method}`)
  }
  const request: BackendApiRequest = {
    id: requestId,
    method,
    params: toPlainParams(params) as JsonObject,
  };
  const resp = await callBackendByRequest(request);
  return unwrapBackendResponse(resp);
}
