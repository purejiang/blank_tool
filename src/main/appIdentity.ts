import { app } from 'electron'
import { installDevDataRoot } from './dataRoot'

/**
 * 应用品牌名：同时决定 Electron 的 userData 目录
 * （Windows `%APPDATA%\blanks`、macOS `~/Library/Application Support/blanks`）。
 *
 * 历史：应用原名 Blank Tool，数据落在 `blank_tool`；改名 Blanks 后统一用 `blanks`，
 * 与旧的 `blank_tool` 目录**刻意分开**（不做迁移，旧目录原样保留，见 appPaths.ts）。
 *
 * ⚠️ 必须由 `main.ts` 作为**第一个 import** 引入：
 * `electron-store` 在模块构造时（`src/main/stores/appStore.ts` 顶层 `new Store()`）
 * 就把 `app.getPath('userData')` 定死，晚一步配置仍会写进旧目录。
 */
export const APP_NAME = 'blanks'

/**
 * 应用身份（Windows 的 AppUserModelID）。
 *
 * 决定任务栏**分组与固定**、通知归属、跳转列表——也就是"Windows 认为这是哪个应用"。
 * 必须与 electron-builder 写进快捷方式的 `package.json > build.appId` **逐字一致**：
 * 两者不一致时，运行中的窗口会挂到**旧 AUMID 那个应用**上（改名后仍与旧的 Blank Tool
 * 挤在同一个任务栏分组里，固定新版快捷方式也对不上），而且不报任何错。
 *
 * 这条规则由 `tests/unit/main/appIdentity.test.ts` 守着，改一个必须改另一个。
 */
export const APP_ID = 'com.cyanrain.blanks'

app.setName(APP_NAME)

/**
 * `app.setName()` 之后、`electron-store` 构造之前，最后一件事：确认默认数据目录
 * （`%APPDATA%\blanks`）真的写得进去。写不进去时（安全软件/系统策略拦 electron.exe
 * 写 C: 用户区域）把 userData 整体挪到候选目录，否则 `electron-store` 会在模块加载期
 * 直接抛 `EPERM ... app-config.json.tmp-...`，App 停在一个截断的模态框上。
 *
 * 实测结论、候选顺序与边界都写在 `src/main/dataRoot.ts` 顶部的注释里。
 * dev 之外（`app.isPackaged`）或没有 dev 标记时本调用什么都不做。
 */
installDevDataRoot()
