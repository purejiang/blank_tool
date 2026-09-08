<template>
  <div class="step-list-editor" :class="{ disabled }">
    <div class="sl-head">
      <n-dropdown
        trigger="click"
        placement="bottom-start"
        :options="addOptions"
        @select="onAdd"
      >
        <n-button size="tiny" type="primary" dashed :disabled="disabled">
          <template #icon><n-icon><Plus /></n-icon></template>
          {{ t('automation.addStep') }}
        </n-button>
      </n-dropdown>
      <span class="sl-count">{{ modelValue.length }}</span>
    </div>

    <n-empty
      v-if="!modelValue.length"
      size="small"
      class="sl-empty"
      :description="t('automation.noStepsHint')"
    />

    <div v-else class="sl-body">
      <div
        v-for="(step, i) in modelValue"
        :key="i"
        class="step-item"
        :class="{ editing: i === editingIndex, selected: i === selectedIndex }"
        @click="toggleSelect(i)"
      >
        <div class="step-row">
          <span class="step-idx">{{ i + 1 }}</span>
          <n-tag size="tiny" :bordered="false" class="step-badge">
            {{ stepActionLabel(step.action, t) }}
          </n-tag>
          <span class="step-sum" :title="stepSummary(step)">{{ stepSummary(step) }}</span>

          <div class="step-ops" @click.stop>
            <n-button
              size="tiny" text :disabled="disabled || i === 0"
              :title="t('automation.stepUp')"
              @click.stop="move(i, -1)"
            >
              <n-icon size="14"><ChevronUp /></n-icon>
            </n-button>
            <n-button
              size="tiny" text :disabled="disabled || i === modelValue.length - 1"
              :title="t('automation.stepDown')"
              @click.stop="move(i, 1)"
            >
              <n-icon size="14"><ChevronDown /></n-icon>
            </n-button>
            <n-button
              size="tiny" text type="primary" :disabled="disabled"
              :title="t('automation.stepEdit')"
              @click.stop="toggleEdit(i)"
            >
              <n-icon size="14"><Pencil /></n-icon>
            </n-button>
            <n-button
              size="tiny" text type="error" :disabled="disabled"
              :title="t('automation.stepDelete')"
              @click.stop="remove(i)"
            >
              <n-icon size="14"><Trash2 /></n-icon>
            </n-button>
          </div>
        </div>

        <StepEditForm
          v-if="i === editingIndex"
          :step="step"
          @click.stop
          @save="onSave(i, $event)"
          @cancel="editingIndex = -1"
          @pick="onPick(i, $event)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NDropdown, NEmpty, NIcon, NTag,
} from 'naive-ui'
import {
  ChevronUp, ChevronDown, Pencil, Plus, Trash2,
} from 'lucide-vue-next'
import StepEditForm from './StepEditForm.vue'
import {
  ADDABLE_ACTIONS, defaultStep, type Step, type StepAction,
} from './stepTypes'
import { stepActionLabel, stepSummary } from './stepMeta'

const props = defineProps<{
  modelValue: Step[]
  disabled?: boolean
  /** 当前选中的行（-1 = 无），父级持有以支持"插入到选中步骤之后" */
  selectedIndex?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', steps: Step[]): void
  (e: 'update:selectedIndex', index: number): void
  (e: 'record-request'): void
  /** StepEditForm 请求从当前界面 dump 中拾取元素/坐标 */
  (e: 'pick', payload: { index: number; mode: 'coord' | 'element' }): void
}>()

const { t } = useI18n()

const editingIndex = ref(-1)

const RECORD_KEY = '__record__'

const addOptions = computed(() => [
  {
    key: RECORD_KEY,
    label: t('automation.recordSegment'),
  },
  { type: 'divider' as const, key: 'd1' },
  ...ADDABLE_ACTIONS.map(a => ({
    key: a,
    label: stepActionLabel(a, t),
  })),
])

/** 行选中：再点一次取消；按钮区已 stop 冒泡 */
function toggleSelect(i: number) {
  if (props.disabled) return
  const cur = props.selectedIndex ?? -1
  emit('update:selectedIndex', cur === i ? -1 : i)
}

/** emit a fresh (cloned) array — never mutate the prop in place */
function emitList(steps: Step[]) {
  emit('update:modelValue', JSON.parse(JSON.stringify(steps)))
}

function onAdd(action: string) {
  if (action === RECORD_KEY) {
    emit('record-request')
    return
  }
  const list = [...props.modelValue, defaultStep(action as StepAction)]
  emitList(list)
  editingIndex.value = list.length - 1
}

/** 增删移动后修正父级持有的选中下标 */
function adjustedIndexAfterRemove(i: number): number {
  const cur = props.selectedIndex ?? -1
  if (cur === i) return -1
  if (cur > i) return cur - 1
  return cur
}

function adjustedIndexAfterMove(i: number, delta: number): number {
  const cur = props.selectedIndex ?? -1
  if (cur === i) return i + delta
  if (cur === i + delta) return i
  return cur
}

function move(i: number, delta: number) {
  const list = [...props.modelValue]
  const j = i + delta
  if (j < 0 || j >= list.length) return
  ;[list[i], list[j]] = [list[j], list[i]]
  emitList(list)
  emit('update:selectedIndex', adjustedIndexAfterMove(i, delta))
  if (editingIndex.value === i) editingIndex.value = j
}

function remove(i: number) {
  const list = props.modelValue.filter((_, k) => k !== i)
  emitList(list)
  emit('update:selectedIndex', adjustedIndexAfterRemove(i))
  if (editingIndex.value === i) editingIndex.value = -1
  else if (editingIndex.value > i) editingIndex.value -= 1
}

function toggleEdit(i: number) {
  editingIndex.value = editingIndex.value === i ? -1 : i
}

function onSave(i: number, step: Step) {
  const list = [...props.modelValue]
  list[i] = step
  emitList(list)
  editingIndex.value = -1
}

function onPick(i: number, payload: { mode: 'coord' | 'element' }) {
  emit('pick', { index: i, ...payload })
}
</script>

<style scoped>
.step-list-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
}
.step-list-editor.disabled { opacity: 0.6; pointer-events: none; }
.sl-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sl-count { font-size: 12px; color: var(--text-tertiary, #999); }
.sl-empty { margin: 18px 0; }
.sl-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
}
.step-item {
  border: 1px solid var(--border-color, #2c2c32);
  border-radius: 6px;
  background: var(--card-color, transparent);
  cursor: pointer;
}
.step-item.editing {
  border-color: var(--primary-color, #4a90d9);
}
.step-item.selected {
  border-color: var(--primary-color, #4a90d9);
  background: var(--app-blue-bg, rgba(74, 144, 217, 0.12));
}
.step-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
}
.step-idx {
  width: 22px;
  flex: none;
  font-size: 11px;
  color: var(--text-tertiary, #999);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.step-badge { flex: none; font-size: 11px; }
.step-sum {
  flex: 1;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary, #aaa);
  font-variant-numeric: tabular-nums;
}
.step-ops {
  display: flex;
  align-items: center;
  gap: 0;
  flex: none;
}
</style>
