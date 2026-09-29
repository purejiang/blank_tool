import homeRoutes from './home'
import settingsRoutes from './settings'
import workflowRoutes from './workflow'
import tasksRoutes from './tasks'
import toolsRoutes from './tools'

/**
 * 一级模块（docs/08 §2.1 / 本次设计系统）：
 *   首页 `/`、工作流 `/workflows`（编辑器为二级页）、任务 `/tasks`、
 *   工具 `/tools`（运行时 `/tools/env`、插件 `/tools/plugins` 为同模块三页）、
 *   设置 `/settings`。`/about`、`/diagnostics` 是不进导航的二级路由。
 */
const routes = [...homeRoutes, ...workflowRoutes, ...tasksRoutes, ...settingsRoutes, ...toolsRoutes]

export default routes
