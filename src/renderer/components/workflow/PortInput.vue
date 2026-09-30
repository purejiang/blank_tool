<template>
  <!-- Single typed control for a port + expression-binding affordances.
       Used by the node config panel and the run-inputs dialog, so the typed
       widget matrix lives in exactly one place. -->
  <div ref="rootRef" class="port-input">
    <!-- file / directory: text input + native picker -->
    <div v-if="isPath" class="pi-path-row">
      <n-input
        :value="asText"
        size="small"
        class="pi-path-input"
        :disabled="disabled"
        :placeholder="resolvedPlaceholder"
        @update:value="emit('update:value', $event)"
        @keyup="rememberSelection"
        @click="rememberSelection"
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
      @keyup="rememberSelection"
      @click="rememberSelection"
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
      @keyup="rememberSelection"
      @click="rememberSelection"
    />

    <!-- Binding row: friendly chips + insert picker + inline validation -->
    <div v-if="bindingsEnabled" class="pi-bind">
      <div class="pi-bind-head">
        <ExpressionPicker
          v-model:show="pickerOpen"
          :inputs="inputs"
          :upstream-nodes="upstreamNodes"
          :trigger="trigger"
          :target-base="baseOf(props.port) || null"
          :disabled="disabled"
          @pick="onPick"
        />
        <div v-if="chips.length > 0" class="pi-chips">
          <span
            v-for="chip in chips"
            :key="`${chip.token.start}-${chip.token.raw}`"
            class="pi-chip"
            :title="chip.label.raw"
          >
            <code>{{ chip.text }}</code>
            <button
              type="button"
              class="pi-chip-remove"
              :title="t('workflow.editor.binding.remove')"
              @click="removeToken(chip.token)"
            >
              ×
            </button>
          </span>
        </div>
        <!-- 只在真的有绑定时说明这是整值表达式还是文本插值：不让用户去猜 `$` 的语义 -->
        <span v-else-if="bindingMode" class="pi-mode">{{ t(`workflow.editor.binding.mode.${bindingMode}`) }}</span>
      </div>
      <div v-for="(item, index) in issues" :key="`${item.code}-${index}`" class="pi-issue" :class="`pi-issue--${item.severity}`">
        {{ t(item.messageKey, item.params ?? {}) }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NInputNumber, NSelect, NSwitch } from 'naive-ui'

import ExpressionPicker from './ExpressionPicker.vue'
import {
  collectBindings,
  describeBindingToken,
  findTrigger,
  insertBindingAt,
  removeBinding,
  validateValue,
  type BindingContext,
  type BindingIssue,
  type BindingToken,
  type BindingTrigger,
  type InsertSelection,
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

/** 每个已插入引用的友好名（`解压 APK · apk_path`），title 保留原始表达式。 */
const chips = computed(() =>
  bindings.value.map((token) => {
    const label = describeBindingToken(token, { nodes: referenceContext.value.nodes, inputs: referenceContext.value.inputNames })
    const text = label.messageKey ? t(label.messageKey, label.params) : label.raw
    return { token, label, text }
  }),
)

/**
 * 值的绑定形态：整值表达式（引擎保留原类型）还是文本插值（按文本拼接）。
 * 只在字段里真的有引用时显示 —— 这是"看不懂 `$` 语义"的最小补救。
 */
const bindingMode = computed<'whole' | 'interpolation' | null>(() => {
  if (bindings.value.length === 0) return null
  if (bindings.value.some((token) => !token.wholeValue)) return 'interpolation'
  return bindings.value[0].wholeValue ? 'whole' : null
})

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
let programmaticInsert = false

watch(
  () => props.value,
  (next) => {
    if (!bindingsEnabled.value) return
    // 刚插入的引用本身就以 `$` 开头，不该被当成"用户正在敲 $"，否则选完一个
    // 候选弹层会立刻又弹回来。
    if (programmaticInsert) {
      programmaticInsert = false
      return
    }
    if (findTrigger(next)) pickerOpen.value = true
  },
)

function onPick(path: string, pipes: string[]) {
  const tail = pipes && pipes.length > 0 ? pipes : null
  const current = typeof props.value === 'string' ? props.value : ''
  // 有光标信息就插在光标处（长命令模板中间补路径是常见操作）；否则沿用
  // "空字段插整值、已有文本插插值"的默认规则。
  const result = insertBindingAt(current, path, tail, lastSelection.value)
  programmaticInsert = true
  emit('update:value', result.value)
  pickerOpen.value = false
  // 让光标停在插入内容之后：用户接着敲下一段文本时不会跳到开头。
  pendingCaret.value = result.caret
}

/** 文本控件的最后一次选区（点「插入引用」时读它决定插入位置）。 */
const lastSelection = ref<InsertSelection | null>(null)
const pendingCaret = ref<number | null>(null)
const rootRef = ref<HTMLElement | null>(null)

function rememberSelection(event: Event) {
  const el = event.target as HTMLInputElement | HTMLTextAreaElement | null
  if (!el || typeof el.selectionStart !== 'number') return
  lastSelection.value = { start: el.selectionStart, end: el.selectionEnd ?? el.selectionStart }
}

watch(pendingCaret, async (caret) => {
  if (caret === null) return
  pendingCaret.value = null
  // 值更新后把光标放回插入点（DOM 更新在下一个 tick）。
  await nextTick()
  const el = rootRef.value?.querySelector('input, textarea') as
    | HTMLInputElement
    | HTMLTextAreaElement
    | null
  if (!el || typeof el.setSelectionRange !== 'function') return
  try {
    el.focus()
    el.setSelectionRange(caret, caret)
  } catch {
    /* 控件可能已被替换（例如 switch → textarea），忽略 */
  }
})

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
  font-family: var(--font-family-monospace);
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

/* 绑定形态提示（整值表达式 / 文本插值）：只在字段里真的有引用时出现 */
.pi-mode {
  overflow: hidden;
  font-size: 10px;
  color: var(--app-text-dim);
  text-overflow: ellipsis;
  white-space: nowrap;
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
  border-radius: var(--radius-chip);
}

.pi-chip code {
  overflow: hidden;
  font-family: var(--font-family-monospace);
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
