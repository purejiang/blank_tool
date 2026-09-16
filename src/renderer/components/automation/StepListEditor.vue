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
        @click="toggleSelect(i)"
        @dragover.prevent="overIndex = i"
        @dragleave="overIndex = -1"
        @drop.prevent="onDrop(i)"
      >
        <div class="step-row">
          <!-- Drag source is THIS handle only, so a plain click on the row body
               can still expand/collapse it. The row stays the drop target —
               dropping onto a 20px grip would be unusable. onDragStart hands the
               browser the WHOLE row as the drag image (see below), otherwise the
               default ghost is just this little grip and the row looks like it
               never followed the cursor. -->
          <span
            class="step-handle"
            :title="t('automation.dragHint')"
            draggable="true"
            @dragstart="onDragStart(i, $event)"
            @dragend="dragIndex = -1; overIndex = -1"
            @click.stop
          >
            <n-icon size="12"><GripVertical /></n-icon>
          </span>
          <span class="step-idx">{{ i + 1 }}</span>
          <span class="step-badge" :class="'g-' + stepActionGroup(step.action)">
            {{ stepActionLabel(step.action, t) }}
          </span>
          <div class="step-texts">
            <span class="step-sum" :title="stepSummary(step)">{{ stepSummary(step) }}</span>
            <span
              v-if="String(step.note || '').trim()"
              class="step-note"
              :title="String(step.note || '')"
            >{{ step.note }}</span>
          </div>

          <div class="step-ops" @click.stop>
            <IconButton
              :icon="Trash2"
              :label="t('automation.stepDelete')"
              :disabled="disabled"
              size="tiny"
              text
              type="error"
              @click.stop="remove(i)"
            />
            <n-dropdown
              trigger="click"
              placement="bottom-end"
              :options="addOptions || []"
              :disabled="disabled"
              @select="(key: string) => emit('insertBelow', { index: i, key: String(key) })"
            >
              <IconButton
                :icon="Plus"
                :label="t('automation.addStep')"
                :disabled="disabled"
                size="tiny"
                text
                type="primary"
              />
            </n-dropdown>
          </div>
        </div>

        <StepEditForm
          v-if="i === editingIndex"
          :key="stepKey(step)"
          :step="step"
          :default-timeout="defaultTimeout"
          :can-grab="canGrab"
          @click.stop
          @save="onSave(i, $event)"
          @cancel="closeEditor"
          @pick="onPick(i, $event)"
          @grab-activity="emit('grabActivity', { index: i })"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NDropdown, NEmpty, NIcon,
} from 'naive-ui'
import {
  GripVertical, Plus, Trash2,
} from 'lucide-vue-next'
import StepEditForm from './StepEditForm.vue'
import IconButton from '@components/common/IconButton.vue'
import { type Step } from './stepTypes'
import { stepActionGroup, stepActionLabel, stepSummary } from './stepMeta'

const props = defineProps<{
  modelValue: Step[]
  disabled?: boolean
  /** 当前选中的行（-1 = 无），父级持有以支持"插入到选中步骤之后" */
  selectedIndex?: number
  /** 元素目标默认超时（右栏可设），元素模式下自动填充 */
  defaultTimeout?: number
  /** 是否可抓取设备当前 Activity（页面按选中设备传入），透传给编辑表单 */
  canGrab?: boolean
  /** 页头「添加步骤」下拉的同一份选项（行内 + 按钮复用，避免第二份清单） */
  addOptions?: any[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', steps: Step[]): void
  (e: 'update:selectedIndex', index: number): void
  /** StepEditForm 请求拾取：元素/坐标走 UI dump，screenshot 走截图取点 */
  (e: 'pick', payload: { index: number; mode: 'coord' | 'element' | 'screenshot' }): void
  /** StepEditForm 请求抓取设备当前 Activity：页面持有设备与后端调用 */
  (e: 'grabActivity', payload: { index: number }): void
  /** 行内「+」在该行下方插入：index = 被点击的行，key = 动作或录制占位键 */
  (e: 'insertBelow', payload: { index: number; key: string }): void
}>()

const { t } = useI18n()

const editingIndex = ref(-1)

/**
 * Row click: collapsed → select + expand; already open → collapse + deselect.
 * 展开的行就是选中的行，所以不再需要单独的编辑按钮 —— 一个手势覆盖两件事。
 */
function toggleSelect(i: number) {
  if (props.disabled) return
  if (editingIndex.value === i) closeEditor()
  else {
    editingIndex.value = i
    emit('update:selectedIndex', i)
  }
}

/** 收起编辑表单，选中状态跟着一起收（open row == selected row）。 */
function closeEditor() {
  editingIndex.value = -1
  emit('update:selectedIndex', -1)
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
    // Drag source is the 20px handle, so the browser's default drag image is
    // just that little grip — the row appears not to follow the cursor. The
    // standard fix is to hand it the whole row, offset to where the pointer
    // grabbed it, so the ghost is the row itself and feels picked up in place.
    const rowEl = (e.currentTarget as HTMLElement | null)?.closest('.step-item') as HTMLElement | null
    if (rowEl) {
      const rect = rowEl.getBoundingClientRect()
      e.dataTransfer.setDragImage(rowEl, e.clientX - rect.left, e.clientY - rect.top)
    }
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

function onSave(i: number, step: Step) {
  const list = [...props.modelValue]
  list[i] = step
  emitList(list)
  closeEditor()
}

function onPick(i: number, payload: { mode: 'coord' | 'element' | 'screenshot' }) {
  emit('pick', { index: i, ...payload })
}

/** 外部（页面顶部"添加步骤"、行内「+」）插入步骤后打开对应行的编辑表单 */
function openEditor(i: number) {
  if (i >= 0 && i < props.modelValue.length && !props.disabled) {
    editingIndex.value = i
    // keep the "open row == selected row" invariant the row click relies on
    emit('update:selectedIndex', i)
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
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
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
/* drag feedback — the grip handle (.step-handle) is the only drag source */
.step-item.dragging { opacity: 0.45; }
.step-item.drag-over {
  border-top: 2px solid var(--app-blue);
}
.step-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  min-height: 36px;
}
/* 20px wide so the grip hits 8 + 20 + 8 = 36 — the same left edge the edit
   form indents to, i.e. the handle sits in the gutter without shifting the
   badge. Also the long-press target, so it must not be a 12px sliver. */
.step-handle {
  flex: none;
  width: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--app-text-dim);
  cursor: grab;
  opacity: 0.45;
  transition: opacity 0.13s;
}
.step-item:hover .step-handle,
.step-item.selected .step-handle,
.step-item.editing .step-handle { opacity: 1; }
.step-idx {
  width: 20px;
  flex: none;
  font-size: var(--app-font-size-xs);
  line-height: 1;
  color: var(--app-text-dim);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
/* action badge — hue = action family, see stepMeta.stepActionGroup */
.step-badge {
  flex: none;
  font-size: var(--app-font-size-xs);
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
/* summary + optional note live in one column so a note grows the row to two
   lines instead of squeezing the summary */
.step-texts {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.step-sum {
  font-size: var(--app-font-size-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-secondary);
  font-variant-numeric: tabular-nums;
}
.step-note {
  font-size: var(--app-font-size-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-dim);
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
