import SettingsPage from '@views/SettingsPage.vue'

const settingsRoutes = [
  {
    path: '/settings',
    name: 'settings',
    component: SettingsPage,
    meta: {
      title: '设置',
      icon: '⚙️'
    }
  }
]

export default settingsRoutes