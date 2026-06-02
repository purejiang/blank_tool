import OtherToolsPage from '@views/OtherToolsPage.vue'
import AboutPage from '@views/AboutPage.vue'

const otherToolsRoutes = [
  {
    path: '/plugins',
    name: 'plugins',
    component: OtherToolsPage,
  },
  {
    path: '/about',
    name: 'about',
    component: AboutPage,
  }
]

export default otherToolsRoutes
