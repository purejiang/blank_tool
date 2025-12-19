import { useAppConfigStore } from './appConfigStore'
import { useUserConfigStore } from './userConfigStore'
import { useDeviceStore } from './deviceStore'
import { useToolStore } from './toolStore'
import { useSystemStore } from './systemStore'

// 配置初始化函数
export const initializeStores = async () => {
  const appConfigStore = useAppConfigStore()
  const userConfigStore = useUserConfigStore()
  const deviceStore = useDeviceStore()
  const toolStore = useToolStore()
  const systemStore = useSystemStore()
  
  await Promise.all([
    appConfigStore.initialize(),
    userConfigStore.initialize()
  ])
  
  return { 
    appConfigStore, 
    userConfigStore, 
    deviceStore,
    toolStore,
    systemStore
  }
}

export { useAppConfigStore, useUserConfigStore, useDeviceStore, useToolStore, useSystemStore }
