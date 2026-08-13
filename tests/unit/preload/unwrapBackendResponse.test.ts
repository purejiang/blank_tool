import { describe, it, expect } from 'vitest';
import { BackendError } from '../../../src/shared/errors';
import { unwrapBackendResponse } from '../../../src/preload/core/unwrapBackendResponse';

describe('unwrapBackendResponse', () => {
  it('returns payload on success', () => {
    const result = unwrapBackendResponse({ result: { type: 'success', payload: { foo: 1 } } });
    expect(result).toEqual({ foo: 1 });
  });

  it('throws BackendError with code on error', () => {
    expect(() =>
      unwrapBackendResponse({ result: { type: 'error', payload: { code: -32001, message: 'backend down' } } })
    ).toThrowError(/backend down/);

    try {
      unwrapBackendResponse({ result: { type: 'error', payload: { code: -32001, message: 'backend down' } } });
      throw new Error('should have thrown');
    } catch (e) {
      expect(e).toBeInstanceOf(BackendError);
      expect((e as BackendError).code).toBe(-32001);
      expect((e as BackendError).message).toBe('backend down');
    }
  });

  it('defaults code to -32603 when missing', () => {
    try {
      unwrapBackendResponse({ result: { type: 'error', payload: { message: 'X' } } });
      throw new Error('should have thrown');
    } catch (e) {
      expect(e).toBeInstanceOf(BackendError);
      expect((e as BackendError).code).toBe(-32603);
    }
  });

  it('handles unwrapped result (no outer { result } envelope)', () => {
    expect(unwrapBackendResponse({ type: 'success', payload: 42 })).toBe(42);
  });
});
