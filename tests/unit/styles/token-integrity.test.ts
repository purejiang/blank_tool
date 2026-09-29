import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

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
 *   4. 别名层（themes.css）里 `var(--x)` 引用必须都能在全仓找到定义 → 失败
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
]

const COMMENT = /\/\*[\s\S]*?\*\//g
const DECL = /(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]*)/g
const VARREF = /var\(\s*(--[A-Za-z0-9_-]+)/g
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

  it('别名层（themes.css）引用的变量都能在全仓找到定义', () => {
    const declared = new Set(DECLS.map((d) => d.name))
    const themes = DECLS.filter((d) => d.file.endsWith('themes.css'))
    const dangling = new Set<string>()
    for (const d of themes) {
      for (const ref of d.value.matchAll(VARREF)) {
        if (!declared.has(ref[1])) dangling.add(`${ref[1]} (from ${d.name})`)
      }
    }
    expect([...dangling], `别名指向了不存在的变量：${[...dangling].join(', ')}`).toEqual([])
  })

  it('修复说明要留在源码里（防止有人再加回自引用）', () => {
    const mainCss = readFileSync(join(STYLES_DIR, 'main.css'), 'utf8')
    expect(mainCss).toMatch(/别再加回来|自引用/)
  })
})
