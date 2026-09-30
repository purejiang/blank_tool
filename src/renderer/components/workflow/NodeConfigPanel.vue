<template>
  <div class="node-config-panel">
    <div v-if="!node" class="npc-empty">{{ t('workflow.editor.config.noSelection') }}</div>
    <template v-else>
      <div class="npc-body">
        <!-- 节点身份（节点名 + 只读 id）不在这里：右栏标题栏（页面的 `.cfg-hd`）
             已经常显这两项，名字的编辑入口也挂在那儿——面板从「功能」直接开始。 -->

        <!-- 功能：这个节点做什么（工具 + 操作 + 描述） -->
        <section class="npc-sec">
          <div class="npc-sec-title">{{ t('workflow.editor.config.sections.capability') }}</div>
          <div class="npc-tool-row">
            <span class="npc-tool" :title="toolName">{{ toolName }}</span>
          </div>
          <AppField
            v-if="ports.operationMode"
            class="npc-op-field"
            :label="t('workflow.editor.config.operation')"
            :error="fieldError('operation')"
          >
            <n-select
              :value="ports.operation"
              size="small"
              :options="operationOptions"
              :placeholder="t('workflow.editor.config.operationPlaceholder')"
              clearable
              data-test="npc-operation"
              @update:value="onOperationChange"
            />
          </AppField>
          <p v-if="capabilityDescription" class="npc-desc">{{ capabilityDescription }}</p>
        </section>

        <!-- 参数：按类型渲染（文本 / 路径 / 布尔 / 数字 / JSON / 单选…），
             名称旁永远带类型徽标；必填常显，可选参数多时折叠。 -->
        <section class="npc-sec">
          <div class="npc-sec-title">
            {{ t('workflow.editor.config.parameters') }}
            <span v-if="inputPorts.length > 0" class="npc-sec-count">{{ inputPorts.length }}</span>
          </div>
          <div v-if="ports.operationMode && !ports.operation" class="npc-hint">
            {{ t('workflow.editor.config.operationPlaceholder') }}
          </div>
          <div v-else-if="inputPorts.length === 0" class="npc-hint">
            {{ t('workflow.editor.config.noParameters') }}
          </div>
          <template v-else>
            <div v-if="pendingIssueCount > 0" class="npc-hint npc-hint--pending">
              {{ t('workflow.editor.config.errors.pendingHint', { count: pendingIssueCount }) }}
            </div>
            <AppField
              v-for="port in visibleInputs"
              :key="port.name"
              class="npc-param"
              :label="port.name"
              :required="isRequired(port)"
              :help="port.description"
              :error="fieldError(port.name)"
            >              <template #label>
                <span class="npc-param-label">
                  <span class="npc-param-name">
                    {{ port.name }}<span v-if="isRequired(port)" class="npc-req">*</span>
                  </span>
                  <PortTypeBadge :type="port.type" :options="port.options" :multi="port.multi" />
                </span>
              </template>
              <PortInput
                :value="values[port.name]"
                :port="port"
                :inputs="workflowInputs"
                :upstream-nodes="upstreamNodes"
                @update:value="(value: any) => onValueChange(port, value)"
              />
            </AppField>
            <button
              v-if="collapsibleOptional"
              type="button"
              class="npc-more"
              data-test="npc-optional-toggle"
              @click="optionalExpanded = !optionalExpanded"
            >
              {{
                optionalExpanded
                  ? t('workflow.editor.config.optional.collapse')
                  : t('workflow.editor.config.optional.expand', { count: optionalCount })
              }}
            </button>
          </template>
        </section>

        <!-- 输出：只读，供下游引用 -->
        <section class="npc-sec">
          <div class="npc-sec-title">{{ t('workflow.editor.config.sections.outputs') }}</div>
          <div v-if="outputPorts.length === 0" class="npc-hint">
            {{ t('workflow.editor.config.noOutputs') }}
          </div>
          <div v-else class="npc-outputs">
            <div
              v-for="port in outputPorts"
              :key="port.name"
              class="npc-output-row"
              :title="port.description || ''"
            >
              <span class="npc-output-name">{{ port.name }}</span>
              <PortTypeBadge :type="port.type" :options="port.options" :multi="port.multi" />
            </div>
          </div>
        </section>

        <!-- 行为：跟随系统（用设置里的节点默认值）或自定义（把值写进这份工作流） -->
        <section class="npc-sec">
          <div class="npc-sec-title">{{ t('workflow.editor.config.sections.behavior') }}</div>
          <n-radio-group
            :value="behaviorMode"
            size="small"
            data-test="npc-behavior-mode"
            @update:value="onBehaviorModeChange"
          >
            <n-radio-button value="inherit">
              {{ t('workflow.editor.config.behavior.inherit') }}
            </n-radio-button>
            <n-radio-button value="custom">
              {{ t('workflow.editor.config.behavior.custom') }}
            </n-radio-button>
          </n-radio-group>

          <template v-if="behaviorMode === 'inherit'">
            <div class="npc-hint npc-behavior-summary">
              {{ t('workflow.editor.config.behavior.inheritSummary', { summary: defaultsSummary }) }}
              <button type="button" class="npc-link" data-test="npc-behavior-settings" @click="emit('open-settings')">
                {{ t('workflow.editor.config.behavior.goSettings') }}
              </button>
            </div>
          </template>
          <template v-else>
            <AppField class="npc-behavior-field" :label="t('workflow.editor.config.fields.onFailure')">
              <n-select
                :value="draftOnFailure"
                size="small"
                :options="failureOptions"
                data-test="npc-on-failure"
                @update:value="onFailureChange"
              />
            </AppField>
            <AppField
              class="npc-behavior-field"
              :label="t('workflow.editor.config.fields.retry')"
              :help="t('workflow.editor.config.fields.retryHint')"
            >
              <n-input-number
                :value="draftRetry"
                class="npc-full"
                size="small"
                :min="0"
                :show-button="false"
                data-test="npc-retry"
                @update:value="onRetryChange"
              />
            </AppField>
          </template>
        </section>
      </div>

      <!-- 字段即时生效，所以这里没有「保存」——落盘只有一个动作：顶栏的保存。 -->
      <div class="npc-footer">
        <AppButton variant="danger-ghost" data-test="npc-delete" @click="requestDelete">
          {{ t('workflow.editor.config.delete') }}
        </AppButton>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 节点检查器（右栏）。
 *
 * 三条设计约束（见 docs/07 / docs/08 §3-S2）：
 *  1. **字段即时生效**：编辑直接写进 `node.data`，没有节点级「保存」。落盘只有
 *     顶栏那一个保存动作，画布 dirty 指示器随之亮起；切换节点不会丢草稿。
 *  2. **不重复节点身份**：节点名（`data.label`）与只读 id 由右栏标题栏
 *     （页面的 `.cfg-hd`）常显并承担改名入口，面板不再有「基础」分区。
 *  3. **一处校验**：必填/操作缺失由 `nodeValidation` 判定，面板做字段级提示，
 *     页面用它挡住顶栏保存——两边不会漂移。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NInputNumber, NRadioButton, NRadioGroup, NSelect } from 'naive-ui'
import type { Node } from '@vue-flow/core'

import unifiedApi from '../../api/unifiedApi'
import { log } from '@utils/logger'
import AppButton from '@components/ui/AppButton.vue'
import AppField from '@components/ui/AppField.vue'
import PortInput from './PortInput.vue'
import PortTypeBadge from './PortTypeBadge.vue'
import {
  boundValues,
  effectivePorts,
  isEmptyValue,
  isRequiredPort,
  issueForField,
  validateNodeEditable,
  type EffectivePortShape,
} from './nodeValidation'
import {
  loadNodeDefaults,
  NODE_BEHAVIOR_FALLBACK,
  type NodeBehaviorDefaults,
} from './nodeDefaults'
import type { ToolOperation, UpstreamNodeRef, WorkflowToolInfo } from './toolMeta'
import type { PortJSON } from './serializer'

const { t } = useI18n()

/** 可选参数超过这个数量才折叠（少的时候全展开更好找）。 */
const OPTIONAL_COLLAPSE_THRESHOLD = 3

const props = defineProps<{
  /** Selected vue-flow node; null/undefined when nothing is selected. */
  node?: Node | null
  /** Workflow-level inputs, offered as `$inputs.<key>` binding candidates. */
  workflowInputs?: PortJSON[]
  /** Nodes that run before this one, offered as `$nodes.<id>.*` candidates. */
  upstreamNodes?: UpstreamNodeRef[]
}>()

const emit = defineEmits<{
  (e: 'delete', nodeId: string): void
  /** 跳到设置页配置节点默认值（路由动作由页面负责）。 */
  (e: 'open-settings'): void
}>()

// ---- node data ---------------------------------------------------------

const nodeData = computed<Record<string, any>>(() => (props.node?.data ?? {}) as Record<string, any>)
/** 工具名（「功能」分区那行只读文本；节点名由右栏标题栏负责）。 */
const toolName = computed<string>(() => {
  const data = nodeData.value
  return String(data.tool || data.toolName || props.node?.id || '')
})

// ---- tool metadata (operation mode) ------------------------------------
// The panel fetches workflow.list_tools itself so it stays self-contained (no
// parent prop); on failure it degrades to the legacy free-form params UI.

const toolList = ref<WorkflowToolInfo[]>([])
let toolsFetched = false

async function fetchToolList() {
  if (toolsFetched) return
  toolsFetched = true
  try {
    const result = await unifiedApi.call<{ tools?: WorkflowToolInfo[] }>('workflow.list_tools', {})
    toolList.value = Array.isArray(result?.tools) ? result.tools : []
  } catch (err) {
    log.warn('[NodeConfigPanel] workflow.list_tools unavailable; operation mode disabled', err)
  }
}

const toolInfo = computed<WorkflowToolInfo | null>(() => {
  const name = nodeData.value.tool
  if (typeof name !== 'string') return null
  return toolList.value.find((tool) => tool?.name === name) ?? null
})

/** 生效端口 + 操作（与页面保存门禁共用同一份解析）。 */
const ports = computed(() => effectivePorts(nodeData.value, toolInfo.value))
const inputPorts = computed<EffectivePortShape[]>(() => ports.value.inputs)
const outputPorts = computed<EffectivePortShape[]>(() => ports.value.outputs)

/** 当前存值容器（operation 模式看 inputs，否则看 params）。 */
const values = computed<Record<string, any>>(() =>
  boundValues(nodeData.value, ports.value.operationMode),
)

const operationOptions = computed(() =>
  (toolInfo.value?.operations ?? []).map((operation: ToolOperation) => ({
    label: operation.name,
    value: operation.name,
  })),
)

/** 功能描述：优先选中的操作描述，其次工具描述。 */
const capabilityDescription = computed(() => {
  const operation = ports.value.currentOperation
  if (operation?.description) return operation.description
  const description = toolInfo.value?.description
  return typeof description === 'string' ? description : ''
})

// ---- field-level validation --------------------------------------------

const issues = computed(() => validateNodeEditable(nodeData.value, toolInfo.value))

/**
 * 出错字段集合：只对"用户碰过"的字段立刻标红。
 *
 * 刚拖上画布的节点每个必填都是空的，一进来满屏红色是在骂人；未触碰的问题用
 * 参数区顶部一句灰字汇总，顶栏保存同样会被挡住（页面用同一份 issues）。
 */
const touched = ref<Set<string>>(new Set())

function markTouched(field: string) {
  if (touched.value.has(field)) return
  const next = new Set(touched.value)
  next.add(field)
  touched.value = next
}

/** 可选参数的展开状态（会话内记一次；换节点回到折叠）。 */
const optionalExpanded = ref(false)

// 切换节点：清空触碰记录与折叠状态
watch(
  () => props.node?.id,
  () => {
    touched.value = new Set()
    optionalExpanded.value = false
  },
)

function fieldError(field: string): string | null {
  if (!touched.value.has(field)) return null
  const issue = issueForField(issues.value, field)
  return issue ? t(issue.messageKey, issue.params ?? {}) : null
}

const pendingIssueCount = computed(
  () => issues.value.filter((issue) => !touched.value.has(issue.field)).length,
)

// ---- immediate edits ---------------------------------------------------

function onOperationChange(name: string | null) {
  markTouched('operation')
  const data = nodeData.value
  if (!name) {
    delete data.operation
    delete data.inputs
    return
  }
  const next = (toolInfo.value?.operations ?? []).find((operation) => operation?.name === name)
  const nextPorts = Array.isArray(next?.inputs) ? next.inputs : []
  const previous = (data.inputs ?? {}) as Record<string, unknown>
  // 换操作时只保留"新操作同样有这个名字"的已填值：既不会把上一条命令的
  // 绑定带错地方，也不会因为误点一下就把填好的参数清空。
  const carried: Record<string, unknown> = {}
  for (const port of nextPorts) {
    if (port?.name && previous[port.name] !== undefined) carried[port.name] = previous[port.name]
  }
  data.operation = name
  data.inputs = carried
  delete data.params
}

function onValueChange(port: EffectivePortShape, value: unknown) {
  markTouched(port.name)
  const data = nodeData.value
  const container = ports.value.operationMode
    ? { ...((data.inputs ?? {}) as Record<string, unknown>) }
    : { ...((data.params ?? {}) as Record<string, unknown>) }
  // 空值删键：未填的参数不该在工作流 JSON 里留下空串/空数组。
  if (isEmptyValue(value)) delete container[port.name]
  else container[port.name] = value
  if (ports.value.operationMode) data.inputs = container
  else data.params = container
}

// ---- optional parameter disclosure -------------------------------------

const optionalCount = computed(() => inputPorts.value.filter((port) => !isRequiredPort(port)).length)
const collapsibleOptional = computed(() => optionalCount.value > OPTIONAL_COLLAPSE_THRESHOLD)
const visibleInputs = computed<EffectivePortShape[]>(() =>
  collapsibleOptional.value && !optionalExpanded.value
    ? inputPorts.value.filter((port) => isRequiredPort(port))
    : inputPorts.value,
)

function isRequired(port: EffectivePortShape): boolean {
  return isRequiredPort(port)
}

// ---- behaviour (跟随系统 / 自定义) -------------------------------------

const defaults = ref<NodeBehaviorDefaults>({ ...NODE_BEHAVIOR_FALLBACK })

onMounted(async () => {
  void fetchToolList()
  defaults.value = await loadNodeDefaults()
})

/**
 * 自定义 = 节点自己写死了行为字段。判定标准就是字段存在与否——wire 上"缺省"
 * 正是"继承"，两边用同一个约定，不需要额外的模式标记。
 */
const behaviorMode = computed<'inherit' | 'custom'>(() => {
  const data = nodeData.value
  return typeof data.on_failure === 'string' || typeof data.retry === 'number'
    ? 'custom'
    : 'inherit'
})

const draftOnFailure = computed<'fail' | 'skip'>(() =>
  nodeData.value.on_failure === 'skip' ? 'skip' : 'fail',
)
const draftRetry = computed<number>(() =>
  typeof nodeData.value.retry === 'number' ? nodeData.value.retry : 0,
)

const failureOptions = computed(() => [
  { label: t('workflow.editor.config.onFailure.fail'), value: 'fail' },
  { label: t('workflow.editor.config.onFailure.skip'), value: 'skip' },
])

const defaultsSummary = computed(() => {
  const mode =
    defaults.value.onFailure === 'skip'
      ? t('workflow.editor.config.onFailure.skip')
      : t('workflow.editor.config.onFailure.fail')
  return t('workflow.editor.config.behavior.summary', {
    mode,
    retry: defaults.value.retry,
  })
})

function onBehaviorModeChange(mode: 'inherit' | 'custom') {
  const data = nodeData.value
  if (mode === 'custom') {
    // 预填当前生效的默认值：用户从"现在会发生什么"开始改，而不是从空白开始。
    if (typeof data.on_failure !== 'string') data.on_failure = defaults.value.onFailure
    if (typeof data.retry !== 'number') data.retry = defaults.value.retry
    return
  }
  delete data.on_failure
  delete data.retry
}

function onFailureChange(value: string | null) {
  nodeData.value.on_failure = value === 'skip' ? 'skip' : 'fail'
}

function onRetryChange(value: number | null) {
  const retry = typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0
  nodeData.value.retry = retry
}

// ---- deletion ----------------------------------------------------------

/** Deletion goes through the page, which owns the confirmation dialog. */
function requestDelete() {
  if (props.node) emit('delete', props.node.id)
}
</script>

<style scoped>
/* 面板填满编辑器右栏 `.ed-right`（其标题/副标题由页面渲染，`.cfg-hd`）。 */
.node-config-panel {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.npc-empty {
  padding: 12px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.npc-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  padding: 12px 14px 14px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

/* 分区之间只用一条细线，不做嵌套卡片——三层边框正是之前"很挤"的主因。 */
.npc-sec {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--app-card-border);
}

.npc-sec + .npc-sec {
  padding-top: 12px;
}

.npc-sec:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.npc-sec-title {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.npc-sec-count {
  padding: 0 5px;
  font-size: 10px;
  font-weight: 400;
  line-height: 15px;
  color: var(--app-text-dim);
  background: var(--app-storage-bg);
  border-radius: var(--radius-chip);
}

.npc-hint {
  font-size: 11px;
  line-height: 1.5;
  color: var(--app-text-dim);
}

.npc-hint--pending {
  color: var(--app-text-muted);
}

.npc-desc {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--app-text-dim);
}

.npc-tool-row {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.npc-tool {
  overflow: hidden;
  font-family: var(--font-family-monospace);
  font-size: 12px;
  color: var(--app-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 参数行 */
.npc-param-label {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

/* 行为字段用同一套 AppField，只是不参与"参数行"选择器 */
.npc-behavior-field {
  margin-top: 2px;
}

.npc-param-name {
  overflow: hidden;
  font-family: var(--font-family-monospace);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.npc-req {
  margin-left: 2px;
  color: var(--danger-text, var(--app-red));
}

.npc-more {
  padding: 2px 0;
  font: inherit;
  font-size: 11px;
  color: var(--app-text-muted);
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 0;
}

.npc-more:hover {
  color: var(--app-blue);
}

.npc-full {
  width: 100%;
}

/* 输出列表 */
.npc-outputs {
  display: flex;
  flex-direction: column;
}

.npc-output-row {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 0;
}

.npc-output-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-family: var(--font-family-monospace);
  font-size: 12px;
  color: var(--app-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 行为：跟随系统摘要 + 「去设置」 */
.npc-behavior-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: baseline;
}

.npc-link {
  padding: 0;
  font: inherit;
  font-size: 11px;
  color: var(--app-blue);
  cursor: pointer;
  background: transparent;
  border: 0;
}

.npc-link:hover {
  text-decoration: underline;
}

/* 页脚：只留删除（保存统一在顶栏） */
.npc-footer {
  display: flex;
  flex: none;
  gap: 8px;
  align-items: center;
  padding: 10px 14px;
  border-top: 1px solid var(--app-card-border);
}
</style>
