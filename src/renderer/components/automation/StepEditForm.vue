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
      <n-button
        v-if="pickable"
        size="tiny"
        @click="$emit('pick', { mode: pickMode })"
      >{{ t('automation.f.pickElement') }}</n-button>
      <n-button size="tiny" @click="$emit('cancel')">{{ t('common.cancel') }}</n-button>
      <n-button size="tiny" type="primary" @click="save">{{ t('common.confirm') }}</n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NInputNumber, NSelect } from 'naive-ui'
import { STEP_FIELDS, visibleFields, type Step, type StepAction } from './stepTypes'

const props = defineProps<{ step: Step }>()
const emit = defineEmits<{
  (e: 'save', step: Step): void
  (e: 'cancel'): void
  /** Request the current UI dump to fill element/coord targets. */
  (e: 'pick', payload: { mode: 'coord' | 'element' }): void
}>()

const { t } = useI18n()

const allFields = computed(() => STEP_FIELDS[props.step.action as StepAction] || [])
/** Fields rendered for THIS step (mode-dependent fields filtered out). */
const fields = computed(() => visibleFields(props.step.action as StepAction, props.step))

/**
 * "Pick from current UI dump" availability + mode:
 *  * tap: coord → fills x/y with the picked element's center; element → fills by/value
 *  * wait: time → picking switches to element mode and fills by/value
 */
const pickable = computed(() => {
  const a = props.step.action
  return a === 'tap' || a === 'wait'
})
const pickMode = computed<'coord' | 'element'>(() => {
  const m = String(props.step.mode ?? '')
  if (props.step.action === 'tap' && m === 'coord') return 'coord'
  return 'element'
})

function buildForm(): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of allFields.value) out[f.key] = props.step[f.key] ?? f.default ?? null
  return out
}

const form = reactive<Record<string, unknown>>(buildForm())

watch(() => props.step, () => {
  Object.assign(form, buildForm())
})

function numVal(k: string): number | null {
  const v = form[k]
  return v === null || v === undefined || v === '' ? null : Number(v)
}
function strVal(k: string): string {
  const v = form[k]
  return v === null || v === undefined ? '' : String(v)
}
function setField(k: string, v: unknown) {
  form[k] = v
}

const error = ref('')

function save() {
  for (const f of fields.value) {
    if (f.required) {
      const v = form[f.key]
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
  // must not leave stale by/value pairs behind (the backend keys element
  // mode off their presence).
  const next: Step = { action: props.step.action }
  if (props.step.ts !== undefined) next.ts = props.step.ts
  for (const f of fields.value) {
    if (f.type === 'number') {
      const n = Number(form[f.key])
      next[f.key] = Number.isFinite(n) ? n : (f.default ?? 0)
    } else {
      next[f.key] = form[f.key] ?? f.default ?? ''
    }
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
.form-error { font-size: 12px; color: var(--danger-color, #e05555); }
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 2px;
}
</style>
