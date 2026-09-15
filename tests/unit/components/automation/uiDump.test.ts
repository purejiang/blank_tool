/**
 * Unit tests for the uiautomator dump parser (`parseUiDump`), focused on
 * editable (input) nodes:
 *  - `editable` flag is class-based (EditText / AutoCompleteTextView / SearchView).
 *  - Editable nodes prefer `resource_id` over `text`: the `text` of an input
 *    is its placeholder and is replaced by the typed value at replay time,
 *    so a text locator goes stale the moment the user types.
 *  - Non-editable nodes keep the text > rid > desc > class priority.
 *  - An empty, id-less, non-clickable input is still kept (not filtered out).
 */
import { describe, it, expect } from 'vitest'
import { parseUiDump } from '@/renderer/components/automation/uiDump'

describe('parseUiDump editable nodes', () => {
  it('EditText with resource-id: editable=true and locator prefers resource_id', () => {
    const xml =
      '<node index="3" text="请输入手机号/账号" resource-id="com.lyj.gdt012:id/ln5_login_accout_edt" class="android.widget.EditText" content-desc="" clickable="true" bounds="[504,275][1095,354]" />'
    const [node] = parseUiDump(xml)
    expect(node.editable).toBe(true)
    expect(node.by).toBe('resource_id')
    expect(node.value).toBe('com.lyj.gdt012:id/ln5_login_accout_edt')
    // label keeps the placeholder text — it is the human-readable hint
    expect(node.label).toBe('请输入手机号/账号')
  })

  it('EditText without resource-id but with placeholder: falls back to text locator', () => {
    const xml =
      '<node index="1" text="请输入密码" resource-id="" class="android.widget.EditText" content-desc="" clickable="true" bounds="[0,0][100,40]" />'
    const [node] = parseUiDump(xml)
    expect(node.editable).toBe(true)
    expect(node.by).toBe('text')
    expect(node.value).toBe('请输入密码')
  })

  it('empty id-less non-clickable EditText is kept, not filtered out', () => {
    const xml =
      '<node index="2" text="" resource-id="" class="android.widget.EditText" content-desc="" clickable="false" bounds="[0,0][100,40]" />'
    const nodes = parseUiDump(xml)
    expect(nodes).toHaveLength(1)
    expect(nodes[0].editable).toBe(true)
    expect(nodes[0].by).toBe('class')
    expect(nodes[0].value).toBe('android.widget.EditText')
  })

  it('TextView/Button stay non-editable with the unchanged text-first priority', () => {
    const xml =
      '<node index="0" text="登录" resource-id="com.app:id/btn_login" class="android.widget.Button" content-desc="" clickable="true" bounds="[0,0][200,60]" />' +
      '<node index="1" text="用户协议" resource-id="com.app:id/tv_terms" class="android.widget.TextView" content-desc="" clickable="false" bounds="[0,0][100,30]" />'
    const [btn, tv] = parseUiDump(xml)
    expect(btn.editable).toBe(false)
    expect(btn.by).toBe('text')
    expect(btn.value).toBe('登录')
    expect(tv.editable).toBe(false)
    expect(tv.by).toBe('text')
    expect(tv.value).toBe('用户协议')
  })

  it('matchCount is recomputed against the new resource_id locator, not the shared placeholder text', () => {
    // Same placeholder on a static TextView and the input; the rid is unique.
    const xml =
      '<node index="0" text="请输入手机号/账号" resource-id="com.app:id/tv_hint" class="android.widget.TextView" content-desc="" clickable="false" bounds="[0,0][100,30]" />' +
      '<node index="3" text="请输入手机号/账号" resource-id="com.lyj.gdt012:id/ln5_login_accout_edt" class="android.widget.EditText" content-desc="" clickable="true" bounds="[504,275][1095,354]" />'
    const [, input] = parseUiDump(xml)
    expect(input.editable).toBe(true)
    expect(input.by).toBe('resource_id')
    expect(input.matchCount).toBe(1)
  })
})
