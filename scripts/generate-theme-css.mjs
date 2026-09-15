#!/usr/bin/env node
/**
 * generate-theme-css.mjs — 从 tokens.ts 生成 themes.css / variables.css。
 *
 * 设计（构建期生成，保零运行时开销 + 现有加载链不变）：
 *   · tokens.ts 是 TS，Node 不能直接 import → 用已安装的 esbuild 在内存里
 *     打包成 ESM，再经 data: URL 动态 import。零临时文件、零新增依赖。
 *   · 生成结果幂等：重复运行不产生 diff（npm run theme:css）。
 *   · 一致性由 tests/unit/theme/tokens-css-parity.test.ts 守卫：手改生成的
 *     CSS 会被测试拒绝。
 *
 * 运行：npm run theme:css（dev / build 前自动执行）
 */
import { build } from 'esbuild'
import { writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')
const TOKENS_TS = resolve(root, 'src/renderer/theme/tokens.ts')
const STYLES_DIR = resolve(root, 'src/renderer/assets/styles')

async function loadTokens() {
  const result = await build({
    entryPoints: [TOKENS_TS],
    bundle: true,
    format: 'esm',
    platform: 'neutral',
    write: false,
    logLevel: 'silent',
  })
  const code = result.outputFiles[0].text
  const dataUrl = 'data:text/javascript;base64,' + Buffer.from(code, 'utf8').toString('base64')
  return import(dataUrl)
}

function header(fileName, sourceNote, ruleNote) {
  return `/* ============================================================================
 * ${fileName} — 【自动生成，请勿手改】
 *
 * 源：src/renderer/theme/tokens.ts（${sourceNote}）
 * 生成：npm run theme:css（scripts/generate-theme-css.mjs）
 * 守卫：tests/unit/theme/tokens-css-parity.test.ts
 *
 * ${ruleNote}
 * 分组的语义注释见 tokens.ts；本文件只保证「token → CSS 变量」的逐一对应。
 * ========================================================================== */
`
}

function block(selector, entries) {
  const body = entries.map(([name, value]) => `  --app-${name}: ${value};`).join('\n')
  return `${selector} {\n${body}\n}\n`
}

async function main() {
  const { colorTokens, staticTokens } = await loadTokens()

  const themesCss =
    header(
      'themes.css',
      'colorTokens：颜色 token',
      '铁律：组件里禁止写死色值；新增色相必须 light / dark 两边都加，否则另一主题下会静默落到别的颜色。',
    ) +
    '\n' +
    block(':root,\n[data-theme="light"]', Object.entries(colorTokens.light)) +
    '\n' +
    block('[data-theme="dark"]', Object.entries(colorTokens.dark))

  const variablesCss =
    header(
      'variables.css',
      'staticTokens：非颜色 token',
      '命名空间与颜色一致，全部 --app-*，避免再出现 --space-sm / --spacing-sm 这类「一件事两个名字」的重复体系。',
    ) +
    '\n' +
    block(':root', Object.entries(staticTokens))

  writeFileSync(resolve(STYLES_DIR, 'themes.css'), themesCss, 'utf8')
  writeFileSync(resolve(STYLES_DIR, 'variables.css'), variablesCss, 'utf8')

  const colorCount = Object.keys(colorTokens.light).length + Object.keys(colorTokens.dark).length
  console.log(
    `[theme:css] generated themes.css (${colorCount} colors) + variables.css ` +
      `(${Object.keys(staticTokens).length} static tokens)`,
  )
}

main().catch((e) => {
  console.error('[theme:css] failed:', e.message)
  process.exit(1)
})
