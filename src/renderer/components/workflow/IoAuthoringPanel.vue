<template>
  <!-- Workflow-level inputs/outputs authoring modal (T6). List mode shows the
       declared ports of the active side; edit mode is a draft form committed
       via the pure ioAuthoring helpers into meta.inputs / meta.outputs. -->
  <n-modal
    :show="show"
    preset="card"
    :title="t('workflow.editor.io.title')"
    :style="{ width: '640px' }"
    :mask-closable="!editing"
    @update:show="(value: boolean) => emit('update:show', value)"
  >
    <n-tabs :value="side" type="line" size="small" @update:value="onSideChange">
      <n-tab-pane name="inputs" :tab="t('workflow.editor.io.inputs')" />
      <n-tab-pane name="outputs" :tab="t('workflow.editor.io.outputs')" />
    </n-tabs>

    <!-- List mode -->
    <div v-if="!editing" class="io-body">
      <div v-if="ports.length === 0" class="io-empty">
        {{ t(side === 'inputs' ? 'workflow.editor.io.emptyInputs' : 'workflow.editor.io.emptyOutputs') }}
      </div>
      <div v-else class="io-list">
        <div v-for="port in ports" :key="port.name" class="io-row">
          <div class="io-row-body">
            <div class="io-row-head">
              <span class="io-row-name">{{ port.name }}</span>
              <span class="io-row-type">{{ t(`workflow.editor.io.types.${portJsonToTypeKey(port)}`) }}</span>
              <span v-if="port.required !== false" class="io-row-required">
                {{ t('workflow.editor.io.required') }}
              </span>
            </div>
            <div v-if="port.description" class="io-row-desc" :title="port.description">
              {{ port.description }}
            </div>
          </div>
          <div class="io-row-actions">
            <n-button size="small" quaternary :title="t('workflow.editor.io.edit')" @click="startEdit(port)">
              <template #icon><n-icon :size="13"><Pencil /></n-icon></template>
            </n-button>
            <n-button
              size="small"
              quaternary
              type="error"
              :title="t('workflow.editor.io.remove')"
              @click="removePort(port)"
            >
              <template #icon><n-icon :size="13"><Trash2 /></n-icon></template>
            </n-button>
          </div>
        </div>
      </div>
      <n-button size="small" class="io-add" @click="startAdd">
        <template #icon><n-icon :size="13"><Plus /></n-icon></template>
        {{ t(side === 'inputs' ? 'workflow.editor.io.addInput' : 'workflow.editor.io.addOutput') }}
      </n-button>
    </div>

    <!-- Edit mode: add or edit one port -->
    <div v-else class="io-body">
      <div class="io-form-title">
        {{ t(side === 'inputs' ? 'workflow.editor.io.editInput' : 'workflow.editor.io.editOutput') }}
      </div>
      <n-form :model="draft" label-placement="top" size="small">
        <n-form-item
          :label="t('workflow.editor.io.fields.name')"
          required
          :feedback="t('workflow.editor.io.fields.nameHint')"
        >
          <n-input
            v-model:value="draft.name"
            :placeholder="t('workflow.editor.io.fields.namePlaceholder')"
            @input="error = null"
          />
        </n-form-item>
        <n-form-item :label="t('workflow.editor.io.fields.type')">
          <n-select v-model:value="draft.typeKey" :options="typeOptions" @update:value="error = null" />
        </n-form-item>
        <n-form-item :label="t('workflow.editor.io.fields.required')">
          <n-checkbox v-model:checked="draft.required">
            {{ t('workflow.editor.io.fields.required') }}
          </n-checkbox>
        </n-form-item>
        <n-form-item :label="t('workflow.editor.io.fields.description')">
          <n-input
            v-model:value="draft.description"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :placeholder="t('workflow.editor.io.fields.descriptionPlaceholder')"
          />
        </n-form-item>
        <!-- Options list editor: only meaningful for 单选 / 多选 -->
        <n-form-item v-if="usesOptions" :label="t('workflow.editor.io.fields.options')" required>
          <div class="io-options">
            <div v-for="(option, index) in draft.options" :key="index" class="io-option-row">
              <n-input
                :value="option"
                size="small"
                class="io-option-input"
                :placeholder="t('workflow.editor.io.fields.optionPlaceholder')"
                @update:value="(value: string) => setOption(index, value)"
              />
              <n-button
                size="small"
                quaternary
                :disabled="index === 0"
                :title="t('workflow.editor.io.fields.optionMoveUp')"
                @click="moveOption(index, -1)"
              >
                <template #icon><n-icon :size="13"><ArrowUp /></n-icon></template>
              </n-button>
              <n-button
                size="small"
                quaternary
                :disabled="index === draft.options.length - 1"
                :title="t('workflow.editor.io.fields.optionMoveDown')"
                @click="moveOption(index, 1)"
              >
                <template #icon><n-icon :size="13"><ArrowDown /></n-icon></template>
              </n-button>
              <n-button
                size="small"
                quaternary
                type="error"
                :title="t('workflow.editor.io.fields.optionRemove')"
                @click="removeOption(index)"
              >
                <template #icon><n-icon :size="13"><Trash2 /></n-icon></template>
              </n-button>
            </div>
            <n-button size="small" dashed class="io-option-add" @click="addOption">
              <template #icon><n-icon :size="13"><Plus /></n-icon></template>
              {{ t('workflow.editor.io.fields.addOption') }}
            </n-button>
          </div>
        </n-form-item>
        <n-alert v-if="error" type="error" :show-icon="false" class="io-error">
          {{ t(error) }}
        </n-alert>
        <div class="io-form-footer">
          <n-button size="small" @click="exitEdit">{{ t('common.cancel') }}</n-button>
          <n-button size="small" type="primary" @click="commit">{{ t('workflow.editor.io.save') }}</n-button>
        </div>
      </n-form>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NCheckbox,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NSelect,
  NTabPane,
  NTabs,
} from 'naive-ui'
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from 'lucide-vue-next'

import {
  PORT_TYPE_KEYS,
  commitPort,
  createEmptyDraft,
  draftFromPort,
  portJsonToTypeKey,
  removePortByName,
  typeKeyUsesOptions,
  type PortDraft,
} from './ioAuthoring'
import type { PortJSON, WorkflowMeta } from './serializer'

/**
 * Authoring UI for workflow-level input/output ports (T6). All persistence
 * rules (type mapping, name validation, duplicate checks) live in the pure
 * ioAuthoring module; this component only manages modal/edit state and emits
 * an updated WorkflowMeta — it never mutates the prop.
 */
const props = defineProps<{
  show: boolean
  meta: WorkflowMeta
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'update:meta', value: WorkflowMeta): void
}>()

const { t } = useI18n()

type Side = 'inputs' | 'outputs'

const side = ref<Side>('inputs')
const editing = ref(false)
const originalName = ref<string | null>(null) // port being edited; null = adding
const draft = reactive<PortDraft>(createEmptyDraft())
const error = ref<string | null>(null) // IO_ERRORS i18n key, resolved on display

const ports = computed<PortJSON[]>(() => props.meta?.[side.value] ?? [])

const usesOptions = computed(() => typeKeyUsesOptions(draft.typeKey))

const typeOptions = computed(() =>
  PORT_TYPE_KEYS.map((key) => ({
    label: t(`workflow.editor.io.types.${key}`),
    value: key,
  })),
)

// Opening the modal always starts in list mode on the inputs tab.
watch(
  () => props.show,
  (open) => {
    if (!open) return
    side.value = 'inputs'
    exitEdit()
  },
)

function onSideChange(value: Side) {
  side.value = value
  exitEdit() // a draft belongs to one side only
}

function exitEdit() {
  editing.value = false
  originalName.value = null
  error.value = null
}

function loadDraft(source: PortDraft) {
  Object.assign(draft, source, { options: [...source.options] })
}

function startAdd() {
  loadDraft(createEmptyDraft())
  editing.value = true
  error.value = null
}

function startEdit(port: PortJSON) {
  loadDraft(draftFromPort(port))
  originalName.value = port.name
  editing.value = true
  error.value = null
}

// ---- options list editor ----------------------------------------------------

function setOption(index: number, value: string) {
  draft.options[index] = value
  error.value = null
}

function addOption() {
  draft.options.push('')
  error.value = null
}

function removeOption(index: number) {
  draft.options.splice(index, 1)
  error.value = null
}

function moveOption(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= draft.options.length) return
  const moved = draft.options[index]
  draft.options[index] = draft.options[target]
  draft.options[target] = moved
}

// ---- commit / remove ---------------------------------------------------------

function commit() {
  const result = commitPort(
    ports.value,
    { ...draft, options: [...draft.options] },
    originalName.value ?? undefined,
  )
  if (result.error) {
    error.value = result.error
    return
  }
  emit('update:meta', { ...props.meta, [side.value]: result.ports })
  exitEdit()
}

function removePort(port: PortJSON) {
  emit('update:meta', { ...props.meta, [side.value]: removePortByName(ports.value, port.name) })
}
</script>

<style scoped>
/*
 * Visual language mirrors the TemplateManager list rows and the page's modal
 * styles: app theme CSS variables (themes.css) only, 6px radii, 8/6/4px gaps.
 */
.io-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}

.io-empty {
  padding: 12px 0;
  font-size: 12px;
  color: var(--app-text-muted);
}

.io-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 360px;
  overflow-y: auto;
}

.io-row {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 6px;
}

.io-row:hover {
  background: var(--app-hover);
}

.io-row-body {
  flex: 1;
  min-width: 0;
}

.io-row-head {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.io-row-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.io-row-type {
  font-size: 11px;
  color: var(--app-text-dim);
}

.io-row-required {
  padding: 0 6px;
  font-size: 10px;
  color: var(--app-text-secondary);
  border: 1px solid var(--app-card-border);
  border-radius: 8px;
}

.io-row-desc {
  margin-top: 2px;
  overflow: hidden;
  font-size: 11px;
  color: var(--app-text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.io-row-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.io-add {
  align-self: flex-start;
}

.io-form-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.io-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.io-option-row {
  display: flex;
  gap: 6px;
  align-items: center;
  width: 100%;
}

.io-option-input {
  flex: 1;
  min-width: 0;
}

.io-option-add {
  align-self: flex-start;
}

.io-error {
  margin-top: 2px;
}

.io-form-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 4px;
}
</style>
