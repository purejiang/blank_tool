import { useAppConfigStore } from './appConfigStore'
import { useToolStore } from './toolStore'
import { useSystemStore } from './systemStore'

// 配置初始化函数
export const initializeStores = async () => {
  const appConfigStore = useAppConfigStore()
  const toolStore = useToolStore()
  const systemStore = useSystemStore()
  
  await Promise.all([
    appConfigStore.initialize()
  ])
  
  return { 
    appConfigStore, 
    toolStore,
    systemStore
  }
}

export { useAppConfigStore, useToolStore, useSystemStore }
// 遗留的 `taskStore`（PackagePage 时代的运行跟踪状态）已随退役方法清理删除：
// 它曾是"不暴露"方法 `task.append_log` / `task.delete_task_dir` 的唯一调用方，
// 而任务模块现在直接用 `task.*` 任务定义接口（docs/08 §3-S3）。
export { useUpdateStore } from './updateStore'
