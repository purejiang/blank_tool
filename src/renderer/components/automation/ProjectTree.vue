<template>
  <section class="col col-left">
    <div class="col-head">
      <span>{{ t('automation.projects') }}</span>
      <div class="head-actions">
        <n-tooltip trigger="hover" placement="bottom">
          <template #trigger>
            <n-button size="tiny" tertiary :disabled="running" :title="t('automation.import')" @click="importConfig">
              <template #icon><n-icon><Upload /></n-icon></template>
            </n-button>
          </template>
          {{ t('automation.importMergeHint') }}
        </n-tooltip>
        <n-button size="tiny" tertiary type="primary" :disabled="running" @click="store.newProject">
          <template #icon><n-icon><FolderPlus /></n-icon></template>
        </n-button>
      </div>
    </div>

    <n-empty v-if="!store.projects.length" :description="t('automation.noProject')" size="small" class="col-empty">
      <template #extra>
        <span class="muted">{{ t('automation.noProjectDesc') }}</span>
      </template>
    </n-empty>

    <div v-else class="tree">
      <div v-for="p in store.projects" :key="p.id" class="proj">
        <div class="proj-row" :class="{ active: p.id === store.selectedProjectId }">
          <div class="proj-name" @click="store.selectProject(p.id)">
            <n-icon size="14"><Box /></n-icon>
            <span class="name-line" :title="p.description ? `${p.name} · ${p.description}` : p.name">{{ p.name }}</span>
          </div>
          <div class="row-actions">
            <n-button size="tiny" text type="primary" :disabled="running" :title="t('automation.editInfo')" @click.stop="store.openProjectMeta(p)">
              <template #icon><n-icon><Pencil /></n-icon></template>
            </n-button>
            <n-button size="tiny" text type="primary" :disabled="running" :title="t('automation.exportProject')" @click.stop="exportProject(p)">
              <template #icon><n-icon><Download /></n-icon></template>
            </n-button>
            <n-button size="tiny" text type="error" :disabled="running" @click.stop="store.deleteProject(p)">
              <template #icon><n-icon><Trash2 /></n-icon></template>
            </n-button>
          </div>
        </div>

        <div v-if="p.id === store.selectedProjectId" class="scripts">
          <div
            v-for="s in p.scripts"
            :key="s.id"
            class="script-row"
            :class="{ active: s.id === store.selectedScriptId }"
            @click="store.selectScript(p.id, s.id)"
          >
            <n-icon size="13"><FileText /></n-icon>
            <span
              class="name-line"
              :title="s.description ? `${s.name} · ${s.description}` : s.name"
            >{{ s.name }}</span>
            <n-button
              size="tiny"
              text
              type="primary"
              class="script-ops"
              :disabled="running"
              :title="t('automation.editInfo')"
              @click.stop="store.openScriptMeta(p.id, s)"
            >
              <template #icon><n-icon><Pencil /></n-icon></template>
            </n-button>
            <n-button
              size="tiny"
              text
              type="primary"
              class="script-ops"
              :disabled="running"
              :title="t('automation.exportScript')"
              @click.stop="exportScript(p, s)"
            >
              <template #icon><n-icon><Download /></n-icon></template>
            </n-button>
            <n-button
              size="tiny"
              text
              type="error"
              class="script-ops"
              :disabled="running"
              @click.stop="store.deleteScript(p.id, s.id)"
            >
              <template #icon><n-icon><Trash2 /></n-icon></template>
            </n-button>
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
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NEmpty, NIcon, NTooltip, useDialog, useMessage } from 'naive-ui'
import { Download, FolderPlus, FilePlus, FileText, Pencil, Trash2, Box, Upload } from 'lucide-vue-next'
import type { AutomationStore } from '@composables/automation/useAutomationStore'

const props = defineProps<{
  store: AutomationStore
  running: boolean
}>()

const { t } = useI18n()
const message = useMessage()
const dialog = useDialog()

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

async function importConfig() {
  if (props.running) return
  const api = window.electronAPI as any
  if (!api || typeof api.showOpenDialog !== 'function' || typeof api.readFile !== 'function') {
    message.error('open dialog unavailable')
    return
  }
  const res = await api.showOpenDialog({
    title: t('automation.import'),
    properties: ['openFile'],
    filters: [{ name: 'JSON', extensions: ['json'] }],
  })
  if (!res || res.canceled || !res.filePaths || !res.filePaths.length) return
  let text = ''
  try {
    text = await api.readFile(res.filePaths[0])
  } catch (e: any) {
    message.error(t('automation.importFailed', { msg: e?.message || String(e) }))
    return
  }
  let parsed: any
  try {
    parsed = JSON.parse(text)
  } catch (e: any) {
    message.error(t('automation.importFailed', { msg: 'JSON: ' + (e?.message || e) }))
    return
  }
  if (!parsed || !Array.isArray(parsed.projects) || !parsed.projects.length) {
    message.error(t('automation.importFailed', { msg: 'missing projects[]' }))
    return
  }

  // dry-run：统计合并影响（新增项目/脚本、被替换的同 id 脚本）
  let addedProjects = 0
  let addedScripts = 0
  let replacedScripts = 0
  for (const imp of parsed.projects) {
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
    for (const imp of parsed.projects) {
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
</script>

<style scoped>
.col {
  background: var(--app-card-bg); border: 1px solid var(--app-card-border);
  border-radius: 10px; padding: 12px; display: flex; flex-direction: column; min-height: 0;
  min-width: 0;
}
.col-head {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px; font-weight: 600; color: var(--app-text-primary);
  margin-bottom: 10px;
}
.head-actions { display: flex; align-items: center; gap: 4px; }
.col-empty { margin: auto; text-align: center; }
.muted { color: var(--app-text-muted); font-size: 12px; }

.tree { overflow: auto; flex: 1; }
.proj { margin-bottom: 2px; }
.proj-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 6px; border-radius: 7px; cursor: pointer;
}
.proj-row.active { background: var(--app-blue-bg); }
.proj-name { display: flex; align-items: center; gap: 5px; font-weight: 600; font-size: 12.5px; color: var(--app-text-primary); overflow: hidden; min-width: 0; }
.proj-name span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row-actions { display: flex; gap: 1px; opacity: 0; flex: none; }
.proj-row:hover .row-actions { opacity: 1; }
.scripts { margin: 2px 0 6px 12px; display: flex; flex-direction: column; gap: 1px; }
.script-row {
  display: flex; align-items: center; gap: 5px; padding: 3px 6px; border-radius: 6px;
  cursor: pointer; font-size: 12px; color: var(--app-text-secondary);
}
.script-row.active { background: var(--app-blue-bg); color: var(--app-text-primary); }
.script-row .name-line {
  flex: 1; min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.script-ops { opacity: 0; flex: none; }
.script-row:hover .script-ops { opacity: 1; }
</style>
