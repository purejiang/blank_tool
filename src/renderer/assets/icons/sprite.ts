/**
 * 图标 sprite（唯一来源）
 * --------------------------------------------------------------------------
 * 口径来自设计契约 docs/ui-prompts/ui-preview.html —— 它在 §2 用一套手写的
 * inline `<svg><symbol>` sprite，24×24、stroke 1.8、round cap/join，配合
 * `<use href="#i-xxx">` 引用。本项目此前用的是 lucide-vue-next，两套图标风格
 * 不统一，这里整体切到设计契约这一套。
 *
 * 组成：
 *   - 前 29 个（wf…clip）**逐字照搬**预览稿 sprite，路径不做任何改动；
 *   - 后 20 个（home…folder-in）是预览稿没有、但本地页面需要的，按同一画法补画
 *     （24×24 画布、同样只用 stroke、line cap/join 由 AppIcon 统一给）。
 *     补画时刻意避开了预览稿已用的形状语义，避免"两个图标长得一样"。
 *
 * 用法：main.ts 里调一次 installIconSprite()，之后用 <AppIcon name="refresh" /> 引用。
 * 不要直接写 <use href="#i-...">，否则尺寸/描边会绕开组件约定。
 */

export const ICON_SYMBOLS = `
<symbol id="i-wf" viewBox="0 0 24 24"><circle cx="6" cy="5" r="2.4"/><circle cx="6" cy="19" r="2.4"/><circle cx="18" cy="12" r="2.4"/><path d="M6 7.4v9.2M8.4 5H15a3 3 0 0 1 3 3v1.6M8.4 19H15a3 3 0 0 0 3-3v-1.6"/></symbol>
<symbol id="i-task" viewBox="0 0 24 24"><path d="M4 6h3M4 12h3M4 18h3M10 6h10M10 12h10M10 18h10"/></symbol>
<symbol id="i-tool" viewBox="0 0 24 24"><path d="M10 4h4v3.2a2 2 0 0 0 1 1.7l2.7 1.6a2 2 0 0 0 2 0l.3-.2v4l-.3-.2a2 2 0 0 0-2 0L15 15.1a2 2 0 0 0-1 1.7V20h-4v-3.2a2 2 0 0 0-1-1.7l-2.7-1.6a2 2 0 0 0-2 0l-.3.2v-4l.3.2a2 2 0 0 0 2 0L9 8.9a2 2 0 0 0 1-1.7z"/></symbol>
<symbol id="i-set" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1v.4a2 2 0 1 1-4 0v-.2a1.6 1.6 0 0 0-2.8-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3.5 14H3a2 2 0 1 1 0-4h.2A1.6 1.6 0 0 0 4.3 7.2l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 3.5V3a2 2 0 1 1 4 0v.2a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.6 1.6 0 0 0 20.5 10H21a2 2 0 1 1 0 4h-.2a1.6 1.6 0 0 0-1.4 1z"/></symbol>
<symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/></symbol>
<symbol id="i-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
<symbol id="i-up" viewBox="0 0 24 24"><path d="M12 19V5M6 11l6-6 6 6"/></symbol>
<symbol id="i-down" viewBox="0 0 24 24"><path d="M12 5v14M6 13l6 6 6-6"/></symbol>
<symbol id="i-refresh" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5"/></symbol>
<symbol id="i-back" viewBox="0 0 24 24"><path d="M15 19l-7-7 7-7"/></symbol>
<symbol id="i-x" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></symbol>
<symbol id="i-more" viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.4" fill="currentColor" stroke="none"/></symbol>
<symbol id="i-grip" viewBox="0 0 24 24"><circle cx="9" cy="6" r="1.3" fill="currentColor" stroke="none"/><circle cx="15" cy="6" r="1.3" fill="currentColor" stroke="none"/><circle cx="9" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="15" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="9" cy="18" r="1.3" fill="currentColor" stroke="none"/><circle cx="15" cy="18" r="1.3" fill="currentColor" stroke="none"/></symbol>
<symbol id="i-folder" viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h3.5l2 2.5H19a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></symbol>
<symbol id="i-file" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></symbol>
<symbol id="i-term" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 2.5 2.5L7 14M13 14h4"/></symbol>
<symbol id="i-globe" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18"/></symbol>
<symbol id="i-loop" viewBox="0 0 24 24"><path d="M17 2l3 3-3 3"/><path d="M20 5H8a5 5 0 0 0 0 10h8a5 5 0 0 1 0 10H5"/></symbol>
<symbol id="i-brace" viewBox="0 0 24 24"><path d="M9 4c-2 0-3 1-3 3v2c0 1.5-.7 2.3-2 3 1.3.7 2 1.5 2 3v2c0 2 1 3 3 3M15 4c2 0 3 1 3 3v2c0 1.5.7 2.3 2 3-1.3.7-2 1.5-2 3v2c0 2-1 3-3 3"/></symbol>
<symbol id="i-check" viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6"/></symbol>
<symbol id="i-alert" viewBox="0 0 24 24"><path d="M12 3.5 22 20H2z"/><path d="M12 10v4.5M12 17.5h.01"/></symbol>
<symbol id="i-play" viewBox="0 0 24 24"><path d="M7 4.5 19.5 12 7 19.5z"/></symbol>
<symbol id="i-trash" viewBox="0 0 24 24"><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/></symbol>
<symbol id="i-info" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></symbol>
<symbol id="i-activity" viewBox="0 0 24 24"><path d="M3 12h4l2.5-7 4 14 2.5-7h5"/></symbol>
<symbol id="i-device" viewBox="0 0 24 24"><rect x="5" y="2.5" width="14" height="19" rx="2.5"/><path d="M11 18.5h2"/></symbol>
<symbol id="i-pkg" viewBox="0 0 24 24"><path d="M12 2.8 21 7v10l-9 4.2L3 17V7z"/><path d="M3 7l9 4.2 9-4.2M12 21V11.2"/></symbol>
<symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5.2l3.4 2"/></symbol>
<symbol id="i-clip" viewBox="0 0 24 24"><path d="M4 5h16v14H4z"/><path d="M8 9h8M8 13h8M8 17h4"/></symbol>
<symbol id="i-home" viewBox="0 0 24 24"><path d="M4 10.6 12 3.8l8 6.8v8.1a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.7z"/><path d="M9.5 20.2v-5.6h5v5.6"/></symbol>
<symbol id="i-chevrons-l" viewBox="0 0 24 24"><path d="M12.5 7 7.5 12l5 5M18 7l-5 5 5 5"/></symbol>
<symbol id="i-chevrons-r" viewBox="0 0 24 24"><path d="M11.5 7l5 5-5 5M6 7l5 5-5 5"/></symbol>
<symbol id="i-arrow-r" viewBox="0 0 24 24"><path d="M4 12h15M13 6l6 6-6 6"/></symbol>
<symbol id="i-ban" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/></symbol>
<symbol id="i-spinner" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-6.2-8.6"/></symbol>
<symbol id="i-help" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9.3a2.6 2.6 0 1 1 3.6 2.4c-.7.3-1.1.8-1.1 1.6v.5"/><path d="M12 16.8h.01"/></symbol>
<symbol id="i-minus-circle" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M8 12h8"/></symbol>
<symbol id="i-x-circle" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M8.8 8.8l6.4 6.4M15.2 8.8l-6.4 6.4"/></symbol>
<symbol id="i-alert-circle" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16.4h.01"/></symbol>
<symbol id="i-dot" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="3.2" fill="currentColor" stroke="none"/></symbol>
<symbol id="i-pencil" viewBox="0 0 24 24"><path d="M16.8 3.7 20.3 7.2 8.5 19H5v-3.5z"/><path d="M14.2 6.3l3.5 3.5"/></symbol>
<symbol id="i-save" viewBox="0 0 24 24"><path d="M6 3h9l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M8 3v5h7V3"/><path d="M8 21v-6h8v6"/></symbol>
<symbol id="i-layers" viewBox="0 0 24 24"><path d="M12 3 20.5 7.5 12 12 3.5 7.5z"/><path d="M3.5 12.5 12 17l8.5-4.5"/><path d="M3.5 16.5 12 21l8.5-4.5"/></symbol>
<symbol id="i-cpu" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/><rect x="10" y="10" width="4" height="4" rx="1"/><path d="M9.5 3v3M14.5 3v3M9.5 18v3M14.5 18v3M3 9.5h3M3 14.5h3M18 9.5h3M18 14.5h3"/></symbol>
<symbol id="i-monitor" viewBox="0 0 24 24"><rect x="2.5" y="4" width="19" height="13" rx="2"/><path d="M9 21h6M12 17v4"/></symbol>
<symbol id="i-drive" viewBox="0 0 24 24"><path d="M5.6 5.2h12.8L21 12v6a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18v-6z"/><path d="M3 12h18"/><path d="M7 15.6h.01M10.5 15.6h.01"/></symbol>
<symbol id="i-archive" viewBox="0 0 24 24"><rect x="2.5" y="3.5" width="19" height="5" rx="1.5"/><path d="M4.5 8.5V19a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5V8.5"/><path d="M10 12.5h4"/></symbol>
<symbol id="i-download" viewBox="0 0 24 24"><path d="M12 3v12M6 9l6 6 6-6"/><path d="M4 17v2.5A1.5 1.5 0 0 0 5.5 21h13a1.5 1.5 0 0 0 1.5-1.5V17"/></symbol>
<symbol id="i-folder-in" viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h3.5l2 2.5H19a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 10.2v4.2M9.8 12.4 12 14.6l2.2-2.2"/></symbol>
`

export const ICON_SPRITE_ID = 'app-icon-sprite'

/**
 * 把 sprite 注入 <body>（幂等）。必须在 app.mount() 之前调用，
 * 否则首帧的 `<use>` 找不到目标会闪一下空白。
 */
export function installIconSprite(): void {
  if (typeof document === 'undefined') return
  if (document.getElementById(ICON_SPRITE_ID)) return

  const holder = document.createElement('div')
  holder.id = ICON_SPRITE_ID
  holder.setAttribute('aria-hidden', 'true')
  holder.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden'
  holder.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg">${ICON_SYMBOLS}</svg>`
  document.body.appendChild(holder)
}
