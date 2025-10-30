import { useAppConfigStore } from './appConfigStore'
import { useUserConfigStore } from './userConfigStore'
import { useDeviceStore } from './deviceStore'

// 配置初始化函数
export const initializeStores = async () => {
  const appConfigStore = useAppConfigStore()
  const userConfigStore = useUserConfigStore()
  const deviceStore = useDeviceStore()
  
  await Promise.all([
    appConfigStore.initialize(),
    userConfigStore.initialize()
  ])
  
  return { appConfigStore, userConfigStore, deviceStore }
}

export { useAppConfigStore, useUserConfigStore, useDeviceStore }
