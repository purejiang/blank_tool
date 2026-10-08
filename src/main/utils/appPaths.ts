import { app } from 'electron'
import path from 'path'
import { existsSync, mkdirSync } from 'fs'
import { APP_NAME } from '../appIdentity'
import { getLocalDataOverride } from '../dataRoot'

/**
 * 获取应用本地数据目录 (机器专属，不应随用户账号漫游)
 *
 * Windows:  %LOCALAPPDATA%\blanks\
 * macOS:    ~/Library/Caches/blanks/
 * Linux:    ~/.cache/blanks/
 *
 * 目录名 = 应用名（`src/main/appIdentity.ts`）。应用从 Blank Tool 改名 Blanks 后，
 * 这里跟着换成 `blanks`，与历史的 `blank_tool` 目录**分开**：旧目录不做迁移、原样保留，
 * 新目录从零开始，避免新旧两种命名混写同一份数据。
 * 注意 userData（`%APPDATA%\blanks`，放 app-config.json 与渲染层 localStorage）
 * 由 `app.setName()` 决定，同样在 appIdentity.ts 里收口。
 *
 * 适用于：缓存、输出文件、下载文件等大容量或机器专属数据
 *
 * dev 模式例外：默认目录写不进去时 `dataRoot.ts` 会把数据根整体挪到工作区/临时目录，
 * 这里跟着返回那个覆盖值（非 dev、或默认目录可写时恒为 null，行为与以前一致）。
 */
export function getAppLocalDataPath(): string {
  const override = getLocalDataOverride()
  if (override) {
    return override
  }
  if (process.platform === 'win32') {
    const localAppData = process.env.LOCALAPPDATA || path.join(app.getPath('home'), 'AppData', 'Local')
    return path.join(localAppData, APP_NAME)
  }
  if (process.platform === 'darwin') {
    return path.join(app.getPath('home'), 'Library', 'Caches', APP_NAME)
  }
  // Linux
  return path.join(app.getPath('home'), '.cache', APP_NAME)
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
