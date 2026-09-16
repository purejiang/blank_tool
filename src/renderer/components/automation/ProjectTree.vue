<template>
  <section class="col col-left">
    <div class="col-head app-subhead">
      <span>{{ t('automation.projects') }}</span>
      <div class="app-subhead-actions">
        <IconButton
          :icon="Upload"
          :label="t('automation.importMergeHint')"
          :aria-label="t('automation.import')"
          :disabled="running"
          size="tiny"
          tertiary
          placement="bottom"
          data-testid="import-projects"
          @click="importConfig"
        />
        <IconButton
          :icon="FolderPlus"
          :label="t('automation.newProject')"
          :disabled="running"
          size="tiny"
          tertiary
          type="primary"
          data-testid="new-project"
          @click="store.newProject"
        />
      </div>
    </div>

    <n-empty v-if="!store.projects.length" :description="t('automation.noProject')" size="small" class="col-empty">
      <template #extra>
        <div class="empty-hint">{{ t('automation.noProjectDesc') }}</div>
        <n-button size="tiny" dashed type="primary" :disabled="running" @click="store.newProject">
          <template #icon><n-icon><FolderPlus /></n-icon></template>
          {{ t('automation.newProject') }}
        </n-button>
      </template>
    </n-empty>

    <!-- n-scrollbar：覆盖式滚动条不占布局宽度，表头与行右边缘始终对齐
         （原生滚动条 + scrollbar-gutter 会在右侧常驻 10px 车道）。 -->
    <n-scrollbar v-else class="tree">
      <div class="tree-body">
        <div v-for="p in store.projects" :key="p.id" class="proj">
          <div class="proj-row" :class="{ current: p.id === store.selectedProjectId }">
            <!-- 开合与选中解耦：箭头只管展开/收起，点名称才是选中 -->
            <button
              class="proj-caret"
              type="button"
              :aria-expanded="isExpanded(p.id)"
              :aria-label="isExpanded(p.id) ? t('automation.collapseProject') : t('automation.expandProject')"
              :title="isExpanded(p.id) ? t('automation.collapseProject') : t('automation.expandProject')"
              @click.stop="toggleProject(p.id)"
            >
              <n-icon size="14"><component :is="isExpanded(p.id) ? ChevronDown : ChevronRight" /></n-icon>
            </button>

            <div class="proj-main">
              <!-- div+click with role/tabindex: a real <button> would be invalid
                   here (the row-actions dropdown renders a button inside). -->
              <div
                class="proj-name"
                role="button"
                tabindex="0"
                :aria-label="t('automation.selectProject', { name: p.name })"
                :aria-current="p.id === store.selectedProjectId ? 'true' : undefined"
                @click="store.selectProject(p.id)"
                @keydown.enter.prevent="store.selectProject(p.id)"
                @keydown.space.prevent="store.selectProject(p.id)"
              >
                <n-icon size="14"><Box /></n-icon>
                <span class="name-line" :title="p.description ? `${p.name} · ${p.description}` : p.name">{{ p.name }}</span>
              </div>
              <div v-if="p.description" class="item-desc proj-desc">{{ p.description }}</div>
            </div>

            <span
              v-if="p.scripts.length"
              class="app-pill"
              :title="t('automation.scriptCountBadge', { n: p.scripts.length })"
            >{{ p.scripts.length }}</span>

            <div class="row-actions">
              <n-dropdown
                trigger="click"
                placement="bottom-end"
                :options="projectMenuOptions"
                @select="(key: string) => onProjectMenu(key, p)"
              >
                <IconButton
                  :icon="MoreHorizontal"
                  :label="t('common.more')"
                  :disabled="running"
                  size="tiny"
                  text
                  @click.stop
                />
              </n-dropdown>
            </div>
          </div>

          <div v-if="isExpanded(p.id)" class="scripts">
            <div v-if="!p.scripts.length" class="scripts-empty">{{ t('automation.noScript') }}</div>
            <div
              v-for="s in p.scripts"
              :key="s.id"
              class="script-row"
              :class="{ active: s.id === store.selectedScriptId }"
              role="button"
              tabindex="0"
              :aria-label="t('automation.selectScript', { name: s.name })"
              :aria-current="s.id === store.selectedScriptId ? 'true' : undefined"
              @click="store.selectScript(p.id, s.id)"
              @keydown.enter.prevent="store.selectScript(p.id, s.id)"
              @keydown.space.prevent="store.selectScript(p.id, s.id)"
            >
              <n-icon size="14"><FileText /></n-icon>
              <div class="script-main">
                <span
                  class="name-line"
                  :title="s.description ? `${s.name} · ${s.description}` : s.name"
                >{{ s.name }}</span>
                <div v-if="s.description" class="item-desc script-desc">{{ s.description }}</div>
              </div>
              <span class="app-pill" :title="t('automation.stepCountBadge', { n: s.steps?.length || 0 })">
                {{ s.steps?.length || 0 }}
              </span>
              <n-dropdown
                trigger="click"
                placement="bottom-end"
                :options="scriptMenuOptions"
                @select="(key: string) => onScriptMenu(key, p, s)"
              >
                <IconButton
                  :icon="MoreHorizontal"
                  :label="t('common.more')"
                  :disabled="running"
                  size="tiny"
                  text
                  class="script-ops"
                  @click.stop
                />
              </n-dropdown>
            </div>
            <n-button
              size="tiny"
              dashed
              block
              :disabled="running"
              @click="store.newScript(p.id)"
            >
              <template #icon><n-icon><FilePlus /></n-icon></template>
              {{ t('automation.newScript') }}
            </n-button>
          </div>
        </div>
      </div>
    </n-scrollbar>
  </section>
</template>

<script setup lang="ts">
import { h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDropdown, NEmpty, NIcon, NScrollbar, useDialog, useMessage } from 'naive-ui'
import type { DropdownOption } from 'naive-ui'
import { Download, FolderPlus, FilePlus, FileText, MoreHorizontal, Pencil, Trash2, Box, ChevronDown, ChevronRight, Upload } from 'lucide-vue-next'
import type { AutomationStore } from '@composables/automation/useAutomationStore'
import { readTextFile } from '@utils/readTextFile'
import { genId } from '@utils/id'
import IconButton from '@components/common/IconButton.vue'

const props = defineProps<{
  store: AutomationStore
  running: boolean
}>()

const { t } = useI18n()
const message = useMessage()
const dialog = useDialog()

// ---------------- 项目展开/收起 ----------------
// 展开状态与选中解耦：点箭头只开合，点名称才选中。选中某个项目时自动展开
// （保留「选中即展开」的旧手感），但之后可以手动收起，也能同时展开多个项目。
// 仅存在内存里（不持久化）：刷新后回到「当前项目展开」。
const expanded = ref<Set<string>>(new Set())

function expand(id: string) {
  if (!id || expanded.value.has(id)) return
  expanded.value = new Set([...expanded.value, id])
}
function collapse(id: string) {
  const next = new Set(expanded.value)
  next.delete(id)
  expanded.value = next
}
function toggleProject(id: string) {
  if (expanded.value.has(id)) collapse(id)
  else expand(id)
}
function isExpanded(id: string) {
  return expanded.value.has(id)
}

watch(
  () => props.store.selectedProjectId,
  (id) => { expand(id) },
  { immediate: true },
)

// ---------------- 行级三点菜单（收敛 hover 按钮） ----------------
const menuIcon = (icon: any) => () => h(NIcon, null, { default: () => h(icon) })

const projectMenuOptions: DropdownOption[] = [
  { label: t('automation.edit'), key: 'edit', icon: menuIcon(Pencil) },
  { label: t('automation.export'), key: 'export', icon: menuIcon(Download) },
  { label: t('automation.import'), key: 'import', icon: menuIcon(Upload) },
  { type: 'divider', key: 'd1' },
  { label: t('automation.delete'), key: 'delete', icon: menuIcon(Trash2), props: { style: 'color: var(--app-red)' } },
]

const scriptMenuOptions: DropdownOption[] = [
  { label: t('automation.edit'), key: 'edit', icon: menuIcon(Pencil) },
  { label: t('automation.export'), key: 'export', icon: menuIcon(Download) },
  { type: 'divider', key: 'd1' },
  { label: t('automation.delete'), key: 'delete', icon: menuIcon(Trash2), props: { style: 'color: var(--app-red)' } },
]

function onProjectMenu(key: string, p: any) {
  if (key === 'edit') props.store.openProjectMeta(p)
  else if (key === 'export') exportProject(p)
  else if (key === 'import') importScriptsTo(p)
  else if (key === 'delete') props.store.deleteProject(p)
}

function onScriptMenu(key: string, p: any, s: any) {
  if (key === 'edit') props.store.openScriptMeta(p.id, s)
  else if (key === 'export') exportScript(p, s)
  else if (key === 'delete') props.store.deleteScript(p.id, s.id)
}

// ---------------- 导入/导出（细粒度） ----------------
// 文件格式统一为 { projects: [...] }：导出项目 = 整个项目；导出脚本 =
// 只带该脚本的壳项目；导入按 id 合并（项目不存在则追加，脚本同名 id
// 则替换），绝不删除文件里没提到的数据——全量备份/单项目/单脚本通用。

function safeFileName(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_') || 'untitled'
}

async function saveJson(defaultName: string, data: unknown): Promise<boolean> {
  const api = window.electronAPI as any
  if (!api || typeof api.showSaveDialog !== 'function' || typeof api.writeFile !== 'function') {
    message.error('save dialog unavailable')
    return false
  }
  const res = await api.showSaveDialog({
    title: t('automation.export'),
    defaultPath: `${safeFileName(defaultName)}.json`,
    filters: [{ name: 'JSON', extensions: ['json'] }],
  })
  if (!res || res.canceled || !res.filePath) return false
  await api.writeFile(res.filePath, JSON.stringify(data, null, 2))
  message.success(t('automation.exportSuccess', { path: res.filePath }))
  return true
}

function exportProject(p: { name: string }) {
  void saveJson(p.name, { projects: [p] })
}

function exportScript(p: { name: string }, s: { name: string }) {
  // 壳项目只携带这一个脚本，导入时按脚本 id 合并，不会碰项目下其他脚本
  void saveJson(s.name, { projects: [{ ...p, scripts: [s] }] })
}

/** 弹文件选择框并解析出 projects[]；失败/取消返回 null（错误已提示） */
async function readProjectsFile(): Promise<any[] | null> {
  const api = window.electronAPI as any
  if (!api || typeof api.showOpenDialog !== 'function' || typeof api.readFile !== 'function') {
    message.error('open dialog unavailable')
    return null
  }
  const res = await api.showOpenDialog({
    title: t('automation.import'),
    properties: ['openFile'],
    filters: [{ name: 'JSON', extensions: ['json'] }],
  })
  if (!res || res.canceled || !res.filePaths || !res.filePaths.length) return null
  let text = ''
  try {
    // unwraps the { success, data } IPC envelope — raw readFile would land
    // JSON.parse on "[object Object]"
    text = await readTextFile(res.filePaths[0])
  } catch (e: any) {
    message.error(t('automation.importFailed', { msg: e?.message || String(e) }))
    return null
  }
  let parsed: any
  try {
    parsed = JSON.parse(text)
  } catch (e: any) {
    message.error(t('automation.importFailed', { msg: 'JSON: ' + (e?.message || e) }))
    return null
  }
  if (!parsed || !Array.isArray(parsed.projects) || !parsed.projects.length) {
    message.error(t('automation.importFailed', { msg: 'missing projects[]' }))
    return null
  }
  const { projects, skipped } = sanitizeProjects(parsed.projects)
  if (!projects.length) {
    message.error(t('automation.importFailed', { msg: 'no valid project' }))
    return null
  }
  // A hand-edited / half-truncated file must not silently import garbage into
  // the persisted config, but the valid part is still worth importing.
  if (skipped) message.warning(t('automation.importSkipped', { count: skipped }))
  return projects
}

/**
 * Validate + normalize an imported `projects[]`.
 *
 * The file is untrusted input: it may come from a colleague's build, be hand
 * edited, or be truncated. A project without an id/name (or a script whose
 * `steps` is not an array) used to be merged as-is, which pollutes the tree
 * and later makes the backend reject the run. Missing ids get a fresh one, so
 * merging by id stays meaningful.
 */
function sanitizeProjects(raw: any[]): { projects: any[]; skipped: number } {
  const projects: any[] = []
  let skipped = 0
  const asText = (v: unknown): string => (typeof v === 'string' ? v.trim() : '')

  for (const imp of raw) {
    if (!imp || typeof imp !== 'object' || Array.isArray(imp)) { skipped++; continue }
    const name = asText(imp.name)
    const scripts: any[] = []
    if (Array.isArray(imp.scripts)) {
      for (const s of imp.scripts) {
        if (!s || typeof s !== 'object' || Array.isArray(s)) { skipped++; continue }
        const sname = asText(s.name)
        if (!sname) { skipped++; continue }
        scripts.push({
          ...s,
          id: asText(s.id) || genId(),
          name: sname,
          updated_at: asText(s.updated_at) || new Date().toISOString(),
          // The backend executes `steps` directly — a non-array (a string, a
          // number, a truncated tail) must never reach it.
          steps: Array.isArray(s.steps) ? s.steps : [],
        })
      }
    }
    // A project shell with no scripts is legitimate (single-script export
    // writes one script under its project, and an empty project is valid UI
    // state), so only the NAME is required.
    if (!name) { skipped++; continue }
    projects.push({
      ...imp,
      id: asText(imp.id) || genId(),
      name,
      scripts,
    })
  }
  return { projects, skipped }
}

/** 收集文件里的全部脚本（项目壳或全量文件都适用） */
function collectScripts(projects: any[]): any[] {
  const out: any[] = []
  for (const imp of projects) {
    if (imp && Array.isArray(imp.scripts)) out.push(...imp.scripts)
  }
  return out
}

async function importConfig() {
  if (props.running) return
  const imported = await readProjectsFile()
  if (!imported) return

  // dry-run：统计合并影响（新增项目/脚本、被替换的同 id 脚本）
  let addedProjects = 0
  let addedScripts = 0
  let replacedScripts = 0
  for (const imp of imported) {
    if (!imp || !Array.isArray(imp.scripts)) continue
    const exist = props.store.projects.find((p) => p.id === imp.id)
    if (!exist) {
      addedProjects += 1
      addedScripts += imp.scripts.length
    } else {
      for (const s of imp.scripts) {
        if (exist.scripts.some((x) => x.id === s.id)) replacedScripts += 1
        else addedScripts += 1
      }
    }
  }
  if (!addedProjects && !addedScripts && !replacedScripts) {
    message.warning(t('automation.importNothing'))
    return
  }

  const apply = () => {
    for (const imp of imported) {
      if (!imp || !Array.isArray(imp.scripts)) continue
      const exist = props.store.projects.find((p) => p.id === imp.id)
      if (!exist) {
        props.store.projects.push(imp)
        continue
      }
      for (const s of imp.scripts) {
        const idx = exist.scripts.findIndex((x) => x.id === s.id)
        if (idx >= 0) exist.scripts.splice(idx, 1, s)
        else exist.scripts.push(s)
      }
    }
    props.store.persist()
    // 选中项的 id 在合并下始终有效（不删除任何既有项），但被替换的
    // 选中脚本需要刷新编辑器内容
    props.store.loadEditorFromSelection()
    message.success(t('automation.importDone', {
      projects: addedProjects,
      added: addedScripts,
      replaced: replacedScripts,
    }))
  }

  if (replacedScripts > 0) {
    dialog.warning({
      title: t('automation.import'),
      content: t('automation.importMerge', { replaced: replacedScripts, added: addedScripts }),
      positiveText: t('common.confirm'),
      negativeText: t('common.cancel'),
      onPositiveClick: apply,
    })
  } else {
    apply()
  }
}

/** 行级导入：把文件里的脚本合并进「这个」项目（目标由用户点选，不看
 *  文件里的项目 id——同事互发脚本时目标项目 id 对不上也能导入） */
async function importScriptsTo(p: { id: string; scripts: any[] }) {
  if (props.running) return
  const imported = await readProjectsFile()
  if (!imported) return
  const scripts = collectScripts(imported)
  if (!scripts.length) {
    message.warning(t('automation.importNothing'))
    return
  }

  let added = 0
  let replaced = 0
  for (const s of scripts) {
    if (p.scripts.some((x) => x.id === s.id)) replaced += 1
    else added += 1
  }
  if (!added && !replaced) {
    message.warning(t('automation.importNothing'))
    return
  }

  const apply = () => {
    for (const s of scripts) {
      const idx = p.scripts.findIndex((x) => x.id === s.id)
      if (idx >= 0) p.scripts.splice(idx, 1, s)
      else p.scripts.push(s)
    }
    props.store.persist()
    props.store.loadEditorFromSelection()
    message.success(t('automation.importDone', {
      projects: 0, added, replaced,
    }))
  }

  if (replaced > 0) {
    dialog.warning({
      title: t('automation.import'),
      content: t('automation.importMerge', { replaced, added }),
      positiveText: t('common.confirm'),
      negativeText: t('common.cancel'),
      onPositiveClick: apply,
    })
  } else {
    apply()
  }
}
</script>

<style scoped>
.col {
  background: var(--app-card-bg); border: 1px solid var(--app-card-border);
  border-radius: 10px; padding: 12px; display: flex; flex-direction: column; min-height: 0;
  min-width: 0;
}
.col-head {
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.col-empty { margin: auto; text-align: center; }
.empty-hint { margin-bottom: 8px; font-size: var(--app-font-size-sm); color: var(--app-text-muted); }

/* 滚动容器用 n-scrollbar（覆盖式滚动条不占宽度）→ 表头与行右边缘对齐 */
.tree { flex: 1; min-height: 0; }
.tree-body { display: flex; flex-direction: column; gap: 1px; }
.proj { margin-bottom: 2px; }

/* 项目行：箭头 | 名称(+描述) | 脚本数 | ⋮ */
.proj-row {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 6px; border-radius: 7px; cursor: pointer;
}
/* 两级选中态区分：项目行 = 「当前项目」（中性底 + 左侧强调条），
   脚本行 = 「正在编辑」（蓝底 + 强调条）。 */
.proj-row.current {
  background: var(--app-hover);
  box-shadow: inset 2px 0 0 var(--app-blue);
}
.proj-caret {
  flex: none; display: flex; align-items: center; justify-content: center;
  width: 18px; padding: 0; border: 0; background: none; cursor: pointer;
  color: var(--app-text-dim);
}
.proj-caret:hover { color: var(--app-text-primary); }
.proj-main { flex: 1; min-width: 0; }
.proj-name { display: flex; align-items: center; gap: 5px; font-weight: 600; font-size: var(--app-font-size-md); color: var(--app-text-primary); overflow: hidden; min-width: 0; }
.proj-name span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row-actions { display: flex; gap: 1px; opacity: 0; flex: none; }
.proj-row:hover .row-actions,
.proj-row.current .row-actions { opacity: 1; }
/* 可见备注行：与名字后的图标对齐（箭头 18 + gap 6 + 图标 14 + gap 5） */
.item-desc {
  font-size: var(--app-font-size-xs); color: var(--app-text-muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.proj-desc { padding: 1px 0 4px 19px; }
.scripts { margin: 2px 0 6px 20px; display: flex; flex-direction: column; gap: 1px; }
.scripts-empty {
  font-size: var(--app-font-size-xs); color: var(--app-text-dim);
  padding: 3px 6px 5px;
}
.script-row {
  display: flex; align-items: center; gap: 5px; padding: 4px 6px; border-radius: 6px;
  cursor: pointer; font-size: var(--app-font-size-sm); color: var(--app-text-secondary);
}
.script-row.active {
  background: var(--app-blue-bg); color: var(--app-text-primary);
  box-shadow: inset 2px 0 0 var(--app-blue);
}
.script-main { flex: 1; min-width: 0; }
.script-main .name-line {
  display: block;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.script-desc { padding: 1px 0 2px 19px; } /* 图标 14px + gap 5px */
.script-ops { opacity: 0; flex: none; }
.script-row:hover .script-ops,
.script-row.active .script-ops { opacity: 1; }
</style>
