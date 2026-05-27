import PackagePage from '@views/PackagePage.vue'

const packageRoutes = [
  {
    path: '/package',
    name: 'package',
    component: PackagePage,
    meta: {
      title: '包体工具',
      icon: '📦'
    }
  }
]

export default packageRoutes
