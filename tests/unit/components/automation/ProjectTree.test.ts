/**
 * ProjectTree — untrusted-import guard + keyboard accessibility.
 *
 * Import files come from colleagues / hand edits / interrupted downloads, so
 * the merge path is the one place raw JSON reaches the persisted config. A
 * project with no name, or a script whose `steps` is not an array, used to be
 * merged as-is: the tree showed blank rows and the backend later refused the
 * run. Rows were also `div + @click` only — unreachable by keyboard.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { mockMessage, mockDialog } = vi.hoisted(() => ({
  mockMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  mockDialog: { warning: vi.fn() },
}))

vi.mock('naive-ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('naive-ui')>()
  return { ...actual, useMessage: () => mockMessage, useDialog: () => mockDialog }
})

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

const readTextFile = vi.fn()
vi.mock('@utils/readTextFile', () => ({ readTextFile: (...a: any[]) => readTextFile(...a) }))

import ProjectTree from '@/renderer/components/automation/ProjectTree.vue'
import { genId } from '@utils/id'

function makeStore(projects: any[] = []) {
  return {
    projects,
    // script rows only render under the SELECTED project
    selectedProjectId: projects[0]?.id || '',
    selectedScriptId: '',
    selectProject: vi.fn(function (this: any, id: string) { this.selectedProjectId = id }),
    selectScript: vi.fn(function (this: any, pid: string, sid: string) {
      this.selectedProjectId = pid
      this.selectedScriptId = sid
    }),
    persist: vi.fn(),
    loadEditorFromSelection: vi.fn(),
    newProject: vi.fn(),
    newScript: vi.fn(),
    openProjectMeta: vi.fn(),
    openScriptMeta: vi.fn(),
    deleteProject: vi.fn(),
    deleteScript: vi.fn(),
  }
}

const PROJECT = {
  id: 'p1',
  name: 'demo',
  scripts: [{ id: 's1', name: 'main', updated_at: '', steps: [{ id: 'x', action: 'back' }] }],
}

function mountTree(store = makeStore([structuredClone(PROJECT)])) {
  const w = mount(ProjectTree, { props: { store, running: false } })
  return { w, store }
}

/** Drive the real "import" entry point (the header icon button). */
async function importWith(text: string) {
  readTextFile.mockResolvedValue(text)
  ;(window as any).electronAPI = {
    showOpenDialog: vi.fn(async () => ({ canceled: false, filePaths: ['x.json'] })),
    readFile: vi.fn(),
  }
  const { w, store } = mountTree()
  await w.get('[data-testid="import-projects"]').trigger('click')
  await flushPromises()
  return { w, store }
}

beforeEach(() => {
  vi.clearAllMocks()
  readTextFile.mockReset()
})

describe('ProjectTree — import shape validation', () => {
  it('drops nameless projects and counts them as skipped', async () => {
    const { w, store } = await importWith(JSON.stringify({
      projects: [
        { id: 'a', name: '  ', scripts: [] },              // blank name
        { id: 'b', scripts: [] },                           // no name
        { id: 'c', name: 'good', scripts: [] },
        null,
      ],
    }))

    expect(store.projects.map((p: any) => p.name)).toEqual(['demo', 'good'])
    expect(mockMessage.warning).toHaveBeenCalledWith('automation.importSkipped')
    expect(mockMessage.error).not.toHaveBeenCalled()
    expect(w.exists()).toBe(true)
  })

  it('normalizes a script whose steps are not an array', async () => {
    const { store } = await importWith(JSON.stringify({
      projects: [{
        id: 'p2',
        name: 'broken',
        scripts: [{ id: 's2', name: 's', steps: 'not-an-array' }],
      }],
    }))

    const imported = store.projects.find((p: any) => p.id === 'p2')!
    expect(Array.isArray(imported.scripts[0].steps)).toBe(true)
    expect(imported.scripts[0].steps).toEqual([])
  })

  it('mints ids for projects/scripts that arrive without one', async () => {
    const { store } = await importWith(JSON.stringify({
      projects: [{ name: 'no-id', scripts: [{ name: 'script' }] }],
    }))

    const imported = store.projects.find((p: any) => p.name === 'no-id')!
    expect(typeof imported.id).toBe('string')
    expect(imported.id.length).toBeGreaterThan(0)
    expect(typeof imported.scripts[0].id).toBe('string')
    expect(imported.scripts[0].id.length).toBeGreaterThan(0)
    // two nameless-id imports must not collide
    expect(imported.id).not.toBe(imported.scripts[0].id)
  })

  it('skips scripts that are not objects and reports the count', async () => {
    const { store } = await importWith(JSON.stringify({
      projects: [{ id: 'p3', name: 'mixed', scripts: ['nope', 42, null, { name: '' }, { id: 'ok', name: 'ok' }] }],
    }))

    const imported = store.projects.find((p: any) => p.id === 'p3')!
    expect(imported.scripts).toHaveLength(1)
    expect(imported.scripts[0].name).toBe('ok')
    expect(mockMessage.warning).toHaveBeenCalledWith('automation.importSkipped')
  })

  it('refuses the whole file when nothing is valid, and imports nothing', async () => {
    const { store } = await importWith(JSON.stringify({
      projects: [{ id: 'x' }, { id: 'y', name: '' }],
    }))

    expect(store.projects).toHaveLength(1)          // only the seeded project
    expect(store.persist).not.toHaveBeenCalled()
    expect(mockMessage.error).toHaveBeenCalledWith('automation.importFailed')
  })

  it('keeps a valid script’s steps byte-for-byte', async () => {
    const steps = [{ id: 'k', action: 'tap', mode: 'coord', coord: { x: 1, y: 2 }, note: 'hi' }]
    const { store } = await importWith(JSON.stringify({
      projects: [{ id: 'p4', name: 'exact', scripts: [{ id: 's4', name: 's', steps }] }],
    }))

    const imported = store.projects.find((p: any) => p.id === 'p4')!
    expect(imported.scripts[0].steps).toEqual(steps)
  })

  it('still rejects a document with no projects[]', async () => {
    const { store } = await importWith(JSON.stringify({ nope: 1 }))
    expect(store.projects).toHaveLength(1)
    expect(mockMessage.error).toHaveBeenCalledWith('automation.importFailed')
  })
})

describe('ProjectTree — keyboard accessibility', () => {
  it('exposes project and script rows as focusable buttons with labels', () => {
    const { w } = mountTree()
    const proj = w.get('.proj-name')
    expect(proj.attributes('role')).toBe('button')
    expect(proj.attributes('tabindex')).toBe('0')
    expect(proj.attributes('aria-label')).toBe('automation.selectProject')

    const script = w.get('.script-row')
    expect(script.attributes('role')).toBe('button')
    expect(script.attributes('tabindex')).toBe('0')
    expect(script.attributes('aria-label')).toBe('automation.selectScript')
  })

  it('marks the active rows for screen readers', () => {
    const store = makeStore([structuredClone(PROJECT)])
    store.selectedProjectId = 'p1'
    store.selectedScriptId = 's1'
    const { w } = mountTree(store)

    expect(w.get('.proj-name').attributes('aria-current')).toBe('true')
    expect(w.get('.script-row').attributes('aria-current')).toBe('true')
  })

  it('selects a project with Enter and with Space', async () => {
    const { w, store } = mountTree()
    const proj = w.get('.proj-name')

    await proj.trigger('keydown.enter')
    expect(store.selectProject).toHaveBeenLastCalledWith('p1')

    await proj.trigger('keydown.space')
    expect(store.selectProject).toHaveBeenCalledTimes(2)
  })

  it('selects a script with Enter and with Space', async () => {
    const { w, store } = mountTree()
    const script = w.get('.script-row')

    await script.trigger('keydown.enter')
    expect(store.selectScript).toHaveBeenLastCalledWith('p1', 's1')

    await script.trigger('keydown.space')
    expect(store.selectScript).toHaveBeenCalledTimes(2)
  })

  it('leaves click selection intact', async () => {
    const { w, store } = mountTree()
    await w.get('.proj-name').trigger('click')
    expect(store.selectProject).toHaveBeenCalledWith('p1')
    await w.get('.script-row').trigger('click')
    expect(store.selectScript).toHaveBeenCalledWith('p1', 's1')
  })
})

describe('ProjectTree — id helper sanity', () => {
  it('genId produces distinct ids (the import fallback relies on it)', () => {
    expect(genId()).not.toBe(genId())
  })
})
