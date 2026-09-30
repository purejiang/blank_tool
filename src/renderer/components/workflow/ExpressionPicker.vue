<template>
  <!-- 引用选择器：字段里能写 `$xxx`，这个弹层负责"xxx 有哪些可选"。
       信息层级（按下单）：搜索 → 候选分组（工作流入参 / 每个上游节点 / 运行时）
       → 可折叠的取值变换。管道变换与环境变量都收进了"按需展开"，不再常驻。 -->
  <n-popover
    :show="show"
    trigger="click"
    placement="bottom-end"
    :show-arrow="false"
    class="ep-popover"
    @update:show="(value: boolean) => emit('update:show', value)"
  >
    <template #trigger>
      <!-- 触发按钮带文字：只给一个花括号图标没人知道这是「插入引用」 -->
      <n-button
        size="tiny"
        quaternary
        :disabled="disabled"
        :title="t('workflow.editor.binding.insert')"
        data-test="binding-insert"
      >
        <template #icon><AppIcon name="brace" size="sm" /></template>
        {{ t('workflow.editor.binding.insert') }}
      </n-button>
    </template>

    <div class="ep" @keydown="onKeydown">
      <n-input
        ref="searchRef"
        v-model:value="query"
        size="tiny"
        clearable
        :placeholder="t('workflow.editor.binding.searchPlaceholder')"
        data-test="binding-search"
      />

      <div class="ep-list" data-test="binding-list">
        <template v-for="group in visibleGroups" :key="group.key">
          <div class="ep-group" :data-test="`binding-group-${group.key}`">
            <span class="ep-group-title">{{ groupTitle(group) }}</span>
            <span v-if="group.nodeTool" class="ep-group-sub">{{ group.nodeTool }}</span>
          </div>
          <button
            v-for="candidate in group.items"
            :key="candidate.path || `${group.key}-env`"
            type="button"
            class="ep-item"
            :class="{
              'ep-item--active': candidate.path === activePath,
              'ep-item--dim': isIncompatible(candidate),
            }"
            :title="`$${candidate.path}`"
            :data-test="`binding-item-${candidate.path || 'env'}`"
            @click="onItemClick(candidate)"
          >
            <span class="ep-item-label">{{ itemLabel(candidate) }}</span>
            <PortTypeBadge
              v-if="candidate.typeKey"
              compact
              :type="{ base: baseOfTypeKey(candidate.typeKey), subtype: candidate.subtype ?? null }"
            />
            <span v-else-if="candidate.kind === 'param'" class="ep-item-tag">
              {{ t('workflow.editor.binding.sections.params') }}
            </span>
          </button>

          <!-- 环境变量：后端无法枚举进程环境，只能手输变量名 -->
          <div v-if="group.key === 'runtime' && showEnv" class="ep-env">
            <n-input
              ref="envInputRef"
              v-model:value="envName"
              size="tiny"
              class="ep-env-input"
              :placeholder="t('workflow.editor.binding.runtime.envPlaceholder')"
              data-test="binding-env-name"
              @keyup.enter="pickEnv"
            />
            <n-button size="tiny" :disabled="!envName.trim()" @click="pickEnv">
              {{ t('workflow.editor.binding.insert') }}
            </n-button>
          </div>
        </template>

        <div v-if="!hasAnyCandidate" class="ep-empty">
          {{ t('workflow.editor.binding.empty') }}
        </div>
      </div>

      <!-- 变换（可选）：默认收起，避免一屏 select + 输入框 -->
      <div class="ep-transform">
        <button
          type="button"
          class="ep-transform-toggle"
          data-test="binding-transform-toggle"
          @click="transformOpen = !transformOpen"
        >
          <AppIcon :name="transformOpen ? 'down' : 'arrow-r'" size="sm" />
          {{ t('workflow.editor.binding.transform.label') }}
        </button>
        <template v-if="transformOpen">
          <n-select
            v-model:value="pipe"
            size="tiny"
            class="ep-transform-select"
            :options="pipeOptions"
            data-test="binding-pipe"
          />
          <n-input
            v-if="pipe === 'default'"
            v-model:value="pipeArg"
            size="tiny"
            class="ep-transform-arg"
            :placeholder="t('workflow.editor.binding.pipes.argPlaceholder')"
          />
        </template>
        <span v-else-if="pipelessLabel" class="ep-transform-value">{{ pipelessLabel }}</span>
      </div>

      <div class="ep-help" :title="t('workflow.editor.binding.help')">
        {{ t('workflow.editor.binding.helpShort') }}
      </div>
    </div>
  </n-popover>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NPopover, NSelect } from 'naive-ui'
import AppIcon from '@components/ui/AppIcon.vue'

import PortTypeBadge from './PortTypeBadge.vue'
import {
  baseOfTypeKey,
  buildReferenceGroups,
  matchesTrigger,
  sortByCompatibility,
  type BindingTrigger,
  type ReferenceCandidate,
  type ReferenceGroup,
} from './expressionBinding'
import type { UpstreamNodeRef } from './toolMeta'
import type { PortJSON } from './serializer'

/**
 * Candidate picker for parameter bindings. Candidate discovery lives in
 * `expressionBinding.buildReferenceGroups` (pure, unit-tested); this component
 * owns presentation, keyboard navigation and the optional pipe tail.
 */
const props = defineProps<{
  /** Popover visibility (v-model:show) — the parent may open it on `$`. */
  show: boolean
  /** Workflow-level inputs (meta.inputs). */
  inputs?: PortJSON[]
  /** Nodes that run before the edited node (only these can be referenced). */
  upstreamNodes?: UpstreamNodeRef[]
  /** Typed `$` fragment used to filter candidates. */
  trigger?: BindingTrigger | null
  disabled?: boolean
  /**
   * Base type of the port being edited: candidates of that type sort first and
   * incompatible ones are dimmed (the engine would still take them — this is
   * guidance, not a gate).
   */
  targetBase?: string | null
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  /** Chosen expression path plus its pipe tail (may be empty). */
  (e: 'pick', path: string, pipes: string[]): void
}>()

const { t } = useI18n()

const query = ref('')
const pipe = ref<'none' | 'basename' | 'dirname' | 'default'>('none')
const pipeArg = ref('')
const envName = ref('')
const transformOpen = ref(false)
const activePath = ref('')
const searchRef = ref<InstanceType<typeof NInput> | null>(null)
const envInputRef = ref<InstanceType<typeof NInput> | null>(null)

watch(
  () => props.show,
  async (open) => {
    if (!open) return
    query.value = props.trigger?.fragment ?? ''
    transformOpen.value = false
    activePath.value = ''
    await nextTick()
    searchRef.value?.focus?.()
  },
)

const pipeOptions = computed(() => [
  { label: t('workflow.editor.binding.pipes.none'), value: 'none' },
  { label: t('workflow.editor.binding.pipes.basename'), value: 'basename' },
  { label: t('workflow.editor.binding.pipes.dirname'), value: 'dirname' },
  { label: t('workflow.editor.binding.pipes.default'), value: 'default' },
])

/** 收起状态下把当前变换显示成一行小字，不再占一个 select。 */
const pipelessLabel = computed(() => {
  const current = pipe.value
  if (current === 'none') return ''
  const label = t(`workflow.editor.binding.pipes.${current}`)
  return current === 'default' && pipeArg.value.trim() ? `${label} ${pipeArg.value.trim()}` : label
})

function groupTitle(group: ReferenceGroup): string {
  if (group.key === 'inputs') return t('workflow.editor.binding.groups.inputs')
  if (group.key === 'runtime') return t('workflow.editor.binding.groups.runtime')
  return t('workflow.editor.binding.groups.node', { name: group.nodeLabel ?? group.nodeId ?? '' })
}

function itemLabel(candidate: ReferenceCandidate): string {
  if (candidate.kind === 'runtime' && candidate.runtimeKey) {
    return t(`workflow.editor.binding.runtime.${candidate.runtimeKey}`)
  }
  if (candidate.kind === 'env') return t('workflow.editor.binding.runtime.env')
  return candidate.label
}

function matched(candidate: ReferenceCandidate): boolean {
  const needle = query.value.trim().toLowerCase()
  if (needle) {
    const haystack = `${candidate.path} ${candidate.label} ${candidate.nodeLabel ?? ''}`.toLowerCase()
    if (!haystack.includes(needle)) return false
  }
  // 只有非空的 path 才参与触发词补全过滤（env 条目是"点开输入"的入口）。
  return !candidate.path || matchesTrigger(candidate.path, props.trigger ?? null)
}

const visibleGroups = computed<ReferenceGroup[]>(() =>
  buildReferenceGroups(props.inputs ?? [], props.upstreamNodes ?? [])
    .map((group) => ({
      ...group,
      items: sortByCompatibility(
        group.items.filter((candidate) => matched(candidate)),
        props.targetBase ?? null,
      ),
    }))
    .filter((group) => group.items.length > 0),
)

/** 环境变量入口：查询为空、或用户正在敲 `env` / `环境` 时显示。 */
const showEnv = computed(() => {
  const needle = query.value.trim().toLowerCase()
  const fragment = (props.trigger?.fragment ?? '').toLowerCase()
  if (fragment.startsWith('env')) return true
  if (needle.length === 0) return true
  return 'env'.includes(needle) || '环境变量'.includes(needle)
})

const hasAnyCandidate = computed(() => visibleGroups.value.length > 0 || showEnv.value)

/** 平铺后的可见候选，用于键盘上下移动。 */
const flatCandidates = computed<ReferenceCandidate[]>(() =>
  visibleGroups.value.flatMap((group) => (group.key === 'runtime' ? group.items.filter((item) => item.kind !== 'env') : group.items)),
)

function isIncompatible(candidate: ReferenceCandidate): boolean {
  const target = props.targetBase
  if (!target || !candidate.typeKey) return false
  if (candidate.kind !== 'output' && candidate.kind !== 'input') return false
  return baseOfTypeKey(candidate.typeKey) !== target
}

watch(flatCandidates, (items) => {
  if (items.length === 0) {
    activePath.value = ''
    return
  }
  if (!items.some((item) => item.path === activePath.value)) activePath.value = items[0].path
})

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    emit('update:show', false)
    return
  }
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp' && event.key !== 'Enter') return
  const items = flatCandidates.value
  if (items.length === 0) return
  event.preventDefault()
  const index = items.findIndex((item) => item.path === activePath.value)
  if (event.key === 'Enter') {
    const picked = items[index >= 0 ? index : 0]
    if (picked) pick(picked.path)
    return
  }
  const delta = event.key === 'ArrowDown' ? 1 : -1
  const next = (index + delta + items.length) % items.length
  activePath.value = items[next].path
}

/** Pipe tail as written, e.g. ['basename'] or ['default:4']. */
function currentPipes(): string[] {
  if (pipe.value === 'none') return []
  if (pipe.value === 'default') {
    const arg = pipeArg.value.trim()
    return [arg ? `default:${arg}` : 'default:']
  }
  return [pipe.value]
}

function pick(path: string) {
  emit('pick', path, currentPipes())
  emit('update:show', false)
}

function onItemClick(candidate: ReferenceCandidate) {
  if (candidate.kind === 'env') {
    envInputRef.value?.focus?.()
    return
  }
  pick(candidate.path)
}

function pickEnv() {
  const name = envName.value.trim()
  if (!name) return
  pick(`env.${name}`)
}
</script>

<style scoped>
.ep {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 288px;
}

.ep-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  max-height: 260px;
  padding-right: 2px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

/* 分组标题：节点组写节点名，副标题写工具名 */
.ep-group {
  display: flex;
  gap: 6px;
  align-items: baseline;
  margin-top: 6px;
  padding: 0 4px;
}

.ep-group:first-child {
  margin-top: 0;
}

.ep-group-title {
  overflow: hidden;
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ep-group-sub {
  flex: none;
  margin-left: auto;
  font-family: var(--font-family-monospace);
  font-size: 10px;
  color: var(--app-text-dim);
}

.ep-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 6px;
  font: inherit;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-chip);
}

.ep-item:hover,
.ep-item--active {
  background: var(--app-hover);
  border-color: var(--app-card-border);
}

/* 类型不匹配：仍然可选，只是先被排到后面并变淡 */
.ep-item--dim {
  opacity: 0.55;
}

.ep-item-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-family: var(--font-family-monospace);
  font-size: 12px;
  color: var(--app-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ep-item-tag {
  flex: none;
  padding: 0 4px;
  font-size: 10px;
  line-height: 15px;
  color: var(--app-text-dim);
  background: var(--app-storage-bg);
  border-radius: var(--radius-chip);
}

.ep-env {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 0 4px;
}

.ep-env-input {
  flex: 1;
  min-width: 0;
}

.ep-transform {
  display: flex;
  gap: 6px;
  align-items: center;
  padding-top: 6px;
  border-top: 1px solid var(--app-card-border);
}

.ep-transform-toggle {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  flex: none;
  padding: 0;
  font: inherit;
  font-size: 11px;
  color: var(--app-text-muted);
  cursor: pointer;
  background: transparent;
  border: 0;
}

.ep-transform-toggle:hover {
  color: var(--app-blue);
}

.ep-transform-select {
  flex: 1;
  min-width: 0;
}

.ep-transform-arg {
  width: 84px;
  flex: none;
}

.ep-transform-value {
  overflow: hidden;
  font-size: 11px;
  color: var(--app-text-dim);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ep-empty,
.ep-help {
  font-size: 11px;
  line-height: 1.5;
  color: var(--app-text-dim);
}
</style>
