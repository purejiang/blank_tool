import type { RouteRecordRaw } from 'vue-router'

const workflowRoutes: RouteRecordRaw[] = [
  {
    path: '/workflow-editor',
    name: 'workflow-editor',
    component: () => import('@views/WorkflowEditorPage.vue'),
    meta: { title: 'Workflow Editor' },
  },
]

export default workflowRoutes
