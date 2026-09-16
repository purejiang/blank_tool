<template>
  <div class="step-edit-form">
    <!-- 备注 is metadata, NOT a schema field (no per-action column), so it is
         a standalone block on top and is written back explicitly in save(). -->
    <div class="form-field">
      <label>{{ t('automation.f.note') }}</label>
      <n-input
        :value="note"
        size="small"
        :placeholder="t('automation.f.notePlaceholder')"
        class="field-ctl"
        @update:value="setNote"
      />
    </div>

    <div v-for="f in fields" :key="f.key" class="form-field">
      <label>{{ t(`automation.f.${f.labelKey}`) }}<span v-if="f.required" class="req">*</span></label>

      <n-input-number
        v-if="f.type === 'number' && f.key !== 'coord.y'"
        :value="numVal(f.key)"
        size="small"
        :placeholder="f.placeholder"
        class="field-ctl"
        @update:value="(v: number | null) => setField(f.key, v)"
      />
      <n-select
        v-else-if="f.type === 'select'"
        :value="strVal(f.key)"
        size="small"
        tag
        filterable
        :options="(f.options || []).map(o => ({ value: o.value, label: o.labelKey ? t(`automation.f.${o.labelKey}`) : (o.label || o.value) }))"
        class="field-ctl"
        @update:value="(v: string) => setField(f.key, v)"
      />
      <n-input
        v-else-if="f.type === 'textarea'"
        :value="strVal(f.key)"
        type="textarea"
        size="small"
        :autosize="{ minRows: 1, maxRows: 4 }"
        :placeholder="f.placeholder"
        class="field-ctl"
        @update:value="(v: string) => setField(f.key, v)"
      />
      <!-- element value row: the "pick from UI" button lives HERE, next to
           the field it fills — not buried in the footer actions -->
      <div v-else-if="f.key === 'target.value'" class="field-ctl ctl-pick">
        <n-input
          :value="strVal(f.key)"
          size="small"
          :placeholder="f.placeholder"
          @update:value="(v: string) => setField(f.key, v)"
        />
        <n-button
          v-if="pickable"
          size="tiny"
          type="info"
          secondary
          class="ctl-pick-btn"
          :title="t('automation.f.pickElement')"
          @click="$emit('pick', { mode: pickMode })"
        >{{ t('automation.f.pickElement') }}</n-button>
      </div>
      <!-- coordinate value row: same button-next-to-the-field pattern —
           opens the screenshot picker (games expose no UI hierarchy).
           `coord.y` is a `number` field, hence the explicit exclusion in the
           generic number branch above: while both claimed it, the chain
           stopped there and this branch was dead code. -->
      <div v-else-if="f.key === 'coord.y'" class="field-ctl ctl-pick">
        <n-input-number
          :value="numVal(f.key)"
          size="small"
          :placeholder="f.placeholder"
          class="ctl-pick-input"
          @update:value="(v: number | null) => setField(f.key, v)"
        />
        <n-button
          v-if="pickMode === 'screenshot'"
          size="tiny"
          type="info"
          secondary
          class="ctl-pick-btn"
          :title="t('automation.f.pickCoord')"
          @click="$emit('pick', { mode: pickMode })"
        >{{ t('automation.f.pickCoord') }}</n-button>
      </div>
      <n-input
        v-else
        :value="strVal(f.key)"
        size="small"
        :placeholder="f.placeholder"
        class="field-ctl"
        @update:value="(v: string) => setField(f.key, v)"
      />
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
import { NButton, NInput, NInputNumber, NSelect } from 'naive-ui'
import {
  STEP_FIELDS, getPath, setPath, type Step, type StepAction,
} from './stepTypes'

const props = defineProps<{
  step: Step
  /** 右栏设置的元素目标默认超时（ms），元素模式下自动填充 */
  defaultTimeout?: number
}>()
const emit = defineEmits<{
  (e: 'save', step: Step): void
  (e: 'cancel'): void
  /** Request a pick: element → UI dump, screenshot → click coords off a capture. */
  (e: 'pick', payload: { mode: 'coord' | 'element' | 'screenshot' }): void
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
  if (props.step.ts !== undefined) next.ts = props.step.ts
  // 备注 is NOT a schema field — write it back explicitly or the rebuild below
  // drops it; whitespace-only is omitted so it never litters the JSON.
  if (note.value.trim()) next.note = note.value
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
  /* left edge lines up with the badge (row padding 8 + index 20 + gap 8) */
  padding: 6px 8px 8px 36px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-field {
  display: flex;
  align-items: center;
  gap: 8px;
}
.form-field label {
  width: 72px;
  flex: none;
  font-size: var(--app-font-size-sm);
  color: var(--app-text-muted);
  text-align: right;
}
.req { color: var(--app-red); margin-left: 2px; }
.field-ctl { flex: 1; }
.ctl-pick { display: flex; align-items: center; gap: 6px; }
.ctl-pick .n-input { flex: 1; min-width: 0; }
.ctl-pick-input { flex: 1; min-width: 0; }
.ctl-pick-btn { flex: none; }
.form-error { font-size: var(--app-font-size-sm); color: var(--app-red); }
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 2px;
}
</style>
