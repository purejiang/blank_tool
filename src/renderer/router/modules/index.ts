import settingsRoutes from './settings'
import workflowRoutes from './workflow'
import toolsRoutes from './tools'

const routes = [
  {
    path: '/',
    redirect: '/workflow-editor'
  },
  ...workflowRoutes,
  ...settingsRoutes,
  ...toolsRoutes
]

export default routes
