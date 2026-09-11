<template>
  <div class="step-list-editor" :class="{ disabled }">
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
        :class="{ editing: i === editingIndex, selected: i === selectedIndex, dragging: dragIndex === i, 'drag-over': overIndex === i && dragIndex !== -1 && dragIndex !== i }"
        :draggable="i !== editingIndex"
        @click="toggleSelect(i)"
        @dragstart="onDragStart(i, $event)"
        @dragover.prevent="overIndex = i"
        @dragleave="overIndex = -1"
        @drop.prevent="onDrop(i)"
        @dragend="dragIndex = -1; overIndex = -1"
      >
        <div class="step-row">
          <span class="step-idx">{{ i + 1 }}</span>
          <span class="step-badge" :class="'g-' + stepActionGroup(step.action)">
            {{ stepActionLabel(step.action, t) }}
          </span>
          <span class="step-sum" :title="stepSummary(step)">{{ stepSummary(step) }}</span>

          <div class="step-ops" @click.stop>
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
          :key="stepKey(step)"
          :step="step"
          :default-timeout="defaultTimeout"
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
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NEmpty, NIcon,
} from 'naive-ui'
import {
  Pencil, Trash2,
} from 'lucide-vue-next'
import StepEditForm from './StepEditForm.vue'
import { type Step } from './stepTypes'
import { stepActionGroup, stepActionLabel, stepSummary } from './stepMeta'

const props = defineProps<{
  modelValue: Step[]
  disabled?: boolean
  /** 当前选中的行（-1 = 无），父级持有以支持"插入到选中步骤之后" */
  selectedIndex?: number
  /** 元素目标默认超时（右栏可设），元素模式下自动填充 */
  defaultTimeout?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', steps: Step[]): void
  (e: 'update:selectedIndex', index: number): void
  /** StepEditForm 请求从当前界面 dump 中拾取元素/坐标 */
  (e: 'pick', payload: { index: number; mode: 'coord' | 'element' }): void
}>()

const { t } = useI18n()

const editingIndex = ref(-1)

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

/** 增删移动后修正父级持有的选中下标 */
function adjustedIndexAfterRemove(i: number): number {
  const cur = props.selectedIndex ?? -1
  if (cur === i) return -1
  if (cur > i) return cur - 1
  return cur
}

// ---------------- drag reorder ----------------
const dragIndex = ref(-1)
const overIndex = ref(-1)

function onDragStart(i: number, e: DragEvent) {
  dragIndex.value = i
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(i))
  }
}

/** from → to 的落点下标换算（选中行与编辑行同步跟随） */
function movedIndex(cur: number, from: number, to: number): number {
  if (cur === from) return to
  if (from < cur && to <= cur) return cur - 1
  if (to >= cur && cur < from) return cur + 1
  return cur
}

function reorder(from: number, to: number) {
  if (from === to || from < 0) return
  const list = [...props.modelValue]
  const [m] = list.splice(from, 1)
  list.splice(to, 0, m)
  emitList(list)
  emit('update:selectedIndex', movedIndex(props.selectedIndex ?? -1, from, to))
  if (editingIndex.value >= 0) {
    editingIndex.value = movedIndex(editingIndex.value, from, to)
  }
}

function onDrop(to: number) {
  if (dragIndex.value < 0) return
  reorder(dragIndex.value, to)
  dragIndex.value = -1
  overIndex.value = -1
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

/** 外部（页面顶部"添加步骤"）追加步骤后打开对应行的编辑表单 */
function openEditor(i: number) {
  if (i >= 0 && i < props.modelValue.length && !props.disabled) {
    editingIndex.value = i
  }
}
defineExpose({ openEditor })

/** Remount key for the edit form: when the step CONTENT is replaced
 * externally (element picked from the UI dump), the form remounts and
 * rebuilds from the new step instead of relying on prop-watch timing. */
function stepKey(step: Step): string {
  return JSON.stringify(step)
}
</script>

<style scoped>
/* NOTE: every colour here comes from the app's own `--app-*` theme tokens
   (themes.css). Do NOT reach for the legacy Bootstrap vars in main.css
   (--border-color / --text-secondary / --primary-color): those are hardcoded
   LIGHT-theme values, so on the dark card they render a near-white 1px
   outline around every row. */
.step-list-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
}
.step-list-editor.disabled { opacity: 0.6; pointer-events: none; }
.sl-empty { margin: 18px 0; }
.sl-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
  overflow-y: auto;
}
.step-item {
  border: 1px solid var(--app-card-border);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
/* hover tint first, then selected/editing — same specificity, later wins */
.step-item:hover {
  background: color-mix(in srgb, var(--app-card-border) 40%, transparent);
}
.step-item.editing {
  border-color: var(--app-blue);
  background: var(--app-blue-bg);
}
.step-item.selected {
  border-color: var(--app-blue);
  background: var(--app-blue-bg);
}
/* drag & drop reorder (whole row is the handle, except the open editor) */
.step-item:not(.editing) { cursor: grab; }
.step-item.dragging { opacity: 0.45; }
.step-item.drag-over {
  border-top: 2px solid var(--app-blue);
}
.step-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
}
.step-idx {
  width: 20px;
  flex: none;
  font-size: 11px;
  line-height: 1;
  color: var(--app-text-dim);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
/* action badge — hue = action family, see stepMeta.stepActionGroup */
.step-badge {
  flex: none;
  font-size: 11px;
  line-height: 1;
  padding: 3px 6px;
  border-radius: 5px;
  white-space: nowrap;
  color: var(--app-text-muted);
  background: color-mix(in srgb, var(--app-text-muted) 16%, transparent);
}
.step-badge.g-nav { color: var(--app-blue); background: color-mix(in srgb, var(--app-blue) 16%, transparent); }
.step-badge.g-act { color: var(--app-green); background: color-mix(in srgb, var(--app-green) 16%, transparent); }
.step-badge.g-wait { color: var(--app-yellow); background: color-mix(in srgb, var(--app-yellow) 16%, transparent); }
.step-badge.g-check { color: var(--app-purple); background: color-mix(in srgb, var(--app-purple) 16%, transparent); }
.step-sum {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-secondary);
  font-variant-numeric: tabular-nums;
}
/* row actions stay out of the way until the row is hovered / focused —
   6 rows × 2 coloured icons was the loudest thing in the column, and the
   space they occupy is reserved either way, so nothing shifts on hover */
.step-ops {
  display: flex;
  align-items: center;
  gap: 0;
  flex: none;
  opacity: 0;
  transition: opacity 0.13s;
}
.step-item:hover .step-ops,
.step-item.selected .step-ops,
.step-item.editing .step-ops { opacity: 1; }
</style>
