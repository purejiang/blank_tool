<template>
  <section class="col col-left">
    <div class="col-head">
      <span>{{ t('automation.projects') }}</span>
      <n-button size="tiny" tertiary type="primary" :disabled="running" @click="store.newProject">
        <template #icon><n-icon><FolderPlus /></n-icon></template>
      </n-button>
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
import { NButton, NEmpty, NIcon } from 'naive-ui'
import { FolderPlus, FilePlus, FileText, Pencil, Trash2, Box } from 'lucide-vue-next'
import type { AutomationStore } from '@composables/automation/useAutomationStore'

defineProps<{
  store: AutomationStore
  running: boolean
}>()

const { t } = useI18n()
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
