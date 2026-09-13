/**
 * Byte-size formatting.
 *
 * Replaces three divergent copies (ApkService / systemStore / SettingsPage)
 * that disagreed on the unit list and on trailing zeros — the same 1048576
 * bytes rendered as `1 MB` in one place and `1.00 MB` in another, and ApkService
 * simply had no TB unit. The canonical form is the one ApkService's contract
 * test locks in:
 *
 *   formatBytes(0)       -> '0 B'
 *   formatBytes(1024)    -> '1 KB'
 *   formatBytes(1048576) -> '1 MB'
 */
const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const

export function formatBytes(bytes: number): string {
  // Guards the log(0) = -Infinity trap and any non-numeric input coming back
  // from the backend (cache sizes, memory totals) instead of emitting 'NaN B'.
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'

  const exponent = Math.floor(Math.log(bytes) / Math.log(1024))
  // Clamp so a petabyte-scale value yields 'TB' rather than 'undefined'.
  const unit = Math.min(exponent, BYTE_UNITS.length - 1)

  return `${parseFloat((bytes / Math.pow(1024, unit)).toFixed(2))} ${BYTE_UNITS[unit]}`
}
