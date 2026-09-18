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

/**
 * One cached matcher per attribute name.
 *
 * `attr` used to build a fresh `RegExp` on EVERY call, and `parseUiDump` calls
 * it ~9× per node — compiling tens of thousands of regexes for a large dump
 * (the whole reason the picker felt slow on dense screens).
 */
const ATTR_RES = new Map<string, RegExp>()

function attrRe(name: string): RegExp {
  let re = ATTR_RES.get(name)
  if (!re) {
    re = new RegExp(`${name}="([^"]*)"`)
    ATTR_RES.set(name, re)
  }
  return re
}

export function attr(tag: string, name: string): string {
  const m = attrRe(name).exec(tag)
  return m ? m[1] : ''
}

/** Single-pass attribute scan of one `<node ...>` tag: `name → value`. */
const TAG_ATTR_RE = /([\w:.-]+)="([^"]*)"/g

function tagAttrs(tag: string): Record<string, string> {
  const out: Record<string, string> = {}
  // The regex is SHARED and stateful (`/g`) — reset lastIndex before reuse.
  // No awaits in this module, so no interleaving is possible.
  TAG_ATTR_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = TAG_ATTR_RE.exec(tag)) !== null) out[m[1]] = m[2]
  return out
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
  // ONE attribute scan per tag, reused by both passes below (`attr` would
  // re-scan the same tag for every attribute it reads).
  const attrs = openTags.map(tagAttrs)
  // First pass: extract the identifying attrs of every node in the dump,
  // so match counts reflect the full tree (not just the kept subset).
  const all = attrs.map((a) => ({
    text: a['text'] || '',
    rid: a['resource-id'] || '',
    desc: a['content-desc'] || '',
    cls: a['class'] || '',
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
  for (const a of attrs) {
    const text = a['text'] || ''
    const rid = a['resource-id'] || ''
    const desc = a['content-desc'] || ''
    const cls = a['class'] || ''
    const bounds = a['bounds'] || ''
    const clickable = a['clickable'] === 'true'
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
