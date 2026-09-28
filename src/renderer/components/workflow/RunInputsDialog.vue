<template>
  <!-- M1 输入表单对话框（docs/08 §4）：按端口类型渲染控件、必填校验、JSON 解析校验。
       工作流列表的「试运行」与编辑器共用；S3 任务编辑页复用同一套 PortInput 控件
       （页面内嵌表单，不是对话框）。 -->
  <n-modal
    v-model:show="visible"
    preset="card"
    :title="title || t('workflow.editor.dialog.inputsTitle')"
    :style="{ width: '460px' }"
    :mask-closable="false"
    data-test="run-inputs-dialog"
  >
    <n-form v-if="ports.length > 0" :model="draft" label-placement="top" size="small">
      <n-form-item
        v-for="port in ports"
        :key="port.name"
        :label="port.name"
        :required="port.required !== false"
      >
        <!-- 运行期入参是字面量：不提供表达式绑定入口 -->
        <PortInput
          :value="draft[port.name]"
          :port="port"
          :allow-bindings="false"
          @update:value="(value: any) => (draft[port.name] = value)"
        />
        <template v-if="port.description" #feedback>
          <span class="rid-port-desc">{{ port.description }}</span>
        </template>
      </n-form-item>
    </n-form>
    <div v-else class="rid-no-inputs">{{ t('workflow.editor.dialog.noInputs') }}</div>

    <n-alert v-if="error" type="error" :show-icon="false" class="rid-error">{{ error }}</n-alert>

    <template #footer>
      <div class="rid-footer">
        <n-button size="small" @click="visible = false">
          {{ t('workflow.editor.dialog.cancel') }}
        </n-button>
        <n-button size="small" type="primary" :loading="loading" @click="submit">
          {{ t('workflow.editor.dialog.run') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAlert, NButton, NForm, NFormItem, NModal } from 'naive-ui'

import PortInput from './PortInput.vue'
import type { PortJSON, WorkflowDefinitionJSON } from './serializer'

/**
 * M1: collect a workflow's declared inputs before running it.
 *
 * The dialog owns validation (required + JSON parse) and emits a ready-to-send
 * `inputs` object; the caller owns the actual run (so the list page can use
 * `template.execute` while the editor uses `workflow.execute`).
 */
const props = defineProps<{
  show: boolean
  /** Definition whose `inputs` drive the form. */
  definition: WorkflowDefinitionJSON | null
  title?: string
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'submit', inputs: Record<string, unknown>): void
}>()

const { t } = useI18n()

const draft = reactive<Record<string, any>>({})
const error = ref<string | null>(null)

const visible = computed({
  get: () => props.show,
  set: (value: boolean) => emit('update:show', value),
})

const ports = computed<PortJSON[]>(() => {
  const raw = props.definition?.inputs
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (port): port is PortJSON => !!port && typeof port === 'object' && typeof port.name === 'string',
  )
})

const KNOWN_BASES = ['file', 'directory', 'text', 'number', 'boolean', 'json']

function baseOf(port: PortJSON): string {
  const base = String(port.type?.base ?? '').toLowerCase()
  return KNOWN_BASES.includes(base) ? base : 'text'
}

/** Seed the draft whenever the dialog opens for a (new) definition. */
watch(
  () => [props.show, props.definition] as const,
  ([open]) => {
    if (!open) return
    error.value = null
    for (const key of Object.keys(draft)) delete draft[key]
    for (const port of ports.value) {
      const base = baseOf(port)
      if (base === 'boolean') draft[port.name] = false
      else if (base === 'number') draft[port.name] = null
      else if (port.multi === true) draft[port.name] = []
      else draft[port.name] = ''
    }
  },
  { immediate: true },
)

function submit() {
  error.value = null
  const inputs: Record<string, unknown> = {}
  for (const port of ports.value) {
    let value = draft[port.name]
    if (value === undefined || value === null || value === '') {
      if (port.required !== false) {
        error.value = t('workflow.editor.execution.requiredInput', { name: port.name })
        return
      }
      continue // 空的可选入参不发送，与节点参数保持一致
    }
    if (baseOf(port) === 'json' && typeof value === 'string') {
      try {
        value = JSON.parse(value)
      } catch {
        error.value = t('workflow.editor.execution.invalidJson', { name: port.name })
        return
      }
    }
    inputs[port.name] = value
  }
  emit('submit', inputs)
}
</script>

<style scoped>
.rid-no-inputs {
  font-size: 12px;
  color: var(--app-text-muted);
}

.rid-error {
  margin-top: 10px;
}

.rid-port-desc {
  font-size: 11px;
  color: var(--app-text-dim);
}

.rid-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
