/**
 * 一级导航项（侧边栏与底部 Tab 共用一份定义）。
 *
 * 路由约定（docs/08 §2.1）：首页 `/`、工作流 `/workflows`、任务 `/tasks`、
 * 工具 `/tools`、设置 `/settings`。二级页（`/workflows/editor/x` 等）按
 * **路径前缀**点亮所属模块。
 */

export interface NavItem {
  key: string
  labelKey: string
  icon: string
}

export const NAV_ITEMS: NavItem[] = [
  { key: '/', labelKey: 'nav.home', icon: 'home' },
  { key: '/workflows', labelKey: 'nav.workflows', icon: 'wf' },
  { key: '/tasks', labelKey: 'nav.tasks', icon: 'task' },
  { key: '/tools', labelKey: 'nav.tools', icon: 'tool' },
  { key: '/settings', labelKey: 'nav.settings', icon: 'set' },
]

/** 当前路径属于哪个一级模块（用于 aria-current 与高亮）。 */
export function activeNavKey(path: string): string {
  if (path === '/' || path === '') return '/'
  const match = NAV_ITEMS.find((item) => item.key !== '/' && (path === item.key || path.startsWith(`${item.key}/`)))
  return match?.key ?? ''
}
