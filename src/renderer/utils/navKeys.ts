/**
 * 左侧导航（tablist）的键盘操作。
 *
 * 设置页和运行配置弹窗的左栏都是「一组 tab + 一个当前项」的形态，之前只有点击：
 * 键盘用户既聚焦不到、也切不了。这里把标准 tablist 行为集中成一个小工具：
 *
 *   ArrowDown / ArrowRight  下一项（末尾回到第一项）
 *   ArrowUp   / ArrowLeft   上一项（第一项回到末项）
 *   Home / End              第一项 / 最后一项
 *   Enter / Space           选中当前项
 *
 * 方向键按「选中即切换」处理（自动激活），并把焦点移到新选中的那一项 —— 配合
 * roving tabindex（只有 active 项 tabindex=0）就是标准的 tab 键盘模型。
 * 事件绑在每一项上，所以焦点定位用 currentTarget 的父节点 + 下标推算。
 */
export function handleNavKeydown(
  event: KeyboardEvent,
  keys: readonly string[],
  current: string,
  onSelect: (key: string) => void,
): void {
  if (!keys.length) return
  const index = keys.indexOf(current)
  const from = index >= 0 ? index : 0
  let next = -1

  switch (event.key) {
    case 'ArrowDown':
    case 'ArrowRight':
      next = (from + 1) % keys.length
      break
    case 'ArrowUp':
    case 'ArrowLeft':
      next = (from - 1 + keys.length) % keys.length
      break
    case 'Home':
      next = 0
      break
    case 'End':
      next = keys.length - 1
      break
    case 'Enter':
    case ' ':
      event.preventDefault()
      onSelect(keys[from])
      return
    default:
      return
  }

  event.preventDefault()
  onSelect(keys[next])
  focusSibling(event.currentTarget, next)
}

/** 把焦点移到同一个导航容器里的第 index 项（DOM 顺序与 keys 顺序一致）。 */
function focusSibling(target: EventTarget | null, index: number): void {
  const el = target as HTMLElement | null
  const parent = el?.parentElement
  const items = parent?.querySelectorAll<HTMLElement>('[role="tab"]')
  items?.[index]?.focus()
}
