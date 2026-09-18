/**
 * Random id generation.
 *
 * Replaces five near-identical copies of the `crypto.randomUUID()` + fallback
 * pattern. Besides the duplication they were mutually inconsistent: the primary
 * path returned a *bare* UUID while the fallback returned a prefixed one
 * (`id-…`, `pl-…`, `step-…`), so the shape of an id depended on whether
 * `randomUUID` happened to exist. `RecordingService` used the bare call with no
 * guard at all, which throws outside a secure context.
 *
 * @param prefix Optional prefix, e.g. `genId('rec')` -> `rec-<uuid>`.
 */
export function genId(prefix?: string): string {
  // `crypto.randomUUID` is missing in non-secure contexts (plain http://),
  // hence the timestamp+entropy fallback.
  let id: string | undefined
  try {
    id = (crypto as { randomUUID?: () => string }).randomUUID?.()
  } catch {
    id = undefined
  }
  if (!id) id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

  return prefix ? `${prefix}-${id}` : id
}
