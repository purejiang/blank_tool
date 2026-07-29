import log from 'electron-log'
import path from 'path'
import { getAppLocalDataPath } from './utils/appPaths'

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

// 配置日志 — 放在 LOCALAPPDATA，不随账号漫游；单文件上限 20MB
export function configureLogging(level: LogLevel = 'info'): void {
  log.transports.file.resolvePathFn = () => path.join(getAppLocalDataPath(), 'logs', 'electron.log')
  log.transports.file.maxSize = 20 * 1024 * 1024
  log.transports.file.level = level
  log.transports.console.level = level
  // 将 console 输出重定向到 electron-log
  Object.assign(console, log.functions)
}
