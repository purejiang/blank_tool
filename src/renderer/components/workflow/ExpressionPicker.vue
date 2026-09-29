<template>
  <!-- Reference picker (T-params): grouped candidates for $inputs / $nodes /
       $workdir / $rundir / $env plus an optional pipe tail. The parent owns
       visibility so it can also open the popover from the `$` type-ahead. -->
  <n-popover
    :show="show"
    trigger="click"
    placement="bottom-end"
    :show-arrow="false"
    class="ep-popover"
    @update:show="(value: boolean) => emit('update:show', value)"
  >
    <template #trigger>
      <n-button
        size="tiny"
        quaternary
        :disabled="disabled"
        :title="t('workflow.editor.binding.insert')"
        data-test="binding-insert"
      >
        <template #icon><AppIcon name="brace" size="sm" /></template>
      </n-button>
    </template>

    <div class="ep">
      <n-input
        v-model:value="query"
        size="tiny"
        clearable
        :placeholder="t('workflow.editor.binding.searchPlaceholder')"
      />

      <div class="ep-pipes">
        <span class="ep-pipes-label">{{ t('workflow.editor.binding.pipes.label') }}</span>
        <n-select v-model:value="pipe" size="tiny" :options="pipeOptions" class="ep-pipe-select" />
        <n-input
          v-if="pipe === 'default'"
          v-model:value="pipeArg"
          size="tiny"
          class="ep-pipe-arg"
          :placeholder="t('workflow.editor.binding.pipes.argPlaceholder')"
        />
      </div>

      <div class="ep-list">
        <template v-for="group in visibleGroups" :key="group.key">
          <div class="ep-group">{{ t(`workflow.editor.binding.groups.${group.key}`) }}</div>
          <button
            v-for="candidate in group.items"
            :key="candidate.path"
            type="button"
            class="ep-item"
            :title="`$${candidate.path}`"
            @click="pick(candidate.path)"
          >
            <span class="ep-item-label">{{ candidate.label }}</span>
            <span v-if="candidate.detail" class="ep-item-detail">{{ candidate.detail }}</span>
          </button>
        </template>

        <!-- Environment variables need a typed key: the backend has no way to
             enumerate the process environment. -->
        <template v-if="showEnv">
          <div class="ep-group">{{ t('workflow.editor.binding.runtime.env') }}</div>
          <div class="ep-env">
            <n-input
              v-model:value="envName"
              size="tiny"
              class="ep-env-input"
              :placeholder="t('workflow.editor.binding.runtime.envPlaceholder')"
              @keyup.enter="pickEnv"
            />
            <n-button size="tiny" :disabled="!envName.trim()" @click="pickEnv">
              {{ t('workflow.editor.binding.insert') }}
            </n-button>
          </div>
          <div class="ep-hint">{{ t('workflow.editor.binding.runtime.envHint') }}</div>
        </template>

        <div v-if="!hasAnyCandidate" class="ep-empty">
          {{ t('workflow.editor.binding.empty') }}
        </div>
      </div>

      <div class="ep-help">{{ t('workflow.editor.binding.help') }}</div>
    </div>
  </n-popover>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NPopover, NSelect } from 'naive-ui'
import AppIcon from '@components/ui/AppIcon.vue'

import {
  BINDING_GROUPS,
  type BindingGroup,
  matchesTrigger,
  nodeOutputPath,
  nodeParamPath,
  inputPath,
  type BindingTrigger,
  type ReferenceCandidate,
} from './expressionBinding'
import { portTypeLabel, type UpstreamNodeRef } from './toolMeta'
import type { PortJSON } from './serializer'

/**
 * Candidate picker for parameter bindings. All candidate discovery lives in
 * props (workflow inputs + upstream node info), so this component stays a thin
 * presentation layer and the editor page owns the graph knowledge.
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

const pipeOptions = computed(() => [
  { label: t('workflow.editor.binding.pipes.none'), value: 'none' },
  { label: t('workflow.editor.binding.pipes.basename'), value: 'basename' },
  { label: t('workflow.editor.binding.pipes.dirname'), value: 'dirname' },
  { label: t('workflow.editor.binding.pipes.default'), value: 'default' },
])

function baseOf(port: { type?: string | { base?: string } }): string {
  const type = port?.type
  if (typeof type === 'string') return type
  if (type && typeof type === 'object' && typeof type.base === 'string') return type.base
  return ''
}

/** All candidates, grouped, before filtering. */
const candidates = computed<ReferenceCandidate[]>(() => {
  const list: ReferenceCandidate[] = []

  for (const port of props.inputs ?? []) {
    if (!port?.name) continue
    list.push({
      path: inputPath(port.name),
      label: port.name,
      detail: baseOf(port),
      group: 'inputs',
    })
  }

  for (const node of props.upstreamNodes ?? []) {
    for (const port of node.outputs ?? []) {
      if (!port?.name) continue
      list.push({
        path: nodeOutputPath(node.id, port.name),
        label: port.name,
        detail: `${node.label || node.id} · ${portTypeLabel(port.type)}`,
        group: 'nodes',
      })
    }
    for (const key of node.paramKeys ?? []) {
      if (!key) continue
      list.push({
        path: nodeParamPath(node.id, key),
        label: key,
        detail: `${node.label || node.id} · ${t('workflow.editor.binding.paramsLabel')}`,
        group: 'nodes',
      })
    }
  }

  list.push(
    {
      path: 'workdir',
      label: t('workflow.editor.binding.runtime.workdir'),
      detail: '$workdir',
      group: 'runtime',
    },
    {
      path: 'rundir',
      label: t('workflow.editor.binding.runtime.rundir'),
      detail: '$rundir',
      group: 'runtime',
    },
  )
  return list
})

function matched(candidate: ReferenceCandidate): boolean {
  const needle = query.value.trim().toLowerCase()
  if (needle && !candidate.path.toLowerCase().includes(needle) && !candidate.label.toLowerCase().includes(needle)) {
    return false
  }
  return matchesTrigger(candidate.path, props.trigger ?? null)
}

const visibleGroups = computed(() =>
  BINDING_GROUPS.map((key: BindingGroup) => ({
    key,
    items: candidates.value.filter((candidate) => candidate.group === key && matched(candidate)),
  })).filter((group) => group.items.length > 0),
)

const showEnv = computed(() => {
  const needle = query.value.trim().toLowerCase()
  const triggerFragment = (props.trigger?.fragment ?? '').toLowerCase()
  return 'env'.includes(needle) || needle.length === 0 || triggerFragment.startsWith('env')
})

const hasAnyCandidate = computed(() => visibleGroups.value.length > 0 || showEnv.value)

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
  width: 300px;
}

.ep-pipes {
  display: flex;
  gap: 6px;
  align-items: center;
}

.ep-pipes-label {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--app-text-dim);
}

.ep-pipe-select {
  flex: 1;
  min-width: 0;
}

.ep-pipe-arg {
  width: 96px;
  flex-shrink: 0;
}

.ep-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 260px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.ep-group {
  margin-top: 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--app-text-dim);
}

.ep-item {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 4px 6px;
  font: inherit;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-chip);
}

.ep-item:hover {
  background: var(--app-hover);
  border-color: var(--app-card-border);
}

.ep-item-label {
  font-family: var(--font-family-monospace);
  font-size: 12px;
  color: var(--app-text-primary);
}

.ep-item-detail {
  min-width: 0;
  overflow: hidden;
  font-size: 11px;
  color: var(--app-text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ep-env {
  display: flex;
  gap: 6px;
  align-items: center;
}

.ep-env-input {
  flex: 1;
  min-width: 0;
}

.ep-empty,
.ep-hint,
.ep-help {
  font-size: 11px;
  line-height: 1.5;
  color: var(--app-text-dim);
}
</style>
