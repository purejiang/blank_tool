import type { RouteRecordRaw } from 'vue-router'

/**
 * 工具模块（docs/08 §2.1 / §3-S6）：**三个页面**共用侧边栏的一个「工具」导航项，
 * 靠页面头右侧的区段切换跳转。不是同页 tab 面板——三者是三类不同对象
 * （工具描述符 / 运行时 / 插件清单），各自有独立的列表、工具栏与空态。
 */
const toolsRoutes: RouteRecordRaw[] = [
  {
    path: '/tools',
    name: 'tools',
    component: () => import('@views/ToolsPage.vue'),
    meta: { title: '工具' },
  },
  {
    path: '/tools/env',
    name: 'tools-env',
    component: () => import('@views/EnvsPage.vue'),
    meta: { title: '运行时' },
  },
  {
    path: '/tools/plugins',
    name: 'tools-plugins',
    component: () => import('@views/PluginsPage.vue'),
    meta: { title: '插件' },
  },
]

export default toolsRoutes
