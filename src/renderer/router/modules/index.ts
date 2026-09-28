import settingsRoutes from './settings'
import workflowRoutes from './workflow'
import tasksRoutes from './tasks'
import toolsRoutes from './tools'

const routes = [
  {
    path: '/',
    // docs/08 §2.1: `/` 重定向到工作流列表（一级页），编辑器是二级页。
    redirect: '/workflows',
  },
  ...workflowRoutes,
  ...tasksRoutes,
  ...settingsRoutes,
  ...toolsRoutes,
]

export default routes
