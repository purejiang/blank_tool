import PackagePage from '@views/PackagePage.vue'

const apkRoutes = [
  {
    path: '/apk',
    name: 'apk',
    component: PackagePage,
    meta: {
      title: '包体工具',
      icon: '📦'
    }
  }
]

export default apkRoutes