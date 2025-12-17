import packageRoutes from './package.js'
import deviceRoutes from './device.js'
import settingsRoutes from './settings.js'
import otherToolsRoutes from './otherTools.js'

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
