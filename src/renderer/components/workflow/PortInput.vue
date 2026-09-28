<template>
  <!-- Single typed control for a port + expression-binding affordances.
       Used by the node config panel and the run-inputs dialog, so the typed
       widget matrix lives in exactly one place. -->
  <div class="port-input">
    <!-- file / directory: text input + native picker -->
    <div v-if="isPath" class="pi-path-row">
      <n-input
        :value="asText"
        size="small"
        class="pi-path-input"
        :disabled="disabled"
        :placeholder="resolvedPlaceholder"
        @update:value="emit('update:value', $event)"
      />
      <n-button size="small" :disabled="disabled" @click="browsePath">
        {{ t('workflow.editor.dialog.browse') }}
      </n-button>
    </div>

    <!-- boolean -->
    <n-switch
      v-else-if="kind === 'boolean' && !boundText"
      :value="value === true"
      :disabled="disabled"
      @update:value="emit('update:value', $event)"
    />

    <!-- number -->
    <n-input-number
      v-else-if="kind === 'number' && !boundText"
      :value="asNumber"
      class="pi-full"
      size="small"
      :show-button="false"
      :disabled="disabled"
      :placeholder="resolvedPlaceholder"
      @update:value="emit('update:value', $event)"
    />

    <!-- multi-select (arrays cannot carry a single expression) -->
    <n-select
      v-else-if="kind === 'multi_select'"
      :value="asArray"
      size="small"
      multiple
      :disabled="disabled"
      :options="selectOptions"
      @update:value="emit('update:value', $event)"
    />

    <!-- single-select (an expression can replace the chosen option) -->
    <n-select
      v-else-if="kind === 'single_select' && !boundText"
      :value="asText || null"
      size="small"
      :disabled="disabled"
      :options="selectOptions"
      @update:value="emit('update:value', $event)"
    />

    <!-- json -->
    <n-input
      v-else-if="kind === 'json' && !boundText"
      :value="asText"
      class="pi-mono"
      size="small"
      type="textarea"
      :autosize="{ minRows: 3, maxRows: 8 }"
      :disabled="disabled"
      :placeholder="resolvedPlaceholder"
      @update:value="emit('update:value', $event)"
    />

    <!-- text, or a typed port currently holding a binding (edited as text) -->
    <n-input
      v-else
      :value="asText"
      :class="{ 'pi-mono': kind === 'json' || boundText }"
      size="small"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 6 }"
      :disabled="disabled"
      :placeholder="resolvedPlaceholder"
      @update:value="emit('update:value', $event)"
    />

    <!-- Binding row: chips + insert picker + inline validation -->
    <div v-if="bindingsEnabled" class="pi-bind">
      <div class="pi-bind-head">
        <ExpressionPicker
          v-model:show="pickerOpen"
          :inputs="inputs"
          :upstream-nodes="upstreamNodes"
          :trigger="trigger"
          :disabled="disabled"
          @pick="onPick"
        />
        <div v-if="tokens.length > 0" class="pi-chips">
          <span v-for="token in tokens" :key="`${token.start}-${token.raw}`" class="pi-chip">
            <code>{{ token.raw }}</code>
            <button
              type="button"
              class="pi-chip-remove"
              :title="t('workflow.editor.binding.remove')"
              @click="removeToken(token)"
            >
              ×
            </button>
          </span>
        </div>
      </div>
      <div v-for="(item, index) in issues" :key="`${item.code}-${index}`" class="pi-issue" :class="`pi-issue--${item.severity}`">
        {{ t(item.messageKey, item.params ?? {}) }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NInputNumber, NSelect, NSwitch } from 'naive-ui'

import ExpressionPicker from './ExpressionPicker.vue'
import {
  collectBindings,
  findTrigger,
  insertBinding,
  removeBinding,
  validateValue,
  type BindingContext,
  type BindingIssue,
  type BindingToken,
  type BindingTrigger,
} from './expressionBinding'
import { portJsonToTypeKey, type PortTypeKey } from './ioAuthoring'
import type { UpstreamNodeRef } from './toolMeta'
import type { PortJSON } from './serializer'
import serviceManager from '@services/ServiceManager'
import { log } from '@utils/logger'

/** Loose port shape (tolerates bare base strings and absent fields). */
export interface PortInputPort {
  name: string
  type?: string | { base?: string; subtype?: string | null }
  required?: boolean
  description?: string
  options?: unknown
  multi?: unknown
}

const props = withDefaults(
  defineProps<{
    value: unknown
    port: PortInputPort
    /** false for the run dialog: runtime inputs are literals, not templates. */
    allowBindings?: boolean
    /** Workflow-level inputs offered as `$inputs.<key>` candidates. */
    inputs?: PortJSON[]
    /** Upstream nodes offered as `$nodes.<id>.*` candidates. */
    upstreamNodes?: UpstreamNodeRef[]
    disabled?: boolean
    placeholder?: string
  }>(),
  { allowBindings: true },
)

const emit = defineEmits<{
  (e: 'update:value', value: any): void
}>()

const { t } = useI18n()

const pickerOpen = ref(false)

// ---- port kind -------------------------------------------------------------

function baseOf(port: PortInputPort | undefined): string {
  const type = port?.type
  if (typeof type === 'string') return type.toLowerCase()
  if (type && typeof type === 'object' && typeof type.base === 'string') return type.base.toLowerCase()
  return ''
}

/** Widget kind via the shared T6 reverse mapping (select kinds included). */
const kind = computed<PortTypeKey>(() =>
  portJsonToTypeKey({
    name: props.port?.name ?? '',
    type: { base: baseOf(props.port) },
    options: Array.isArray(props.port?.options) ? (props.port.options as string[]) : [],
    multi: props.port?.multi === true,
  } as PortJSON),
)

const isPath = computed(() => kind.value === 'file' || kind.value === 'directory')

const resolvedPlaceholder = computed(() => {
  if (props.placeholder) return props.placeholder
  if (kind.value === 'file') return t('workflow.editor.config.placeholders.file')
  if (kind.value === 'directory') return t('workflow.editor.config.placeholders.directory')
  if (kind.value === 'json') return t('workflow.editor.config.placeholders.json')
  if (kind.value === 'number') return '0'
  return t('workflow.editor.config.placeholders.text')
})

const selectOptions = computed(() =>
  (Array.isArray(props.port?.options) ? (props.port.options as unknown[]) : []).map((value) => ({
    label: String(value),
    value: String(value),
  })),
)

// ---- value coercion --------------------------------------------------------

const asText = computed(() => (typeof props.value === 'string' ? props.value : props.value == null ? '' : String(props.value)))
const asNumber = computed(() => (typeof props.value === 'number' ? props.value : null))
const asArray = computed(() => (Array.isArray(props.value) ? props.value : []))

/** A string holding at least one `$` reference — edited as text, not typed. */
const boundText = computed(() => typeof props.value === 'string' && props.value.includes('$'))

// ---- bindings --------------------------------------------------------------

const bindingsEnabled = computed(
  () => props.allowBindings !== false && kind.value !== 'multi_select',
)

const bindings = computed<BindingToken[]>(() => (bindingsEnabled.value ? collectBindings(props.value) : []))
const tokens = bindings

const trigger = computed<BindingTrigger | null>(() =>
  bindingsEnabled.value ? findTrigger(props.value) : null,
)

const upstreamIds = computed(() => (props.upstreamNodes ?? []).map((node) => node.id))

const referenceContext = computed<BindingContext>(() => {
  const nodes: BindingContext['nodes'] = {}
  for (const node of props.upstreamNodes ?? []) {
    nodes[node.id] = {
      label: node.label,
      tool: node.tool,
      outputs: node.outputs ?? [],
      paramKeys: node.paramKeys ?? [],
    }
  }
  return {
    inputNames: (props.inputs ?? []).map((port) => port?.name).filter((name): name is string => !!name),
    nodes,
    upstreamIds: upstreamIds.value,
    targetBase: baseOf(props.port) || null,
  }
})

const issues = computed<BindingIssue[]>(() =>
  bindingsEnabled.value ? validateValue(props.value, referenceContext.value) : [],
)

/** Typing `$` (or `${`) at the tail opens the candidate picker. */
watch(
  () => props.value,
  (next) => {
    if (!bindingsEnabled.value) return
    if (findTrigger(next)) pickerOpen.value = true
  },
)

function onPick(path: string, pipes: string[]) {
  const tail = pipes && pipes.length > 0 ? pipes : null
  const current = typeof props.value === 'string' ? props.value : ''
  // insertBinding completes a typed `$`/`${` trigger and otherwise appends —
  // the whole-value vs interpolation rule lives in expressionBinding.
  emit('update:value', insertBinding(current, path, tail))
}

function removeToken(token: BindingToken) {
  emit('update:value', removeBinding(props.value, token))
}

// ---- native path picker ----------------------------------------------------

async function browsePath() {
  const isDir = kind.value === 'directory'
  try {
    const svc = (await serviceManager.getService('system')) as any
    const title = t('workflow.editor.dialog.selectTitle', { name: props.port?.name ?? '' })
    const res = isDir
      ? await svc.selectDirectory({ title })
      : await svc.selectFile({ title })
    if (res && !res.canceled) {
      const picked = (res.filePath || (res.filePaths && res.filePaths[0]) || '').trim()
      if (picked) emit('update:value', picked)
    }
  } catch (error) {
    log.error('PortInput: path picker failed', error)
  }
}
</script>

<style scoped>
.port-input {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  min-width: 0;
}

.pi-full {
  width: 100%;
}

.pi-path-row {
  display: flex;
  gap: 6px;
  width: 100%;
  min-width: 0;
}

.pi-path-input {
  flex: 1;
  min-width: 0;
}

.pi-mono :deep(.n-input__textarea-el),
.pi-mono :deep(.n-input__input-el) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
}

.pi-bind {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.pi-bind-head {
  display: flex;
  gap: 6px;
  align-items: center;
}

.pi-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}

.pi-chip {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  max-width: 100%;
  padding: 1px 4px 1px 6px;
  background: var(--app-code-bg, var(--app-card-bg));
  border: 1px solid var(--app-card-border);
  border-radius: 5px;
}

.pi-chip code {
  overflow: hidden;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 11px;
  color: var(--app-purple, var(--app-text-secondary));
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pi-chip-remove {
  padding: 0 2px;
  font: inherit;
  font-size: 12px;
  line-height: 1;
  color: var(--app-text-dim);
  cursor: pointer;
  background: transparent;
  border: 0;
}

.pi-chip-remove:hover {
  color: var(--app-red);
}

.pi-issue {
  font-size: 11px;
  line-height: 1.45;
}

.pi-issue--error {
  color: var(--app-red);
}

.pi-issue--warning {
  color: var(--app-orange, var(--app-text-dim));
}
</style>
