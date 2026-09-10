<template>
  <div class="step-edit-form">
    <div v-for="f in fields" :key="f.key" class="form-field">
      <label>{{ t(`automation.f.${f.labelKey}`) }}<span v-if="f.required" class="req">*</span></label>

      <n-input-number
        v-if="f.type === 'number'"
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
  /** Request the current UI dump to fill element/coord targets. */
  (e: 'pick', payload: { mode: 'coord' | 'element' }): void
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
 * "Pick from current UI dump" availability: ONLY meaningful for an element
 * target (fills target.by/value). Coordinate taps and fixed-duration waits
 * have nothing to pick.
 */
const pickable = computed(() => {
  const a = props.step.action
  // input focuses the target field by by/value — always element-based
  if (a === 'input') return true
  if (a !== 'tap' && a !== 'wait') return false
  return String(getPath(form, 'mode') ?? '') === 'element'
})
const pickMode = computed<'coord' | 'element'>(() => {
  const m = String(getPath(form, 'mode') ?? '')
  if (props.step.action === 'tap' && m === 'coord') return 'coord'
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
  padding: 6px 8px 8px 30px;
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
  font-size: 12px;
  color: var(--text-secondary, #888);
  text-align: right;
}
.req { color: var(--danger-color, #e05555); margin-left: 2px; }
.field-ctl { flex: 1; }
.ctl-pick { display: flex; align-items: center; gap: 6px; }
.ctl-pick .n-input { flex: 1; min-width: 0; }
.ctl-pick-btn { flex: none; }
.form-error { font-size: 12px; color: var(--danger-color, #e05555); }
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 2px;
}
</style>
