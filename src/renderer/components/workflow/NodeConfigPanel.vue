<template>
  <div class="node-config-panel">
    <div v-if="!node" class="npc-empty">{{ t('workflow.editor.config.noSelection') }}</div>
    <template v-else>
      <!-- Tool identity -->
      <div class="npc-identity">
        <div class="npc-tool-name">{{ toolName }}</div>
        <div v-if="description" class="npc-tool-desc">{{ description }}</div>
      </div>

      <div class="npc-body">
        <!-- Input ports → editable params -->
        <div class="npc-section">
          <div class="npc-section-title">Parameters</div>
          <div v-if="inputPorts.length === 0" class="npc-empty-inline">No parameters</div>
          <n-form v-else :model="draft" label-placement="top" size="small">
            <n-form-item
              v-for="port in inputPorts"
              :key="port.name"
              :label="port.name"
              :required="isRequired(port)"
            >
              <!-- file / directory: text input + native picker button -->
              <div v-if="isPathPort(port)" class="npc-path-row">
                <n-input
                  v-model:value="draft[port.name]"
                  class="npc-path-input"
                  size="small"
                  :placeholder="portTypeOf(port) === 'directory' ? '/path/to/folder' : '/path/to/file'"
                />
                <n-button size="small" @click="browsePath(port)">Browse</n-button>
              </div>
              <!-- boolean -->
              <n-switch
                v-else-if="portTypeOf(port) === 'boolean'"
                v-model:value="draft[port.name]"
              />
              <!-- number -->
              <n-input-number
                v-else-if="portTypeOf(port) === 'number'"
                v-model:value="draft[port.name]"
                class="npc-full"
                size="small"
                :show-button="false"
                placeholder="0"
              />
              <!-- json: monospace textarea -->
              <n-input
                v-else-if="portTypeOf(port) === 'json'"
                v-model:value="draft[port.name]"
                class="npc-mono"
                size="small"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 8 }"
                placeholder='{ "key": "value" }'
              />
              <!-- text / unknown: textarea for longer values -->
              <n-input
                v-else
                v-model:value="draft[port.name]"
                size="small"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
                placeholder="Text value (expressions are typed as plain text)"
              />
              <template v-if="port.description" #feedback>
                <span class="npc-port-desc">{{ port.description }}</span>
              </template>
            </n-form-item>
          </n-form>
        </div>

        <!-- Output ports: read-only -->
        <div v-if="outputPorts.length > 0" class="npc-section">
          <div class="npc-section-title">Outputs</div>
          <div class="npc-outputs">
            <div
              v-for="port in outputPorts"
              :key="port.name"
              class="npc-output-row"
              :title="port.description || ''"
            >
              <span class="npc-dot" :class="`npc-dot--${portTypeOf(port)}`" />
              <span class="npc-output-name">{{ port.name }}</span>
              <span class="npc-output-type">{{ typeLabel(port) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Commit draft values to node.data.params -->
      <div class="npc-footer">
        <n-button size="small" type="primary" :disabled="!dirty" @click="save">Save</n-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NForm, NFormItem, NInput, NInputNumber, NSwitch, NButton } from 'naive-ui'
import type { Node } from '@vue-flow/core'
import serviceManager from '@services/ServiceManager'
import { log } from '@utils/logger'
import type { ToolNodeData, ToolPorts } from './toolMeta'

const { t } = useI18n()

/**
 * Loose port shape accepted by this panel. Todo 34's `ToolPort` (toolMeta.ts,
 * mirroring backend `Port.to_dict()`) is structurally assignable to it; the
 * looser form also tolerates bare base-name type strings or missing fields
 * (e.g. nodes rebuilt by the todo 37 deserializer) without crashing.
 */
interface LoosePort {
  name: string
  type?: string | { base?: string; subtype?: string | null }
  required?: boolean
  description?: string
}

const props = defineProps<{
  /** Selected vue-flow node; null/undefined when nothing is selected. */
  node?: Node | null
}>()

// ---- node data accessors ---------------------------------------------
// Node payload contract is toolMeta.ts `ToolNodeData`:
//   { tool, status?, ports?: { inputs, outputs }, params? (added here) }

const nodeData = computed<Record<string, any>>(() => (props.node?.data ?? {}) as Record<string, any>)

const toolName = computed<string>(() => {
  const d = nodeData.value
  return String(d.tool || d.toolName || d.label || props.node?.id || 'Unknown tool')
})

const description = computed<string>(() => {
  const desc = nodeData.value.description
  return typeof desc === 'string' ? desc : ''
})

function toPorts(raw: unknown): LoosePort[] {
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (p): p is LoosePort => !!p && typeof p === 'object' && typeof (p as LoosePort).name === 'string',
  )
}

/** Prefer todo 34's nested data.ports; tolerate flat data.inputs/outputs. */
const ports = computed<ToolPorts | null>(() => {
  const d = nodeData.value
  if (d.ports && typeof d.ports === 'object') return d.ports as ToolPorts
  if (Array.isArray(d.inputs) || Array.isArray(d.outputs)) {
    return { inputs: d.inputs, outputs: d.outputs } as ToolPorts
  }
  return null
})

const inputPorts = computed<LoosePort[]>(() => toPorts(ports.value?.inputs))
const outputPorts = computed<LoosePort[]>(() => toPorts(ports.value?.outputs))

// ---- port type helpers -------------------------------------------------

const KNOWN_BASE_TYPES = ['file', 'directory', 'text', 'number', 'boolean', 'json']

function portTypeOf(port: LoosePort): string {
  const t = port.type
  let base = ''
  if (typeof t === 'string') base = t
  else if (t && typeof t === 'object' && typeof t.base === 'string') base = t.base
  base = base.toLowerCase()
  // Unknown/missing types degrade to a plain text field (advisory typing, D7).
  return KNOWN_BASE_TYPES.includes(base) ? base : 'text'
}

function typeLabel(port: LoosePort): string {
  const base = portTypeOf(port)
  const t = port.type
  if (t && typeof t === 'object' && typeof t.subtype === 'string' && t.subtype) {
    return `${base}/${t.subtype}`
  }
  return base
}

function isRequired(port: LoosePort): boolean {
  // Backend Port defaults to required=True when the flag is absent.
  return port.required !== false
}

function isPathPort(port: LoosePort): boolean {
  const t = portTypeOf(port)
  return t === 'file' || t === 'directory'
}

// ---- draft editing + save ----------------------------------------------

const draft = reactive<Record<string, any>>({})
const snapshot = ref('')

function emptyValueFor(base: string): unknown {
  if (base === 'boolean') return false
  if (base === 'number') return null
  return ''
}

/** Reload the draft from node.data.params whenever another node is selected. */
function resetDraft() {
  for (const key of Object.keys(draft)) delete draft[key]
  const stored = nodeData.value.params
  for (const port of inputPorts.value) {
    let value = stored ? stored[port.name] : undefined
    if (value !== undefined && value !== null && typeof value === 'object') {
      value = JSON.stringify(value, null, 2)
    }
    draft[port.name] = value !== undefined && value !== null ? value : emptyValueFor(portTypeOf(port))
  }
  snapshot.value = JSON.stringify(draft)
}

watch(() => props.node?.id, resetDraft, { immediate: true })

const dirty = computed(() => JSON.stringify(draft) !== snapshot.value)

/** Commit the draft into node.data.params (replaces any previous params). */
function save() {
  const node = props.node
  if (!node || !dirty.value) return
  const data = node.data as ToolNodeData
  const params: Record<string, unknown> = {}
  for (const port of inputPorts.value) {
    const value = draft[port.name]
    // Skip empty values so unset params stay absent in the workflow JSON.
    if (value === undefined || value === null || value === '') continue
    params[port.name] = value
  }
  data.params = params
  snapshot.value = JSON.stringify(draft)
}

// ---- native path pickers -------------------------------------------------

async function browsePath(port: LoosePort) {
  const isDir = portTypeOf(port) === 'directory'
  try {
    const svc = (await serviceManager.getService('system')) as any
    const res = isDir
      ? await svc.selectDirectory({ title: `Select ${port.name}` })
      : await svc.selectFile({ title: `Select ${port.name}` })
    if (res && !res.canceled) {
      const p = (res.filePath || (res.filePaths && res.filePaths[0]) || '').trim()
      if (p) draft[port.name] = p
    }
  } catch (error) {
    log.error('NodeConfigPanel: path picker failed', error)
  }
}
</script>

<style scoped>
.node-config-panel {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  background: var(--config-panel-bg);
}

.npc-empty {
  padding: 12px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.npc-identity {
  padding: 12px;
  border-bottom: 1px solid var(--node-border);
}

.npc-tool-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
  word-break: break-all;
}

.npc-tool-desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--app-text-secondary);
}

.npc-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  padding: 12px;
  overflow-y: auto;
}

.npc-section-title {
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--app-text-secondary);
  text-transform: uppercase;
}

.npc-empty-inline {
  font-size: 12px;
  color: var(--app-text-muted);
}

.npc-path-row {
  display: flex;
  gap: 6px;
  width: 100%;
}

.npc-path-input {
  flex: 1;
  min-width: 0;
}

.npc-full {
  width: 100%;
}

.npc-mono :deep(.n-input__textarea-el) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
}

.npc-port-desc {
  font-size: 11px;
  color: var(--app-text-dim);
}

.npc-outputs {
  display: flex;
  flex-direction: column;
}

.npc-output-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
}

.npc-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--app-text-muted);
}

.npc-dot--file {
  background: var(--app-blue);
}

.npc-dot--text {
  background: var(--app-green);
}

.npc-dot--json {
  /* --app-orange added alongside todo 34's port palette; yellow fallback */
  background: var(--app-orange, var(--app-yellow));
}

.npc-dot--number {
  /* --app-purple added alongside todo 34's port palette; muted fallback */
  background: var(--app-purple, var(--app-text-muted));
}

.npc-output-name {
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  color: var(--app-text-primary);
}

.npc-output-type {
  margin-left: auto;
  font-size: 11px;
  color: var(--app-text-muted);
}

.npc-footer {
  display: flex;
  justify-content: flex-end;
  padding: 10px 12px;
  border-top: 1px solid var(--node-border);
}
</style>
