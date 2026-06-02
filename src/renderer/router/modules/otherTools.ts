import OtherToolsPage from '@views/OtherToolsPage.vue'
import AboutPage from '@views/AboutPage.vue'

const otherToolsRoutes = [
  {
    path: '/plugins',
    name: 'plugins',
    component: OtherToolsPage,
    meta: {
      title: '其他工具',
      icon: '🛠️'
    }
  },
  {
    path: '/about',
    name: 'about',
    component: AboutPage,
    meta: {
      title: '关于',
      icon: 'ℹ️'
    }
  }
]

export default otherToolsRoutes
