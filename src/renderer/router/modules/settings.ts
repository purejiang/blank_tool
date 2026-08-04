import SettingsPage from '@views/SettingsPage.vue'
import AboutPage from '@views/AboutPage.vue'
import DiagnosticsPage from '@views/DiagnosticsPage.vue'

const settingsRoutes = [
  {
    path: '/settings',
    name: 'settings',
    component: SettingsPage,
  },
  {
    path: '/about',
    name: 'about',
    component: AboutPage,
  },
  {
    path: '/diagnostics',
    name: 'diagnostics',
    component: DiagnosticsPage,
  }
]

export default settingsRoutes
