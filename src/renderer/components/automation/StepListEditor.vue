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
        :class="{ editing: i === editingIndex }"
      >
        <div class="step-row">
          <span class="step-idx">{{ i + 1 }}</span>
          <n-tag size="tiny" :bordered="false" class="step-badge">
            {{ stepActionLabel(step.action, t) }}
          </n-tag>
          <span class="step-sum" :title="stepSummary(step)">{{ stepSummary(step) }}</span>

          <div class="step-ops">
            <n-button
              size="tiny" text :disabled="disabled || i === 0"
              :title="t('automation.stepUp')"
              @click="move(i, -1)"
            >
              <n-icon size="14"><ChevronUp /></n-icon>
            </n-button>
            <n-button
              size="tiny" text :disabled="disabled || i === modelValue.length - 1"
              :title="t('automation.stepDown')"
              @click="move(i, 1)"
            >
              <n-icon size="14"><ChevronDown /></n-icon>
            </n-button>
            <n-button
              size="tiny" text type="primary" :disabled="disabled"
              :title="t('automation.stepEdit')"
              @click="toggleEdit(i)"
            >
              <n-icon size="14"><Pencil /></n-icon>
            </n-button>
            <n-button
              size="tiny" text type="error" :disabled="disabled"
              :title="t('automation.stepDelete')"
              @click="remove(i)"
            >
              <n-icon size="14"><Trash2 /></n-icon>
            </n-button>
          </div>
        </div>

        <StepEditForm
          v-if="i === editingIndex"
          :step="step"
          @save="onSave(i, $event)"
          @cancel="editingIndex = -1"
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
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', steps: Step[]): void
}>()

const { t } = useI18n()

const editingIndex = ref(-1)

const addOptions = computed(() =>
  ADDABLE_ACTIONS.map(a => ({
    key: a,
    label: stepActionLabel(a, t),
  })),
)

/** emit a fresh (cloned) array — never mutate the prop in place */
function emitList(steps: Step[]) {
  emit('update:modelValue', JSON.parse(JSON.stringify(steps)))
}

function onAdd(action: string) {
  const list = [...props.modelValue, defaultStep(action as StepAction)]
  emitList(list)
  editingIndex.value = list.length - 1
}

function move(i: number, delta: number) {
  const list = [...props.modelValue]
  const j = i + delta
  if (j < 0 || j >= list.length) return
  ;[list[i], list[j]] = [list[j], list[i]]
  emitList(list)
  if (editingIndex.value === i) editingIndex.value = j
}

function remove(i: number) {
  const list = props.modelValue.filter((_, k) => k !== i)
  emitList(list)
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
}
.step-item.editing {
  border-color: var(--primary-color, #4a90d9);
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
