import apkRoutes from './apk.js'
import deviceRoutes from './device.js'
import settingsRoutes from './settings.js'
import testRoutes from './test.js'

const routes = [
  {
    path: '/',
    redirect: '/apk'
  },
  ...apkRoutes,
  ...deviceRoutes,
  ...settingsRoutes,
  ...testRoutes
]

export default routes
