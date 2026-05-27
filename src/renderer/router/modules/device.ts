import DevicePage from '@views/DevicePage.vue'

const deviceRoutes = [
  {
    path: '/device',
    name: 'device',
    component: DevicePage,
    meta: {
      title: '设备管理',
      icon: '📱'
    }
  }
]

export default deviceRoutes
