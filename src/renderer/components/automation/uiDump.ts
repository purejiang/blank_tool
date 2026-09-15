/**
 * uiautomator XML dump → element list, for the picker panel.
 *
 * Pure functions (no Vue/backend deps) so they can be unit-tested
 * standalone and reused by any picker UI.
 */

export interface UiNode {
  text: string
  resource_id: string
  content_desc: string
  class: string
  bounds: string
  by: string
  value: string
  clickable: boolean
  editable: boolean
  matchCount: number
  label: string
}

export function attr(tag: string, name: string): string {
  const m = tag.match(new RegExp(`${name}="([^"]*)"`))
  return m ? m[1] : ''
}

export function shortClass(cls: string): string {
  const i = cls.lastIndexOf('.')
  return i >= 0 ? cls.slice(i + 1) : cls
}

/**
 * Editable text widgets: the user types into them, so their `text`
 * (placeholder / typed value) changes over time and is NOT a stable locator.
 * Matched by class substring — do NOT widen to `focusable` (containers are
 * focusable too and would flood the list).
 */
export function isEditableClass(cls: string): boolean {
  return /EditText|AutoCompleteTextView|SearchView/.test(cls)
}

export function boundsCenter(bounds: string): { x: number; y: number } | null {
  const m = /\[(\d+),(\d+)\]\[(\d+),(\d+)\]/.exec(bounds || '')
  if (!m) return null
  return {
    x: Math.round((Number(m[1]) + Number(m[3])) / 2),
    y: Math.round((Number(m[2]) + Number(m[4])) / 2),
  }
}

export function parseUiDump(xml: string): UiNode[] {
  if (!xml) return []
  const openTags = xml.match(/<node[^>]*>/g) || []
  // First pass: extract the identifying attrs of every node in the dump,
  // so match counts reflect the full tree (not just the kept subset).
  const all = openTags.map((tag) => ({
    text: attr(tag, 'text'),
    rid: attr(tag, 'resource-id'),
    desc: attr(tag, 'content-desc'),
    cls: attr(tag, 'class'),
  }))
  // Mirrors the backend matcher: substring match on the same attribute.
  const countMatches = (by: string, value: string): number => {
    if (!value) return 0
    let n = 0
    for (const t of all) {
      const v =
        by === 'text' ? t.text : by === 'resource_id' ? t.rid : by === 'content_desc' ? t.desc : t.cls
      if (v && v.includes(value)) n++
    }
    return n
  }
  const nodes: UiNode[] = []
  for (const tag of openTags) {
    const text = attr(tag, 'text')
    const rid = attr(tag, 'resource-id')
    const desc = attr(tag, 'content-desc')
    const cls = attr(tag, 'class')
    const bounds = attr(tag, 'bounds')
    const clickable = attr(tag, 'clickable') === 'true'
    const editable = isEditableClass(cls)
    // Keep nodes identifiable by text/rid/desc, plus clickable widgets
    // (icon-only buttons etc.) which are located by class substring, plus
    // editable boxes — an untouched, id-less input has none of the above
    // and would otherwise be invisible in the picker.
    if (!text && !rid && !desc && !clickable && !editable) continue
    let by = ''
    let value = ''
    if (editable) {
      // The `text` of an input is its placeholder and becomes the typed
      // value at replay time — prefer the stable resource-id when present.
      if (rid) {
        by = 'resource_id'
        value = rid
      } else if (text) {
        by = 'text'
        value = text
      } else if (desc) {
        by = 'content_desc'
        value = desc
      } else {
        by = 'class'
        value = cls
      }
    } else if (text) {
      by = 'text'
      value = text
    } else if (rid) {
      by = 'resource_id'
      value = rid
    } else if (desc) {
      by = 'content_desc'
      value = desc
    } else {
      by = 'class'
      value = cls
    }
    nodes.push({
      text,
      resource_id: rid,
      content_desc: desc,
      class: cls,
      bounds,
      by,
      value,
      clickable,
      editable,
      matchCount: countMatches(by, value),
      label: text || rid || desc || shortClass(cls),
    })
  }
  return nodes
}
