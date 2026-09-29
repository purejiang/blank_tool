import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

/**
 * 应用身份守卫（2026-09-29 实测的真实事故）。
 *
 * 应用从 Blank Tool 改名 Blanks 时只改了一半：`APP_NAME` / userData 目录、`productName`、
 * `package.json` 的 `name` 都换成了 blanks，但 `main.ts` 里
 * `app.setAppUserModelId('com.cyanrain.blank-tool')` 还是旧字面量。AppUserModelID 是
 * **Windows 判定"这是哪个应用"的依据**（任务栏分组与固定、通知归属、跳转列表），
 * 于是运行中的 Blanks 窗口仍然和旧的 Blank Tool 挤在同一个任务栏分组里，固定新版
 * 快捷方式也对不上——而且不报任何错、日志里什么都没有。
 *
 * 这里把三处身份钉成一致，谁漂了就红灯：
 *   1. `APP_ID` 必须等于 `package.json > build.appId`（electron-builder 用它写快捷方式 AUMID）；
 *   2. `main.ts` 必须**引用 `APP_ID`**，不得再出现写死的 `com.cyanrain.*` 字面量；
 *   3. `APP_NAME` / `productName` / `artifactName` 必须是 Blanks 口径。
 */

// appIdentity.ts 在模块加载时就会调用 app.setName()，测试环境没有 electron 运行时，
// 所以先把它换成桩。
const setName = vi.fn()
vi.mock('electron', () => ({ app: { setName: (...args: unknown[]) => setName(...args) } }))

const { APP_ID, APP_NAME } = await import('@/main/appIdentity')

const ROOT = resolve(process.cwd())
const pkg = JSON.parse(readFileSync(resolve(ROOT, 'package.json'), 'utf8'))
const mainSource = readFileSync(resolve(ROOT, 'src/main/main.ts'), 'utf8')

describe('应用身份（APP_NAME / APP_ID / package.json）', () => {
  it('用 APP_NAME 决定 Electron 应用名（= userData 目录名）', () => {
    expect(APP_NAME).toBe('blanks')
    expect(setName).toHaveBeenCalledWith('blanks')
  })

  it('APP_ID 与 package.json 的 build.appId 逐字一致', () => {
    expect(APP_ID).toBe('com.cyanrain.blanks')
    expect(pkg.build?.appId).toBe(APP_ID)
  })

  it('main.ts 用 APP_ID 设置 AppUserModelID，不再有写死的旧 id', () => {
    expect(mainSource).toContain('setAppUserModelId(APP_ID)')
    // 写死字面量就会与 build.appId 漂移 —— 正是这次事故的形态
    expect(mainSource).not.toMatch(/setAppUserModelId\(\s*['"]/)
    expect(mainSource).not.toContain('com.cyanrain.blank-tool')
  })

  it('包名 / 产品名 / 安装包名都是 Blanks 口径（与旧的 blank_tool 分离）', () => {
    expect(pkg.name).toBe('blanks')
    expect(pkg.build?.productName).toBe('Blanks')
    expect(pkg.build?.artifactName).toContain('Blanks-Setup')
  })
})
