<template>
  <div class="step-edit-form">
    <!-- 每行三列：标签 | 输入 | 动作。动作列始终占位（即使这行没有动作），
         这样所有输入框右边缘对齐；按钮与输入框之间有固定空隙，互不重叠。 -->
    <!-- 备注 is metadata, NOT a schema field (no per-action column), so it is
         a standalone block on top and is written back explicitly in save(). -->
    <div class="form-row">
      <label class="form-label">{{ t('automation.f.note') }}</label>
      <n-input
        :value="note"
        size="small"
        :placeholder="t('automation.f.notePlaceholder')"
        class="form-ctl"
        @update:value="setNote"
      />
      <span class="form-actions-cell" />
    </div>

    <div v-for="f in renderedFields" :key="f.key" class="form-row">
      <label class="form-label">{{ t(`automation.f.${f.key === 'coord.x' ? 'byCoord' : f.labelKey}`) }}<span v-if="f.required" class="req">*</span></label>

      <n-input-number
        v-if="f.type === 'number' && f.key !== 'coord.y' && f.key !== 'coord.x'"
        :value="numVal(f.key)"
        size="small"
        :placeholder="f.placeholder"
        class="form-ctl"
        @update:value="(v: number | null) => setField(f.key, v)"
      />
      <n-select
        v-else-if="f.type === 'select'"
        :value="strVal(f.key)"
        size="small"
        tag
        filterable
        :options="(f.options || []).map(o => ({ value: o.value, label: o.labelKey ? t(`automation.f.${o.labelKey}`) : (o.label || o.value) }))"
        class="form-ctl"
        @update:value="(v: string) => setField(f.key, v)"
      />
      <n-input
        v-else-if="f.type === 'textarea'"
        :value="strVal(f.key)"
        type="textarea"
        size="small"
        :autosize="{ minRows: 1, maxRows: 4 }"
        :placeholder="f.placeholder"
        class="form-ctl"
        @update:value="(v: string) => setField(f.key, v)"
      />
      <!-- 元素匹配值：输入框在中间列，「取元素」在右侧动作列 —— 按钮不塞进输入框，
           也不跟输入框挤同一行宽度。 -->
      <n-input
        v-else-if="f.key === 'target.value'"
        :value="strVal(f.key)"
        size="small"
        :placeholder="f.placeholder"
        class="form-ctl"
        @update:value="(v: string) => setField(f.key, v)"
      />
      <!-- 坐标对：X / Y 各自带前缀标记（一眼分清哪个是哪个），等宽并排在中间列，
           「选坐标」在右侧动作列。`coord.y` 由这一行渲染，所以从 v-for 里排除
           （校验/保存仍走完整 fields）。 -->
      <div v-else-if="f.key === 'coord.x'" class="form-ctl coord-pair">
        <n-input-number
          :value="numVal('coord.x')"
          size="small"
          :show-button="false"
          :placeholder="t('automation.f.x')"
          @update:value="(v: number | null) => setField('coord.x', v)"
        >
          <template #prefix>X</template>
        </n-input-number>
        <n-input-number
          :value="numVal('coord.y')"
          size="small"
          :show-button="false"
          :placeholder="t('automation.f.y')"
          @update:value="(v: number | null) => setField('coord.y', v)"
        >
          <template #prefix>Y</template>
        </n-input-number>
      </div>
      <n-input
        v-else-if="f.key === 'activity'"
        :value="strVal(f.key)"
        size="small"
        :placeholder="f.placeholder"
        class="form-ctl"
        @update:value="(v: string) => setField(f.key, v)"
      />
      <n-input
        v-else
        :value="strVal(f.key)"
        size="small"
        :placeholder="f.placeholder"
        class="form-ctl"
        @update:value="(v: string) => setField(f.key, v)"
      />

      <!-- 动作列：只有需要「从设备/界面取一个值」的行才有按钮 -->
      <div class="form-actions-cell">
        <n-button
          v-if="f.key === 'target.value' && pickable"
          size="tiny"
          type="info"
          secondary
          :title="t('automation.f.pickElement')"
          :aria-label="t('automation.f.pickElement')"
          @click="$emit('pick', { mode: pickMode })"
        >
          <template #icon><n-icon size="14"><Crosshair /></n-icon></template>
          {{ t('automation.f.pickElementShort') }}
        </n-button>
        <n-button
          v-else-if="f.key === 'coord.x' && pickMode === 'screenshot'"
          size="tiny"
          type="info"
          secondary
          :title="t('automation.f.pickCoord')"
          :aria-label="t('automation.f.pickCoord')"
          @click="$emit('pick', { mode: pickMode })"
        >
          <template #icon><n-icon size="14"><Crosshair /></n-icon></template>
          {{ t('automation.f.pickCoord') }}
        </n-button>
        <n-tooltip v-else-if="f.key === 'activity'" :disabled="canGrab" trigger="hover" placement="top-end">
          <template #trigger>
            <span class="grab-btn-wrap">
              <n-button
                size="tiny"
                type="info"
                secondary
                :disabled="!canGrab"
                :aria-label="canGrab ? t('automation.f.grabActivity') : t('automation.f.grabActivityNoDevice')"
                @click="$emit('grabActivity')"
              >
                <template #icon><n-icon size="14"><RefreshCw /></n-icon></template>
                {{ t('automation.f.grabActivity') }}
              </n-button>
            </span>
          </template>
          {{ t('automation.f.grabActivityNoDevice') }}
        </n-tooltip>
      </div>
    </div>

    <!-- 间隔：和备注 / 失败策略一样是「通用」字段（每个动作都有），所以不进
         per-action schema。留空 = 跟随运行配置里的默认间隔，0 = 这一步不等待。 -->
    <div class="form-row">
      <label class="form-label">{{ t('automation.f.intervalMs') }}</label>
      <n-input-number
        :value="interval"
        size="small"
        :min="0"
        :placeholder="t('automation.f.intervalDefault', { n: defaultInterval ?? 0 })"
        :title="t('automation.f.intervalHint')"
        class="form-ctl"
        @update:value="setInterval"
      />
      <span class="form-actions-cell" />
    </div>

    <!-- 失败策略：和备注一样是「通用」字段（每个动作都有），所以不进
         per-action schema —— 渲染在字段区之后。inherit = 跟随运行级设置。 -->
    <div class="form-row">
      <label class="form-label">{{ t('automation.f.onError') }}</label>
      <n-select
        :value="onError"
        size="small"
        :options="onErrorOptions"
        class="form-ctl"
        @update:value="(v: string) => setOnError(v)"
      />
      <span class="form-actions-cell" />
    </div>

    <div v-if="error" class="form-error">{{ error }}</div>

    <div class="form-actions">
      <n-button size="tiny" @click="$emit('cancel')">{{ t('common.cancel') }}</n-button>
      <n-button size="tiny" type="primary" @click="save">{{ t('common.confirm') }}</n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NInput, NInputNumber, NSelect, NTooltip } from 'naive-ui'
import { Crosshair, RefreshCw } from 'lucide-vue-next'
import {
  STEP_FIELDS, getPath, setPath, type Step, type StepAction,
} from './stepTypes'

const props = defineProps<{
  step: Step
  /** 右栏设置的元素目标默认超时（ms），元素模式下自动填充 */
  defaultTimeout?: number
  /** 运行配置里的默认步骤间隔（ms）—— 间隔留空时的占位提示 + 实际生效值 */
  defaultInterval?: number
  /** 是否可抓取设备当前 Activity（页面按选中设备传入）；false 时按钮禁用+提示 */
  canGrab?: boolean
}>()
const emit = defineEmits<{
  (e: 'save', step: Step): void
  (e: 'cancel'): void
  /** Request a pick: element → UI dump, screenshot → click coords off a capture. */
  (e: 'pick', payload: { mode: 'coord' | 'element' | 'screenshot' }): void
  /** Request the page grab the device's current foreground Activity. */
  (e: 'grabActivity'): void
}>()

const { t } = useI18n()

const allFields = computed(() => STEP_FIELDS[props.step.action as StepAction] || [])
/**
 * Fields rendered for THIS step, honouring `visibleWhen` against the LIVE
 * form state (not the saved step) — switching 目标方式 must instantly swap
 * the coordinate fields for the element fields and vice versa.
 */
const fields = computed(() =>
  allFields.value.filter((f) => {
    if (!f.visibleWhen) return true
    return f.visibleWhen.equals.includes(getPath(form, f.visibleWhen.key) as string | number)
  }),
)

/**
 * 实际渲染的字段：`coord.y` 由 `coord.x` 那一行一起渲染（两个坐标等宽并排），
 * 所以从模板循环里排除。校验与保存仍遍历完整 `fields`，X / Y 依旧分别必填。
 */
const renderedFields = computed(() => fields.value.filter((f) => f.key !== 'coord.y'))

/**
 * "Pick" availability: element targets (and the input focus tap) pick from
 * the UI dump; a coordinate tap picks from a screenshot instead — games
 * (SurfaceView) expose no UI hierarchy, so coords are the only option there.
 * Fixed-duration waits have nothing to pick.
 *
 * assert_element is an unconditional element target (no mode discriminator),
 * so it is pickable exactly like input's focus field.
 */
const pickable = computed(() => {
  const a = props.step.action
  // input focuses the target field by by/value — always element-based
  if (a === 'input') return true
  // tap is pickable in BOTH modes: coord → screenshot, element → UI dump
  if (a === 'tap') return true
  // assert_element always asserts against an element target
  if (a === 'assert_element') return true
  if (a !== 'wait') return false
  return String(getPath(form, 'mode') ?? '') === 'element'
})
const pickMode = computed<'coord' | 'element' | 'screenshot'>(() => {
  const m = String(getPath(form, 'mode') ?? '')
  if (props.step.action === 'tap' && m === 'coord') return 'screenshot'
  return 'element'
})

function buildForm(): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of allFields.value) {
    const v = getPath(props.step, f.key)
    // MUST write through setPath (nested), matching getPath/setField reads —
    // `out[f.key] = v` would create a FLAT "target.value" key while every
    // reader resolves the dotted path as form.target.value → fields
    // (incl. the element pick fill and the default timeout) rendered empty.
    setPath(out, f.key, v === undefined ? fieldDefault(f) : v)
  }
  return out
}

/** Effective default for a field — the element timeout uses the right-column
 * setting instead of the static schema default. */
function fieldDefault(f: { key: string; default?: string | number }): string | number | null {
  if (f.key === 'target.timeout_ms' && props.defaultTimeout != null) {
    return props.defaultTimeout
  }
  return f.default ?? null
}

const form = reactive<Record<string, unknown>>(buildForm())

/**
 * 备注 is user metadata, NOT a schema field — it lives outside the `form` bag
 * and must be written back explicitly in save(), which rebuilds the step from
 * the visible schema fields only and would otherwise drop it.
 */
const note = ref(String(props.step.note ?? ''))

function setNote(v: string) {
  note.value = v
}

/**
 * 失败策略（`on_error`）是每个动作都有的通用字段 —— 和备注一样不写进
 * per-action schema，因此独立维护并在 save() 里显式写回。
 * `inherit` 表示**不写这个键**，即跟随运行级 `continue_on_error`。
 */
const onError = ref(String(props.step.on_error ?? 'inherit'))
function setOnError(v: string) {
  onError.value = v
}
const onErrorOptions = computed(() => [
  { value: 'inherit', label: t('automation.f.onErrorInherit') },
  { value: 'continue', label: t('automation.f.onErrorContinue') },
  { value: 'abort', label: t('automation.f.onErrorAbort') },
])

/**
 * 步骤间隔（`delay_ms`）与备注 / 失败策略一样是通用字段：不进 per-action
 * schema，独立维护并在 save() 里显式写回。`null`（输入框清空）= **不写这个
 * 键** = 跟随运行配置里的默认间隔；`0` 是显式「这一步不等待」。
 */
const interval = ref<number | null>(
  typeof props.step.delay_ms === 'number' ? props.step.delay_ms : null,
)
function setInterval(v: number | null) {
  interval.value = v === null || v === undefined || Number.isNaN(Number(v)) ? null : Number(v)
}

// Switching to element mode auto-fills the timeout from the right-column
// default (only when empty — never overwrite a user-entered value).
watch(() => String(getPath(form, 'mode') ?? ''), (m) => {
  if (m !== 'element') return
  const cur = getPath(form, 'target.timeout_ms')
  if (cur === null || cur === undefined || cur === '') {
    setField('target.timeout_ms', props.defaultTimeout ?? 10000)
  }
})

watch(() => props.step, () => {
  // 备注 lives outside `form`, so it needs its own re-sync when the step is
  // replaced externally (e.g. an element picked from the UI dump).
  note.value = String(props.step.note ?? '')
  onError.value = String(props.step.on_error ?? 'inherit')
  interval.value = typeof props.step.delay_ms === 'number' ? props.step.delay_ms : null
  Object.assign(form, buildForm())
})

function numVal(k: string): number | null {
  const v = getPath(form, k)
  return v === null || v === undefined || v === '' ? null : Number(v)
}
function strVal(k: string): string {
  const v = getPath(form, k)
  return v === null || v === undefined ? '' : String(v)
}
function setField(k: string, v: unknown) {
  setPath(form, k, v)
}

const error = ref('')

function save() {
  for (const f of fields.value) {
    if (f.required) {
      const v = getPath(form, f.key)
      if (v === null || v === undefined || v === '') {
        error.value = t('automation.f.required', {
          field: t(`automation.f.${f.labelKey}`),
        })
        return
      }
    }
  }
  error.value = ''
  // Rebuild from VISIBLE fields only — switching mode (e.g. element → coord)
  // must not leave stale coord/target pairs behind.
  const next: any = { id: props.step.id, action: props.step.action }
  // 备注 is NOT a schema field — write it back explicitly or the rebuild below
  // drops it; whitespace-only is omitted so it never litters the JSON.
  if (note.value.trim()) next.note = note.value
  // Same for the failure policy: only an EXPLICIT choice is stored, so
  // "inherit" keeps following the run-level setting instead of pinning it.
  if (onError.value === 'continue' || onError.value === 'abort') {
    next.on_error = onError.value
  }
  // 间隔同理：留空 = 不写键（跟随运行默认），0 是显式的「不等待」。
  if (interval.value !== null && Number.isFinite(Number(interval.value)) && Number(interval.value) >= 0) {
    next.delay_ms = Math.round(Number(interval.value))
  }
  for (const f of fields.value) {
    if (f.type === 'number') {
      const n = Number(getPath(form, f.key))
      setPath(next, f.key, Number.isFinite(n) ? n : (fieldDefault(f) ?? 0))
    } else {
      setPath(next, f.key, getPath(form, f.key) ?? f.default ?? '')
    }
  }
  // input: empty focus target = no pre-typing tap — drop it entirely
  if (props.step.action === 'input' && !(next.target as any)?.value) {
    delete next.target
  }
  emit('save', next)
}
</script>

<style scoped>
.step-edit-form {
  /* 左内边距对齐行内徽标（行 padding 8 + 序号 20 + gap 8）；右边留 10px，
     避开 n-scrollbar 覆盖式滚动条 6px 的车道，控件不会被滚动条压住。
     同时声明为容器：窄列时用容器查询把动作列换到下一行。 */
  padding: 6px 10px 8px 36px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  container-type: inline-size;
}
/* 三列网格：标签 | 输入 | 动作。`minmax(0, 1fr)` 的最小宽度必须是 0 —— 否则
   控件的 min-content 会把行撑宽，窄列下按钮被挤出可见区。动作列 max-content
   只占按钮实际宽度，且每行都渲染（没动作时留空），保证输入框右边缘对齐。 */
.form-row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) max-content;
  align-items: center;
  gap: 8px;
}
.form-label {
  min-width: 0;
  font-size: var(--app-font-size-sm);
  line-height: 1.35;
  color: var(--app-text-muted);
  text-align: right;
  overflow-wrap: anywhere;
}
.req { color: var(--app-red); margin-left: 2px; }
.form-ctl { min-width: 0; }
/* 坐标对：两个等宽输入（各自带 X / Y 前缀），中间列内再分两列 */
.coord-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}
/* 动作列：按钮靠右，与输入框之间由 grid gap 留出固定空隙 */
.form-actions-cell { display: flex; justify-content: flex-end; align-items: center; }
.grab-btn-wrap { display: inline-flex; }
.form-error { font-size: var(--app-font-size-sm); color: var(--app-red); }
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 2px;
}
/* 窄列降级：动作列换到输入框下面一行，按钮左对齐 —— 任何宽度都不裁切、不重叠 */
@container (max-width: 360px) {
  .form-row { grid-template-columns: 72px minmax(0, 1fr); }
  .form-actions-cell { grid-column: 2; justify-content: flex-start; }
}
</style>
