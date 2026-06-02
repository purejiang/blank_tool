import { createRouter, createWebHashHistory } from 'vue-router'
import routes from './modules/index'

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach((to, _from, next) => {
  const pageTitle = to.meta?.title as string | undefined
  document.title = pageTitle ? `${pageTitle} - Blank Tool` : 'Blank Tool'
  next()
})

export default router
