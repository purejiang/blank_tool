<template>
  <aside class="workflow-node-palette">
    <div class="wnp-header">{{ t('workflow.editor.palette.title') }}</div>
    <div class="wnp-body">
      <div v-if="loading" class="wnp-status-text">Loading tools…</div>
      <div v-else-if="error" class="wnp-status-text wnp-status-error" :title="error">
        Failed to load tools
      </div>
      <div v-else-if="tools.length === 0" class="wnp-status-text">No tools available</div>
      <template v-else>
        <div v-for="group in groups" :key="group.key" class="wnp-group">
          <div class="wnp-group-label">{{ t('workflow.editor.palette.groups.' + group.key) }}</div>
          <div
            v-for="tool in group.tools"
            :key="tool.name"
            class="wnp-item"
            :class="{ 'wnp-item-invalid': !tool.is_valid }"
            draggable="true"
            :title="tool.is_valid ? 'Drag onto the canvas to add a node' : 'Tool unavailable (environment or binary missing)'"
            @dragstart="onDragStart($event, tool)"
          >
            <div class="wnp-item-head">
              <span class="wnp-item-name">{{ tool.name }}</span>
              <span
                class="wnp-valid-dot"
                :class="tool.is_valid ? 'wnp-valid-ok' : 'wnp-valid-bad'"
              />
            </div>
            <div class="wnp-item-desc">{{ describe(tool) }}</div>
          </div>
        </div>
      </template>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import unifiedApi from '@/api/unifiedApi'
import { log } from '@utils/logger'
import { TOOL_DRAG_MIME, groupWorkflowTools, type WorkflowToolInfo } from './toolMeta'

const { t } = useI18n()

const tools = ref<WorkflowToolInfo[]>([])
const loading = ref(false)
const error = ref('')

async function loadTools() {
  loading.value = true
  error.value = ''
  try {
    // workflow.list_tools returns { tools: [...] } — descriptor/code tools
    // from ToolManager plus the builtin workflow primitives (ports + builtin
    // flag are only present for builtins).
    const result = await unifiedApi.call<{ tools?: WorkflowToolInfo[] }>('workflow.list_tools', {})
    tools.value = Array.isArray(result?.tools) ? result.tools : []
  } catch (err) {
    log.error('Failed to load workflow tools:', err)
    error.value = err instanceof Error ? err.message : String(err)
    tools.value = []
  } finally {
    loading.value = false
  }
}

// Grouping by `kind` (shipped-native → builtin group, native/descriptor →
// plugins group), with legacy `builtin` fallback — see toolMeta.groupWorkflowTools.
// Group labels are rendered via i18n (workflow.editor.palette.groups.*).
const groups = computed(() => groupWorkflowTools(tools.value))

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
  return 'workflow tool'
}

function onDragStart(event: DragEvent, tool: WorkflowToolInfo) {
  if (!event.dataTransfer) return
  event.dataTransfer.setData(TOOL_DRAG_MIME, JSON.stringify(tool))
  event.dataTransfer.effectAllowed = 'move'
}

onMounted(loadTools)
</script>

<style scoped>
.workflow-node-palette {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: 220px;
  overflow: hidden;
  background: var(--palette-bg);
  border: 1px solid var(--node-border);
  border-radius: 6px;
  color: var(--palette-text);
}

.wnp-header {
  padding: 10px 12px;
  border-bottom: 1px solid var(--node-border);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--app-text-secondary);
}

.wnp-body {
  flex: 1;
  overflow-y: auto;
  padding: 6px 0;
}

.wnp-status-text {
  padding: 12px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.wnp-status-error {
  color: var(--app-red);
}

.wnp-group {
  display: flex;
  flex-direction: column;
}

.wnp-group-label {
  padding: 8px 12px 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--app-text-dim);
}

.wnp-item {
  padding: 6px 12px;
  cursor: grab;
  border-left: 2px solid transparent;
  user-select: none;
}

.wnp-item:hover {
  background: var(--app-hover);
  border-left-color: var(--app-text-dim);
}

.wnp-item:active {
  cursor: grabbing;
}

.wnp-item-invalid {
  opacity: 0.6;
}

.wnp-item-head {
  display: flex;
  gap: 6px;
  align-items: center;
}

.wnp-item-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  font-weight: 500;
  color: var(--app-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wnp-valid-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.wnp-valid-ok {
  background: var(--app-green);
}

.wnp-valid-bad {
  background: var(--app-red);
}

.wnp-item-desc {
  margin-top: 2px;
  overflow: hidden;
  font-size: 11px;
  color: var(--app-text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
