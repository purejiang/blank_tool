import { app } from 'electron'
import path from 'path'
import { existsSync, mkdirSync } from 'fs'

const APP_DIR_NAME = 'blank_tool'

/**
 * 获取应用本地数据目录 (机器专属，不应随用户账号漫游)
 *
 * Windows:  %LOCALAPPDATA%\blank_tool\
 * macOS:    ~/Library/Caches/blank_tool/
 * Linux:    ~/.cache/blank_tool/
 *
 * 适用于：缓存、输出文件、下载文件等大容量或机器专属数据
 */
export function getAppLocalDataPath(): string {
  if (process.platform === 'win32') {
    const localAppData = process.env.LOCALAPPDATA || path.join(app.getPath('home'), 'AppData', 'Local')
    return path.join(localAppData, APP_DIR_NAME)
  }
  if (process.platform === 'darwin') {
    return path.join(app.getPath('home'), 'Library', 'Caches', APP_DIR_NAME)
  }
  // Linux
  return path.join(app.getPath('home'), '.cache', APP_DIR_NAME)
}

/**
 * 获取应用漫游数据目录 (跟随用户账号漫游)
 * 即 Electron 内置的 userData 路径
 *
 * Windows:  %APPDATA%\blank_tool\
 * macOS:    ~/Library/Application Support/blank_tool/
 * Linux:    ~/.config/blank_tool/
 *
 * 适用于：用户配置、偏好设置等小容量且需漫游的数据
 */
export function getAppRoamingDataPath(): string {
  return app.getPath('userData')
}

/**
 * 确保指定目录存在（递归创建）
 */
export function ensureDir(dirPath: string): void {
  if (!existsSync(dirPath)) {
    mkdirSync(dirPath, { recursive: true })
  }
}

/**
 * 基于应用根目录解析相对路径：dev 用项目根 (app.getAppPath())，打包后用 process.resourcesPath。
 * 与 src/main/python/paths.ts 的 getBaseDir() 用途不同（后者解析运行时/服务端根目录），保持独立。
 */
export function resolveFromAppBase(relativePath: string): string {
  if (!relativePath) {
    return relativePath
  }
  // 绝对路径原样返回
  if (path.isAbsolute(relativePath)) {
    return relativePath
  }
  const baseDir = app.isPackaged ? process.resourcesPath : app.getAppPath()
  // 移除开头的 .\ 或 ./
  const stripped = relativePath.replace(/^[.][/\\\\]+/, '')
  return path.join(baseDir, stripped)
}
