import { createRouter, createWebHashHistory } from 'vue-router'
import routes from './modules/index'

const router = createRouter({
  history: createWebHashHistory(),
  // 二级路由（/about、/diagnostics）在 modules/settings.ts 里声明一次即可——
  // 这里曾重复声明 /diagnostics，已清理（docs/08 §2.1）。
  routes: [...routes],
})

router.beforeEach((to, _from, next) => {
  const pageTitle = to.meta?.title as string | undefined
  document.title = pageTitle ? `${pageTitle} - Blank Tool` : 'Blank Tool'
  next()
})

export default router
