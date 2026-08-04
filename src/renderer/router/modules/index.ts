import settingsRoutes from './settings'
import workflowRoutes from './workflow'

const routes = [
  {
    path: '/',
    redirect: '/workflow-editor'
  },
  ...workflowRoutes,
  ...settingsRoutes
]

export default routes
