import serviceManager from './ServiceManager'
import { ConfigService } from './ConfigService'
import NotificationService from './NotificationService'
import DeviceService from './DeviceService'
import { ThemeService } from './ThemeService'
import ToolService from './ToolService'
import ErrorService from './ErrorService'
import SystemService from './SystemService'
import ApkService from './ApkService'
import CacheService from './CacheService'
import StoreService from './StoreService'
import SettingsService from './SettingsService'
import UpdateService from './UpdateService'
import TaskStreamService from './TaskStreamService'

export function registerServices(sm: typeof serviceManager = serviceManager): void {
  sm.register('config', ConfigService)
  sm.register('notification', NotificationService)
  sm.register('device', DeviceService)
  sm.register('theme', ThemeService)
  sm.register('tools', ToolService, ['config'])
  sm.register('error', ErrorService, ['notification'])
  sm.register('system', SystemService)
  sm.register('apk', ApkService, ['config'])
  sm.register('cache', CacheService, ['config'])
  sm.register('store', StoreService)
  sm.register('settings', SettingsService, ['store'])
  sm.register('update', UpdateService)
  sm.register('taskStream', TaskStreamService)
}
