import type { RouteRecordRaw } from 'vue-router'

/**
 * 首页（一级，`/`）。概览 + 快捷入口 + 最近运行 + 系统状态，
 * 数据来自 template.list / task.list / history.list / workflow.list_tools / env.list。
 */
const homeRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@views/HomePage.vue'),
    meta: { title: '首页' },
  },
]

export default homeRoutes
