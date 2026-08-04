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
export { useTaskStore } from './taskStore'
export { useUpdateStore } from './updateStore'
