import type { RouteRecordRaw } from 'vue-router'

/**
 * 工作流模块（docs/08 §2.1）：一级页是**列表** `/workflows`，编辑器是二级页
 * `/workflows/editor/:name?`（`:name` 省略 = 新建空定义）。旧路由
 * `/workflow-editor` 保留为重定向，避免历史书签/文档链接失效。
 */
const workflowRoutes: RouteRecordRaw[] = [
  {
    path: '/workflows',
    name: 'workflows',
    component: () => import('@views/WorkflowsListPage.vue'),
    meta: { title: '工作流' },
  },
  {
    path: '/workflows/editor/:name?',
    name: 'workflow-editor',
    component: () => import('@views/WorkflowEditorPage.vue'),
    meta: { title: '工作流编辑器' },
  },
  {
    path: '/workflow-editor',
    redirect: '/workflows/editor',
  },
]

export default workflowRoutes
