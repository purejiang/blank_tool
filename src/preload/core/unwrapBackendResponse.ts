import { BackendError } from '../../shared/errors';

type BackendResult = { type: 'success'; payload: unknown } | { type: 'error'; payload: { code?: number; message: string } };

export const unwrapBackendResponse = (raw: unknown): unknown => {
  const result = (raw && typeof raw === 'object' && 'result' in raw ? (raw as { result: BackendResult }).result : raw) as BackendResult;
  if (!result || typeof result !== 'object' || !result.type) return undefined; // streaming init response (no type field)
  if (result.type === 'success') return result.payload;
  if (result.type === 'error') {
    const code = result.payload?.code ?? -32603;
    throw new BackendError(result.payload?.message ?? 'Unknown backend error', code);
  }
  // Any other typed envelope (log / complete / started / record_event / …)
  // is a streaming event that raced ahead of the init response and became
  // the invoke's resolved value — it is NOT an error, return it untouched.
  return result;
};
