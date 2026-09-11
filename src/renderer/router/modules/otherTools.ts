import OtherToolsPage from '@views/OtherToolsPage.vue'
import PluginsPage from '@views/PluginsPage.vue'
import AboutPage from '@views/AboutPage.vue'

const otherToolsRoutes = [
  {
    // automation owns its own route — /plugins belongs to real plugins
    path: '/automation',
    name: 'automation',
    component: OtherToolsPage,
  },
  {
    path: '/plugins',
    name: 'plugins',
    component: PluginsPage,
  },
  {
    path: '/about',
    name: 'about',
    component: AboutPage,
  }
]

export default otherToolsRoutes
