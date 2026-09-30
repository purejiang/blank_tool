<template>
  <!--
    工具（节点）面板。版式逐字取自 docs/ui-prompts/ui-preview.html 的
    `.pal` / `.pal-scroll` / `.pal-grp` / `.tool-row`（这些类已在
    assets/styles/preview-layout.css 里，挂在 `.pv` 作用域下），所以组件里
    只保留必要的尺寸覆盖，不再自己造一套 `.wnp-*` 视觉。

    分组键 = 工具域（文件/网络/执行/流程/其它），每组可折叠并显示条数。
    插件不再单独成组（那会让 `file.read` 和插件 `file.pack` 分家），改成
    条目上的「插件」标记 —— 见 toolMeta.isBuiltinTool。
  -->
  <div class="workflow-node-palette">
    <div class="pal">
      <label class="search pal-search">
        <AppIcon name="search" size="sm" />
        <input
          v-model="query"
          type="text"
          :placeholder="t('workflow.editor.palette.search')"
          :aria-label="t('workflow.editor.palette.search')"
        />
      </label>
    </div>

    <div class="pal-scroll">
      <div v-if="loading" class="pal-status">{{ t('workflow.editor.palette.loading') }}</div>
      <div v-else-if="error" class="pal-status pal-status--error" :title="error">
        {{ t('workflow.editor.palette.loadFailed') }}
      </div>
      <div v-else-if="tools.length === 0" class="pal-status">
        {{ t('workflow.editor.palette.noTools') }}
      </div>
      <div v-else-if="visibleGroups.length === 0" class="pal-status">
        {{ t('workflow.editor.palette.noMatch') }}
      </div>

      <template v-else>
        <div v-for="group in visibleGroups" :key="group.key" class="pal-block">
          <button
            type="button"
            class="pal-grp pal-grp-btn"
            :aria-expanded="isOpen(group.key)"
            @click="toggleGroup(group.key)"
          >
            <AppIcon
              name="arrow-r"
              size="sm"
              class="pal-caret"
              :class="{ 'is-open': isOpen(group.key) }"
            />
            <span class="pal-grp-text">
              {{ t('workflow.editor.palette.groups.' + group.key) }}
            </span>
            <span class="pal-grp-count">{{ group.tools.length }}</span>
          </button>

          <template v-if="isOpen(group.key)">
            <div
              v-for="tool in group.tools"
              :key="tool.name"
              class="tool-row"
              :class="{ off: !tool.is_valid }"
              :draggable="tool.is_valid ? 'true' : 'false'"
              :title="
                tool.is_valid
                  ? `${describe(tool)} · ${t('workflow.editor.palette.dragHint')}`
                  : t('workflow.editor.palette.dragHintInvalid')
              "
              @dragstart="onDragStart($event, tool)"
              @click="onAppend(tool)"
            >
              <span class="ti"><AppIcon :name="iconFor(tool)" size="sm" /></span>
              <span class="tt">
                <span class="tn">
                  {{ tool.name }}
                  <span v-if="!isBuiltinTool(tool)" class="tag-plugin">
                    {{ t('workflow.editor.palette.pluginTag') }}
                  </span>
                </span>
                <div class="td">{{ describe(tool) }}</div>
              </span>
              <span class="grip">
                <AppIcon :name="tool.is_valid ? 'grip' : 'ban'" size="sm" />
              </span>
            </div>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import unifiedApi from '@/api/unifiedApi'
import AppIcon from '@components/ui/AppIcon.vue'
import { log } from '@utils/logger'
import {
  CATEGORY_ICONS,
  TOOL_DRAG_MIME,
  categoryOfToolName,
  groupWorkflowTools,
  isBuiltinTool,
  type WorkflowGroupKey,
  type WorkflowToolInfo,
} from './toolMeta'

/**
 * Tool palette. Drag-and-drop onto the canvas (original MVP) plus
 * click-to-append (the page decides where "the end of the chain" is) and a
 * name filter. Invalid tools are not draggable — the environment/binary they
 * need is missing, so a node would only fail at run time.
 */
const emit = defineEmits<{
  (e: 'append', tool: WorkflowToolInfo): void
}>()

const { t } = useI18n()

const tools = ref<WorkflowToolInfo[]>([])
const loading = ref(false)
const error = ref('')
const query = ref('')

/** Groups the user collapsed (empty = everything open). */
const collapsed = ref(new Set<WorkflowGroupKey>())

async function loadTools() {
  loading.value = true
  error.value = ''
  try {
    // tool.list returns { tools: [...] } — descriptor/code tools
    // from ToolManager plus the builtin workflow primitives (ports + builtin
    // flag are only present for builtins).
    const result = await unifiedApi.call<{ tools?: WorkflowToolInfo[] }>('tool.list', {})
    tools.value = Array.isArray(result?.tools) ? result.tools : []
  } catch (err) {
    log.error('Failed to load workflow tools:', err)
    error.value = err instanceof Error ? err.message : String(err)
    tools.value = []
  } finally {
    loading.value = false
  }
}

// Grouping by domain — see toolMeta.groupWorkflowTools. Group labels are
// rendered via i18n (workflow.editor.palette.groups.*).
const groups = computed(() => groupWorkflowTools(tools.value))

/** True while a search is active: matches win over the manual collapse state. */
const searching = computed(() => query.value.trim().length > 0)

/** Case-insensitive name/description filter; empty groups drop out. */
const visibleGroups = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return groups.value
  return groups.value
    .map((group) => ({
      ...group,
      tools: group.tools.filter(
        (tool) =>
          tool.name.toLowerCase().includes(needle) ||
          (tool.description ?? '').toLowerCase().includes(needle),
      ),
    }))
    .filter((group) => group.tools.length > 0)
})

function isOpen(key: WorkflowGroupKey): boolean {
  return searching.value || !collapsed.value.has(key)
}

function toggleGroup(key: WorkflowGroupKey) {
  const next = new Set(collapsed.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  collapsed.value = next
}

/** Category icon for a palette row (same mapping the canvas node uses). */
function iconFor(tool: WorkflowToolInfo): string {
  return CATEGORY_ICONS[categoryOfToolName(tool.name)]
}

/**
 * One-line description for the palette entry. The backend payload has no
 * description field yet, so fall back to a port summary (builtins) or the
 * tool path / version (descriptor tools); use `description` when present.
 */
function describe(tool: WorkflowToolInfo): string {
  if (tool.description) return tool.description
  if (tool.ports) return `${tool.ports.inputs.length} in / ${tool.ports.outputs.length} out`
  if (tool.tool_path) return tool.tool_path.split(/[\\/]/).pop() || tool.tool_path
  if (tool.version) return `v${tool.version}`
  return t('workflow.editor.palette.genericTool')
}

function onDragStart(event: DragEvent, tool: WorkflowToolInfo) {
  if (!tool.is_valid) {
    event.preventDefault()
    return
  }
  if (!event.dataTransfer) return
  event.dataTransfer.setData(TOOL_DRAG_MIME, JSON.stringify(tool))
  event.dataTransfer.effectAllowed = 'move'
}

function onAppend(tool: WorkflowToolInfo) {
  if (!tool.is_valid) return
  emit('append', tool)
}

onMounted(loadTools)
</script>

<style scoped>
/* Fills the editor's `.ed-left` column (the page owns the 240px width and the
   right-hand 1px divider). */
.workflow-node-palette {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

/* `.pv .search` is 260px wide (list-page toolbar palette); the sidebar wants
   the full column. Compound scoped selector so it beats `.pv .search` (0,2,0)
   regardless of stylesheet injection order. */
.workflow-node-palette .pal-search {
  width: 100%;
  flex: 1;
}

.pal-status {
  padding: 12px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.pal-status--error {
  color: var(--app-red);
}

.pal-block {
  display: flex;
  flex-direction: column;
}

/* `.pal-grp` is the preview's group caption; here it doubles as a collapse
   button, so the UA button chrome has to go. */
.pal-grp-btn {
  display: flex;
  gap: 6px;
  align-items: center;
  width: 100%;
  padding: 0;
  font: inherit;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 0;
}

.pal-grp-btn:hover .pal-grp-text {
  color: var(--app-text-secondary);
}

.pal-caret {
  flex: none;
  transition: transform 0.12s ease;
}

.pal-caret.is-open {
  transform: rotate(90deg);
}

.pal-grp-text {
  flex: 1;
  min-width: 0;
}

.pal-grp-count {
  flex: none;
  font-family: var(--font-family-monospace);
  font-size: 10px;
  color: var(--app-text-muted);
}

.tag-plugin {
  margin-left: 6px;
  padding: 0 5px;
  font-family: var(--font-family-base);
  font-size: 10px;
  color: var(--app-text-dim);
  background: var(--app-hover);
  border-radius: var(--radius-pill);
}
</style>
