import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

/**
 * 样式 token 完整性守卫。
 *
 * 起因（2026-09-29 实测，真实渲染层）：`main.css` 的 `:root` 里写着
 *   --text-secondary: var(--text-secondary);
 *   --text-muted: var(--text-muted);
 * 这是**自引用**。按 CSS 规范，含自引用的自定义属性在 computed-value 阶段是 invalid，
 * 计算值变成空串 —— 于是 `color: var(--app-text-muted)` 退化成 `unset`（继承父色），
 * 整个设计系统的第 2/3 档文字色**静默失效**（全仓 ~160 处引用），浅/深主题都中招，
 * 而且不报错、不警告、截图上也"看着还行"。main.css 在 tokens.css 之后加载且同为
 * :root 特异性，所以它会盖掉 tokens.css 里的正确定义。
 *
 * 本测试把这类 bug 变成红灯：
 *   1. 任何自定义属性（直接或间接）自引用 → 失败
 *   2. 声明了空值（`--x:;`）→ 失败
 *   3. 关键 token 必须被声明过 → 失败
 *   4. `var(--x)` 引用必须都能在全仓找到定义 → 失败
 *      （**只算没有 fallback 的写法**。`var(--x, var(--y))` 是有意为之的降级，
 *        x 未定义时仍能取到 y，不算 bug；`var(--x)` 则会让整条声明静默失效。）
 *
 * ⚠️ 解析前必须剥掉 CSS 注释：修复说明里就原样写了那段自引用代码，
 *    不剥注释会把注释当成"仍然存在自引用"。
 */

const RENDERER = resolve(process.cwd(), 'src/renderer')
const STYLES_DIR = join(RENDERER, 'assets/styles')

/** 这些 token 是全应用外观的底座，缺一个就说明有人改名/误删了。 */
const CRITICAL_TOKENS = [
  '--bg',
  '--surface',
  '--surface-alt',
  '--border',
  '--text',
  '--text-secondary',
  '--text-muted',
  '--text-dim',
  '--sidebar-bg',
  '--primary',
  '--primary-soft',
  '--ring',
  '--scrim',
  '--success-text',
  '--warning-text',
  '--danger-text',
  '--info-text',
  '--shadow-card',
  '--shadow-lift',
  '--shadow-pop',
  '--focus-ring',
  '--radius-card',
  '--radius-control',
  '--radius-chip',
  '--font-family-base',
  '--font-family-monospace',
  /* 非颜色维度（tokens.css 末尾的「非颜色维度」块）：字号阶 + 语义角色 */
  '--fs-page-title',
  '--fs-page-desc',
  '--fs-section-title',
  '--fs-card-title',
  '--fs-row-title',
  '--fs-body',
  '--fs-label',
  '--fs-aux',
  '--fs-meta',
  '--fs-mono',
  '--fs-stat',
  /* 间距阶 + 语义角色 + 列表/卡片内距 */
  '--gap-xs',
  '--gap-sm',
  '--gap-md',
  '--gap-lg',
  '--gap-xl',
  '--row-pad-y',
  '--row-pad-x',
  '--card-pad',
  /* 控件密度、描边、动效 */
  '--control-h-tiny',
  '--control-h-sm',
  '--control-h-md',
  '--hairline',
  '--dash-border',
  '--duration-fast',
  '--duration-base',
  '--duration-slow',
  '--ease-standard',
]

const COMMENT = /\/\*[\s\S]*?\*\//g
const DECL = /(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]*)/g
const VARREF = /var\(\s*(--[A-Za-z0-9_-]+)/g
/** 只匹配**没有 fallback** 的引用：`var(--x)` 会让整条声明静默失效，`var(--x, y)` 不会。 */
const VARREF_NOFALLBACK = /var\(\s*(--[A-Za-z0-9_-]+)\s*\)/g
const STYLE_BLOCK = /<style[^>]*>([\s\S]*?)<\/style>/g

interface Decl {
  name: string
  value: string
  file: string
  line: number
}

function lineOf(text: string, index: number): number {
  return text.slice(0, index).split('\n').length
}

function parseCss(text: string, file: string, out: Decl[]): void {
  const stripped = text.replace(COMMENT, (m) => ' '.repeat(m.length)) // 保长度以维持行号
  for (const m of stripped.matchAll(DECL)) {
    out.push({ name: m[1], value: m[2].trim(), file, line: lineOf(stripped, m.index ?? 0) })
  }
}

function collectCssFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) collectCssFiles(full, out)
    else if (entry.endsWith('.css')) out.push(full)
  }
  return out
}

function collectVueFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) collectVueFiles(full, out)
    else if (entry.endsWith('.vue')) out.push(full)
  }
  return out
}

/** 收集全仓（独立 css + 组件 scoped style）的自定义属性声明。 */
function collectDeclarations(): Decl[] {
  const decls: Decl[] = []
  for (const file of collectCssFiles(STYLES_DIR)) {
    parseCss(readFileSync(file, 'utf8'), file, decls)
  }
  for (const file of collectVueFiles(RENDERER)) {
    const text = readFileSync(file, 'utf8')
    for (const m of text.matchAll(STYLE_BLOCK)) {
      parseCss(m[1], file, decls)
    }
  }
  return decls
}

const DECLS = collectDeclarations()

/**
 * 全仓样式来源：独立 CSS 文件 + 每个 `.vue` 的 `<style>` 块。
 * 用于「引用是否存在」的检查 —— 这个检查必须看**引用点的原文**，
 * 而 DECLS 只保留了声明。
 */
function collectSources(): { file: string; text: string }[] {
  const out: { file: string; text: string }[] = []
  for (const file of collectCssFiles(STYLES_DIR)) {
    out.push({ file, text: readFileSync(file, 'utf8') })
  }
  for (const file of collectVueFiles(RENDERER)) {
    const text = readFileSync(file, 'utf8')
    const blocks = [...text.matchAll(STYLE_BLOCK)].map((m) => m[1]).join('\n')
    if (blocks.trim()) out.push({ file, text: blocks })
  }
  return out
}

/** name → 它引用到的所有自定义属性（跨声明取并集：被覆盖的声明同样是隐患）。 */
function buildGraph(decls: Decl[]): Map<string, Set<string>> {
  const graph = new Map<string, Set<string>>()
  for (const d of decls) {
    const deps = graph.get(d.name) ?? new Set<string>()
    for (const ref of d.value.matchAll(VARREF)) deps.add(ref[1])
    graph.set(d.name, deps)
  }
  return graph
}

/** 找环：对每个起点做一次沿依赖的 DFS，路径重复即环。 */
function findCycles(graph: Map<string, Set<string>>): string[][] {
  const cycles: string[][] = []
  const keys = new Set<string>()

  const walk = (name: string, path: string[]): void => {
    if (path.includes(name)) {
      const cycle = path.slice(path.indexOf(name)).concat(name)
      const key = [...new Set(cycle)].sort().join('|')
      if (!keys.has(key)) {
        keys.add(key)
        cycles.push(cycle)
      }
      return
    }
    for (const dep of graph.get(name) ?? []) walk(dep, [...path, name])
  }

  for (const name of graph.keys()) walk(name, [])
  return cycles
}

describe('样式 token 完整性', () => {
  it('扫描到了足够多的声明（守卫自身要有效）', () => {
    expect(DECLS.length).toBeGreaterThan(100)
    expect(new Set(DECLS.map((d) => d.name)).size).toBeGreaterThan(100)
  })

  it('没有自引用 / 循环引用的自定义属性', () => {
    const cycles = findCycles(buildGraph(DECLS)).map((cycle) => cycle.join(' -> '))
    expect(cycles, `发现循环引用（会导致变量计算值为空）：\n${cycles.join('\n')}`).toEqual([])
  })

  it('没有声明成空值', () => {
    const empty = DECLS.filter((d) => d.value === '').map((d) => `${d.name} @ ${d.file}:${d.line}`)
    expect(empty).toEqual([])
  })

  it('关键 token 都有定义', () => {
    const declared = new Set(DECLS.map((d) => d.name))
    const missing = CRITICAL_TOKENS.filter((name) => !declared.has(name))
    expect(missing, `缺少关键 token：${missing.join(', ')}`).toEqual([])
  })

  /**
   * 原实现只检查 themes.css 的别名层，于是 `common/components.css` 里
   * `var(--primary-color-alpha)` / `var(--primary-color-light)` / `var(--transition-normal)`
   * 三个悬空引用长期无人发现（相关声明整条静默失效，进度条渐变根本没渲染）。
   * 现在覆盖**全仓** CSS + 所有组件 `<style>` 块。
   */
  it('全仓没有引用未定义变量的 var()（只算无 fallback 的写法）', () => {
    const declared = new Set(DECLS.map((d) => d.name))
    const dangling: string[] = []
    for (const { file, text } of collectSources()) {
      const stripped = text.replace(COMMENT, (m) => ' '.repeat(m.length))
      for (const ref of stripped.matchAll(VARREF_NOFALLBACK)) {
        if (!declared.has(ref[1])) {
          dangling.push(`${ref[1]} @ ${relative(RENDERER, file)}:${lineOf(stripped, ref.index ?? 0)}`)
        }
      }
    }
    expect(
      dangling,
      `引用了未定义的自定义属性（该声明不会生效）：\n${dangling.join('\n')}`,
    ).toEqual([])
  })

  it('修复说明要留在源码里（防止有人再加回自引用）', () => {
    const mainCss = readFileSync(join(STYLES_DIR, 'main.css'), 'utf8')
    expect(mainCss).toMatch(/别再加回来|自引用/)
  })
})
