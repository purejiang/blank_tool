import type { RouteRecordRaw } from 'vue-router'

/**
 * 任务模块（docs/08 §2.1）：`/tasks` 是任务中心（默认 tab「任务」，
 * `?tab=runs` 为「运行记录」），`/tasks/editor/:name?` 是任务编辑的**唯一入口**
 * （新建 = 无 name）。
 */
const taskRoutes: RouteRecordRaw[] = [
  {
    path: '/tasks',
    name: 'tasks',
    component: () => import('@views/TasksPage.vue'),
    meta: { title: '任务' },
  },
  {
    path: '/tasks/editor/:name?',
    name: 'task-editor',
    component: () => import('@views/TaskEditorPage.vue'),
    meta: { title: '任务编辑' },
  },
]

export default taskRoutes
