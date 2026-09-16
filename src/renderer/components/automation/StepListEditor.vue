<template>
  <div class="step-list-editor" :class="{ disabled }">
    <!-- 用 n-scrollbar：它的滚动条是**覆盖式**的（绝对定位，不占布局宽度），所以步骤
         卡片与下面常驻的「添加步骤」按钮左/右边缘完全一致、始终居中。之前用原生滚动条 +
         scrollbar-gutter: stable，右侧常驻 10px 车道，卡片看起来比按钮窄一截。 -->
    <n-scrollbar class="sl-scroll">
      <div class="sl-body">
        <n-empty
          v-if="!modelValue.length"
          size="small"
          class="sl-empty"
          :description="t('automation.noStepsHint')"
        />

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
            </div>
            <!-- 备注是次要信息：放在行尾（不再占第二行、不再把行撑高），灰掉 + 单行截断，
                 全文走 title 悬浮提示 -->
            <span
              v-if="String(step.note || '').trim()"
              class="step-note"
              :title="String(step.note || '')"
            >{{ step.note }}</span>

            <div class="step-ops" @click.stop>
              <!-- 行内操作收进一个竖排「⋮」菜单：向下添加步骤（子菜单 = 同一份动作清单）、
                   上移 / 下移 / 置顶 / 复制 / 删除。行里只剩这一个按钮，安静且不会挤到内容。 -->
              <n-dropdown
                trigger="click"
                placement="bottom-end"
                :options="rowMenuOptions(i)"
                :disabled="disabled"
                @select="(key: string) => onRowMenu(String(key), i)"
              >
                <IconButton
                  :icon="MoreVertical"
                  :label="t('common.more')"
                  :disabled="disabled"
                  size="tiny"
                  text
                />
              </n-dropdown>
            </div>
          </div>

          <StepEditForm
            v-if="i === editingIndex"
            :key="stepKey(step)"
            :step="step"
            :default-timeout="defaultTimeout"
            :default-interval="defaultInterval"
            :can-grab="canGrab"
            @click.stop
            @save="onSave(i, $event)"
            @cancel="closeEditor"
            @pick="onPick(i, $event)"
            @grab-activity="emit('grabActivity', { index: i })"
          />
        </div>
      </div>
    </n-scrollbar>

    <!-- 「添加步骤」常驻在列表底部（取代原来的顶部幽灵行）：列表为空时也在，
         点开就是动作清单 + 录制片段，落点 = 追加到末尾。 -->
    <n-dropdown
      trigger="click"
      placement="top-start"
      :options="addOptions || []"
      :disabled="disabled"
      @select="(key: string) => onAppend(String(key))"
    >
      <button class="add-step" type="button" :disabled="disabled">
        <n-icon size="14"><Plus /></n-icon>
        <span>{{ t('automation.addStep') }}</span>
      </button>
    </n-dropdown>
  </div>
</template>

<script setup lang="ts">
import { h, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NDropdown, NEmpty, NIcon, NScrollbar,
} from 'naive-ui'
import {
  ArrowDown, ArrowUp, ArrowUpToLine, Copy, GripVertical, MoreVertical, Play, Plus, Trash2,
} from 'lucide-vue-next'
import StepEditForm from './StepEditForm.vue'
import IconButton from '@components/common/IconButton.vue'
import { genId } from '@utils/id'
import { type Step } from './stepTypes'
import { stepActionGroup, stepActionLabel, stepSummary } from './stepMeta'

const props = defineProps<{
  modelValue: Step[]
  disabled?: boolean
  /** 当前选中的行（-1 = 无），父级持有以支持"插入到选中步骤之后" */
  selectedIndex?: number
  /** 元素目标默认超时（右栏可设），元素模式下自动填充 */
  defaultTimeout?: number
  /** 运行配置里的默认步骤间隔（ms），编辑表单里作为「间隔」的占位/默认 */
  defaultInterval?: number
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
  /** 行菜单「从此步开始运行」：index = 起点行，前面的步骤不执行 */
  (e: 'runFrom', index: number): void
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

// ---------------- 行内「⋮」菜单 ----------------
/** 菜单项里的图标按统一尺寸渲染（naive 的 icon 字段是 render 函数） */
function menuIcon(icon: any) {
  return () => h(NIcon, { size: 14 }, { default: () => h(icon) })
}

/** 「⋮」菜单：从此步开始运行 + 向下添加步骤（子菜单 = 页面给的同一份动作清单）
 *  + 排序 + 复制 + 删除 */
function rowMenuOptions(i: number) {
  const last = props.modelValue.length - 1
  return [
    { key: 'insert', label: t('automation.addStepBelow'), children: props.addOptions || [] },
    // 从这一步起跑（前面的步骤完全不执行）：调试长脚本时最常用的一步
    { key: 'runFrom', label: t('automation.runFromStep'), icon: menuIcon(Play) },
    { type: 'divider' as const, key: 'd0' },
    { key: 'up', label: t('automation.stepUp'), icon: menuIcon(ArrowUp), disabled: i === 0 },
    { key: 'down', label: t('automation.stepDown'), icon: menuIcon(ArrowDown), disabled: i >= last },
    { key: 'top', label: t('automation.moveToTop'), icon: menuIcon(ArrowUpToLine), disabled: i === 0 },
    { key: 'duplicate', label: t('automation.duplicateStep'), icon: menuIcon(Copy) },
    { type: 'divider' as const, key: 'd1' },
    {
      key: 'delete',
      label: t('automation.stepDelete'),
      icon: menuIcon(Trash2),
      props: { style: 'color: var(--app-red)' },
    },
  ]
}

/** 菜单选中：内置动作自己处理，其余 key（子菜单里的动作 / 录制片段）
 *  一律理解为「在这一行下面插入」。 */
function onRowMenu(key: string, i: number) {
  if (key === 'up') return reorder(i, i - 1)
  if (key === 'down') return reorder(i, i + 1)
  if (key === 'top') return reorder(i, 0)
  if (key === 'duplicate') return duplicate(i)
  if (key === 'delete') return remove(i)
  if (key === 'insert') return
  if (key === 'runFrom') {
    emit('runFrom', i)
    return
  }
  emit('insertBelow', { index: i, key })
}

/** 复制一行：内容一致、id 重新生成，插在原行下方并选中副本 */
function duplicate(i: number) {
  const src = props.modelValue[i]
  if (!src) return
  const copy = JSON.parse(JSON.stringify(src)) as Step
  copy.id = genId()
  const list = [...props.modelValue]
  list.splice(i + 1, 0, copy)
  emitList(list)
  emit('update:selectedIndex', i + 1)
}

/** 底部常驻「添加步骤」：落点 = 追加到末尾（空列表 = 第一行） */
function onAppend(key: string) {
  emit('insertBelow', { index: props.modelValue.length - 1, key })
}

/** 外部（底部「添加步骤」、行内菜单）插入步骤后打开对应行的编辑表单 */
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
/* 滚动容器：n-scrollbar 的滚动条是覆盖式的，不占宽度，所以卡片左右边缘 = 列边缘。
   `.sl-body` 只是内容列（行间距在这里），不再是滚动容器。 */
.sl-scroll { flex: 1 1 auto; min-height: 0; }
.sl-body {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
/* 底部常驻「添加步骤」：虚线幽灵行（原顶部那条挪到这里），始终可见 */
.add-step {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: none;
  width: 100%;
  margin-top: 6px;
  padding: 6px 8px;
  font-family: inherit;
  font-size: var(--app-font-size-sm);
  color: var(--app-text-muted);
  cursor: pointer;
  background: transparent;
  border: 1px dashed var(--app-card-border);
  border-radius: 8px;
  transition: color 0.13s, border-color 0.13s, background 0.13s;
}
.add-step:hover:not(:disabled) {
  color: var(--app-blue);
  border-color: var(--app-blue);
  background: var(--app-blue-bg);
}
.add-step:disabled { opacity: 0.5; cursor: not-allowed; }
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
/* summary 独占左侧弹性区；备注在行尾（见 .step-note） */
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
/* 行尾备注：刻意做得不显眼（小字 + 最弱颜色 + 宽度上限），完整内容看 title */
.step-note {
  flex: 0 1 auto;
  max-width: 40%;
  font-size: var(--app-font-size-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-dim);
  opacity: 0.85;
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
