/**
 * Return `value` when it is a non-empty (after trim) string, otherwise
 * `fallback`. Used for reading electron-store values that may be missing,
 * blank, or of the wrong type.
 */
export function toNonEmptyString(value: unknown, fallback: string): string {
  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }
  return fallback;
}
