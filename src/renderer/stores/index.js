import { useAppConfigStore } from './appConfigStore'
import { useDeviceStore } from './deviceStore'
import { useToolStore } from './toolStore'
import { useSystemStore } from './systemStore'

// 配置初始化函数
export const initializeStores = async () => {
  const appConfigStore = useAppConfigStore()
  const deviceStore = useDeviceStore()
  const toolStore = useToolStore()
  const systemStore = useSystemStore()
  
  await Promise.all([
    appConfigStore.initialize()
  ])
  
  return { 
    appConfigStore, 
    deviceStore,
    toolStore,
    systemStore
  }
}

export { useAppConfigStore, useDeviceStore, useToolStore, useSystemStore }
