import packageRoutes from './package'
import deviceRoutes from './device'
import settingsRoutes from './settings'
import otherToolsRoutes from './otherTools'

const routes = [
  {
    path: '/',
    redirect: '/package'
  },
  ...packageRoutes,
  ...deviceRoutes,
  ...otherToolsRoutes,
  ...settingsRoutes
]

export default routes
