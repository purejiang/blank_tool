import { createRouter, createWebHashHistory } from 'vue-router'
import ApkPage from '../views/ApkPage.vue'
import DevicePage from '../views/DevicePage.vue'
import SettingsPage from '../views/SettingsPage.vue'

const routes = [
  {
    path: '/',
    redirect: '/apk'
  },
  {
    path: '/apk',
    name: 'apk',
    component: ApkPage,
    meta: {
      title: 'APK工具',
      icon: '📦'
    }
  },
  {
    path: '/device',
    name: 'device',
    component: DevicePage,
    meta: {
      title: '设备管理',
      icon: '📱'
    }
  },
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

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// 路由守卫
router.beforeEach((to, from, next) => {
  // 设置页面标题
  if (to.meta?.title) {
    document.title = `${to.meta.title} - Android开发工具`
  }
  next()
})

export default router