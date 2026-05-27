import { createRouter, createWebHashHistory } from 'vue-router'
import routes from './modules/index'

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// 路由守卫
router.beforeEach((to, from, next) => {
  // 设置页面标题
  const baseTitle = 'Blank Tool'
  const pageTitle = to.meta?.title || baseTitle
  document.title = `${pageTitle} - ${baseTitle}`
  next()
})

export default router
