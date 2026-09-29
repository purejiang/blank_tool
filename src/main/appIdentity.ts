import { app } from 'electron'

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

app.setName(APP_NAME)
