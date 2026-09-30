import type { RouteRecordRaw } from 'vue-router'

/**
 * 任务模块（docs/08 §2.1）：`/tasks` 是任务中心（默认 tab「任务」，
 * `?tab=runs` 为「运行记录」），`/tasks/editor/:ref?` 是任务编辑的**唯一入口**
 * （`:ref` 是任务 id；历史上是任务名，后端仍能按名字解析。新建 = 无 ref）。
 */
const taskRoutes: RouteRecordRaw[] = [
  {
    path: '/tasks',
    name: 'tasks',
    component: () => import('@views/TasksPage.vue'),
    meta: { title: '任务' },
  },
  {
    path: '/tasks/editor/:ref?',
    name: 'task-editor',
    component: () => import('@views/TaskEditorPage.vue'),
    meta: { title: '任务编辑' },
  },
]

export default taskRoutes
