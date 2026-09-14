/**
 * Read a text file through the Electron bridge.
 *
 * `electronAPI.readFile` hands back the RAW main-process envelope
 * `{ success: true, data: "…" }` (or `{ success: false, error }`) — not the
 * file contents. Spreading `String(res)` straight into a template (e.g. an
 * iframe `srcdoc`) renders the literal text `[object Object]`.
 *
 * Every caller that wants the *contents* must go through here.
 */
export async function readTextFile(filePath: string): Promise<string> {
  const api = (window as any).electronAPI
  if (!api || typeof api.readFile !== 'function') {
    throw new Error('electronAPI.readFile unavailable')
  }
  const res = await api.readFile(filePath)
  // tolerate a future flattening of the bridge (main returns plain text)
  if (typeof res === 'string') return res
  if (res && typeof res === 'object' && res.success === false) {
    throw new Error(String(res.error || 'read failed'))
  }
  const data = res?.data
  if (typeof data !== 'string') {
    throw new Error('readFile did not return text content')
  }
  return data
}

export default readTextFile
