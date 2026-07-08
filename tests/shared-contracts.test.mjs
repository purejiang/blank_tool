import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const channelsPath = new URL('../src/shared/ipc/channels.ts', import.meta.url)
const pathConfigPath = new URL('../src/shared/config/pathConfig.ts', import.meta.url)

test('IPC channels 包含配置相关契约', async () => {
  const content = await readFile(channelsPath, 'utf8')
  assert.match(content, /getAppConfig:\s*\{\s*name:\s*'get-app-config'/)
  assert.match(content, /setManyAppConfig:\s*\{\s*name:\s*'set-app-config-batch'/)
  assert.match(content, /appConfigChanged:\s*\{\s*name:\s*'app-config-changed'/)
  assert.match(content, /getUserConfig:\s*\{\s*name:\s*'get-user-config'/)
  assert.match(content, /setUserConfig:\s*\{\s*name:\s*'set-user-config'/)
  assert.match(content, /getSettingsViewModel:\s*\{\s*name:\s*'get-settings-view-model'/)
  assert.match(content, /resolveSettingsPaths:\s*\{\s*name:\s*'resolve-settings-paths'/)
  assert.match(content, /showSystemNotification:\s*\{\s*name:\s*'show-system-notification'/)
})

test('共享路径配置包含主进程关键键名', async () => {
  const content = await readFile(pathConfigPath, 'utf8')
  assert.match(content, /export const PATH_CONFIG_DEFAULTS/)
  assert.match(content, /export const APP_CONFIG_KEYS/)
  assert.match(content, /runtime:\s*'runtime'/)
  assert.match(content, /rendererEntry:\s*'rendererEntry'/)
})
