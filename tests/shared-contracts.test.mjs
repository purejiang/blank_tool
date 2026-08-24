import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import test from 'node:test'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

const channelsPath = new URL('../src/shared/ipc/channels.ts', import.meta.url)
const pathConfigPath = new URL('../src/shared/config/pathConfig.ts', import.meta.url)
const protocolPath = new URL('../src/shared/ipc/protocol.ts', import.meta.url)
const handlersDir = new URL('../cli/app/handlers/', import.meta.url)

test('IPC channels 包含配置相关契约', async () => {
  const content = await readFile(channelsPath, 'utf8')
  assert.match(content, /getAppConfig:\s*'get-app-config'/)
  assert.match(content, /setManyAppConfig:\s*'set-app-config-many'/)
  assert.match(content, /appConfigChanged:\s*'app-config-changed'/)
  assert.match(content, /getUserConfig:\s*'get-user-config'/)
  assert.match(content, /setUserConfig:\s*'set-user-config'/)
  assert.match(content, /getSettingsViewModel:\s*'get-settings-view-model'/)
  assert.match(content, /resolveSettingsPaths:\s*'resolve-settings-paths'/)
  assert.match(content, /showSystemNotification:\s*'show-system-notification'/)
})

test('共享路径配置包含主进程关键键名', async () => {
  const content = await readFile(pathConfigPath, 'utf8')
  assert.match(content, /export const PATH_CONFIG_DEFAULTS/)
  assert.match(content, /export const APP_CONFIG_KEYS/)
  assert.match(content, /runtime:\s*'runtime'/)
  assert.match(content, /rendererEntry:\s*'rendererEntry'/)
})

test('ApiMethodMap 覆盖所有后端 API_MAP 键 — 100% 覆盖', async () => {
  // ---- 1. Extract all backend API_MAP keys from Python handler files ----
  const handlerFiles = (await readdir(fileURLToPath(handlersDir)))
    .filter(f => f.endsWith('.py'))
    .sort()

  /** @type {Map<string, string>} key → source file name */
  const backendKeys = new Map()

  for (const file of handlerFiles) {
    const filePath = path.join(fileURLToPath(handlersDir), file)
    const content = await readFile(filePath, 'utf8')

    // Extract the API_MAP dict block: API_MAP = { ... }
    const apiMapMatch = content.match(/API_MAP\s*=\s*\{([^]*?)\n\}/)
    if (!apiMapMatch) {
      console.warn(`  ⚠ no API_MAP found in ${file}`)
      continue
    }

    // Extract all quoted keys from the block
    // Matches both "key" and 'key' followed by :
    const keyRegex = /['"]([\w.]+)['"]\s*:/g
    let match
    while ((match = keyRegex.exec(apiMapMatch[1])) !== null) {
      const key = match[1]
      if (backendKeys.has(key)) {
        console.warn(`  ⚠ duplicate key "${key}" in ${file} (previously in ${backendKeys.get(key)})`)
      }
      backendKeys.set(key, file)
    }
  }

  console.log(`\n  Backend API_MAP keys found: ${backendKeys.size}`)

  // ---- 2. Extract all ApiMethodMap keys from protocol.ts ----
  const protocolContent = await readFile(protocolPath, 'utf8')

  // Extract the interface ApiMethodMap block
  const ifaceMatch = protocolContent.match(/export interface ApiMethodMap\s*\{([^]*?)\n\}/)
  if (!ifaceMatch) {
    throw new Error('Could not find ApiMethodMap interface in protocol.ts')
  }

  const tsKeyRegex = /['"]([\w.]+)['"]\s*:\s*\{/g
  const tsKeys = new Set()
  let tsMatch
  while ((tsMatch = tsKeyRegex.exec(ifaceMatch[1])) !== null) {
    tsKeys.add(tsMatch[1])
  }

  console.log(`  TypeScript ApiMethodMap keys found: ${tsKeys.size}`)

  // ---- 3. Assert every backend key has a matching TS key ----
  /** @type {string[]} */
  const missing = []
  for (const [pyKey, sourceFile] of backendKeys) {
    if (!tsKeys.has(pyKey)) {
      missing.push(`"${pyKey}" (from ${sourceFile})`)
    }
  }

  if (missing.length > 0) {
    console.error(`\n  ❌ MISSING KEYS (${missing.length}):`)
    for (const m of missing) {
      console.error(`     ${m}`)
    }
    assert.fail(
      `ApiMethodMap is missing ${missing.length} backend key(s):\n${missing.join('\n')}`
    )
  }

  // ---- 4. Report extra TS keys not in backend (informational, not a failure) ----
  const extra = []
  for (const tsKey of tsKeys) {
    if (!backendKeys.has(tsKey)) {
      extra.push(tsKey)
    }
  }
  if (extra.length > 0) {
    console.warn(`\n  ⚠ TS-only keys (not in any backend API_MAP): ${extra.length}`)
    for (const e of extra) {
      console.warn(`     "${e}"`)
    }
  }

  console.log(`  ✅ All ${backendKeys.size} backend keys covered in ApiMethodMap`)
})
