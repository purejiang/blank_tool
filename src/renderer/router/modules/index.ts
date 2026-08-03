import packageRoutes from './package'
import deviceRoutes from './device'
import settingsRoutes from './settings'
import otherToolsRoutes from './otherTools'
import workflowRoutes from './workflow'

const routes = [
  {
    path: '/',
    redirect: '/package'
  },
  ...packageRoutes,
  ...deviceRoutes,
  ...otherToolsRoutes,
  ...workflowRoutes,
  ...settingsRoutes
]

export default routes
