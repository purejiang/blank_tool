<template>
  <div class="template-manager">
    <n-button size="small" @click="openSave">
      <template #icon>
        <n-icon :size="14"><Save /></n-icon>
      </template>
      Save as Template
    </n-button>
    <n-button size="small" @click="openLoad">
      <template #icon>
        <n-icon :size="14"><FolderOpen /></n-icon>
      </template>
      Load Template
    </n-button>

    <!-- Save as Template: name + description dialog (todo 39) -->
    <n-modal
      v-model:show="saveVisible"
      preset="card"
      title="Save as Template"
      style="width: 420px"
      :mask-closable="!saving"
    >
      <n-form :model="saveForm" label-placement="top" size="small">
        <n-form-item
          label="Name"
          required
          :validation-status="nameInvalid ? 'error' : undefined"
          :feedback="nameInvalid
            ? 'Template name is required'
            : 'Stored as a JSON file — avoid path characters (\\, /, :)'"
        >
          <n-input
            v-model:value="saveForm.name"
            placeholder="my-workflow"
            :disabled="saving"
            @input="nameInvalid = false"
          />
        </n-form-item>
        <n-form-item label="Description">
          <n-input
            v-model:value="saveForm.description"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            placeholder="What this workflow does (optional)"
            :disabled="saving"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="tm-actions">
          <n-button :disabled="saving" @click="saveVisible = false">Cancel</n-button>
          <n-button type="primary" :loading="saving" @click="submitSave">Save</n-button>
        </div>
      </template>
    </n-modal>

    <!-- Load / delete: list of saved templates, fetched lazily on open -->
    <n-modal
      v-model:show="loadVisible"
      preset="card"
      title="Load Template"
      style="width: 560px"
    >
      <div v-if="listLoading" class="tm-status">Loading templates…</div>
      <div v-else-if="listError" class="tm-status tm-status-error" :title="listError">
        {{ listError }}
      </div>
      <div v-else-if="templates.length === 0" class="tm-status">
        No saved templates yet — use “Save as Template” to create one.
      </div>
      <div v-else class="tm-list">
        <div v-for="tpl in templates" :key="tpl.name" class="tm-item">
          <div class="tm-item-main">
            <div class="tm-item-head">
              <span class="tm-item-name" :title="tpl.name">{{ tpl.name }}</span>
              <span class="tm-item-meta">
                {{ tpl.node_count }} node(s) · updated {{ formatTime(tpl.updated_at) }}
              </span>
            </div>
            <div v-if="tpl.description" class="tm-item-desc" :title="tpl.description">
              {{ tpl.description }}
            </div>
          </div>
          <div class="tm-item-actions">
            <n-button
              size="small"
              type="primary"
              :loading="busyName === tpl.name"
              :disabled="busyName !== null && busyName !== tpl.name"
              @click="loadTemplate(tpl)"
            >
              Load
            </n-button>
            <n-button
              size="small"
              type="error"
              quaternary
              title="Delete template"
              :disabled="busyName !== null"
              @click="confirmDelete(tpl)"
            >
              <template #icon>
                <n-icon :size="13"><Trash2 /></n-icon>
              </template>
            </n-button>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="tm-actions">
          <n-button @click="loadVisible = false">Close</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { NButton, NForm, NFormItem, NIcon, NInput, NModal, useDialog, useMessage } from 'naive-ui'
import { FolderOpen, Save, Trash2 } from 'lucide-vue-next'
import unifiedApi from '@/api/unifiedApi'
import { log } from '@utils/logger'
import {
  deserializeWorkflow,
  type WorkflowDefinitionJSON,
} from './serializer'

/**
 * Canvas state emitted on template load — the exact shape returned by
 * the serializer's deserializeWorkflow (todo 37). The parent page applies
 * it to the vue-flow canvas (with ToolNode hydration, see the page).
 */
export type TemplateLoadPayload = ReturnType<typeof deserializeWorkflow>

/** One entry of the `template.list` response (template_handler.handle_list). */
interface TemplateInfo {
  name: string
  description: string
  created_at: string
  updated_at: string
  tags: string[]
  node_count: number
}

const props = defineProps<{
  /**
   * Snapshot of the current canvas as a WorkflowDefinition JSON, or null when
   * there is nothing to save (empty canvas). TemplateManager overrides the
   * definition's name/description with the dialog values before template.save;
   * tags are stored empty (tags UI is deliberately out of MVP scope).
   */
  getDefinition: () => WorkflowDefinitionJSON | null
}>()

const emit = defineEmits<{
  (e: 'load', payload: TemplateLoadPayload): void
}>()

const message = useMessage()
const dialog = useDialog()

function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// ---------------------------------------------------------------------------
// Save as Template
// ---------------------------------------------------------------------------

const saveVisible = ref(false)
const saving = ref(false)
const nameInvalid = ref(false)
const saveForm = reactive({ name: '', description: '' })

function openSave() {
  if (!props.getDefinition()) {
    message.warning('The canvas is empty — add nodes before saving a template')
    return
  }
  saveForm.name = ''
  saveForm.description = ''
  nameInvalid.value = false
  saveVisible.value = true
}

async function submitSave() {
  const name = saveForm.name.trim()
  if (!name) {
    nameInvalid.value = true
    return
  }
  const definition = props.getDefinition()
  if (!definition) {
    // Canvas was emptied while the dialog was open.
    saveVisible.value = false
    message.warning('The canvas is empty — nothing to save')
    return
  }
  saving.value = true
  try {
    const description = saveForm.description.trim()
    await unifiedApi.call('template.save', {
      name,
      // Definition name/description mirror the template identity so the
      // stored WorkflowDefinition is self-consistent (name must be non-empty
      // per the backend schema).
      definition: { ...definition, name, description },
      description,
      tags: [],
    })
    message.success(`Template “${name}” saved`)
    saveVisible.value = false
  } catch (err) {
    log.error(`Failed to save template “${name}”:`, err)
    message.error(`Failed to save template: ${errMsg(err)}`)
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------------------
// Load / Delete
// ---------------------------------------------------------------------------

const loadVisible = ref(false)
const listLoading = ref(false)
const listError = ref('')
const templates = ref<TemplateInfo[]>([])
const busyName = ref<string | null>(null)

function openLoad() {
  loadVisible.value = true
  // Lazy fetch on every open — the list is not cached globally (MVP).
  loadTemplates()
}

async function loadTemplates() {
  listLoading.value = true
  listError.value = ''
  try {
    const result = await unifiedApi.call<{ templates?: TemplateInfo[] }>('template.list', {})
    templates.value = Array.isArray(result?.templates) ? result.templates : []
  } catch (err) {
    log.error('Failed to list templates:', err)
    listError.value = `Failed to load templates: ${errMsg(err)}`
    templates.value = []
  } finally {
    listLoading.value = false
  }
}

async function loadTemplate(tpl: TemplateInfo) {
  busyName.value = tpl.name
  try {
    const result = await unifiedApi.call<{ definition?: WorkflowDefinitionJSON }>(
      'template.load',
      { name: tpl.name },
    )
    if (!result?.definition || typeof result.definition !== 'object') {
      throw new Error(`template “${tpl.name}” returned no definition`)
    }
    // Throws on a structurally invalid definition (serializer validation,
    // todo 37) — surfaced as an error toast below.
    const payload = deserializeWorkflow(result.definition)
    emit('load', payload)
    message.success(`Template “${tpl.name}” loaded`)
    loadVisible.value = false
  } catch (err) {
    log.error(`Failed to load template “${tpl.name}”:`, err)
    message.error(`Failed to load template: ${errMsg(err)}`)
  } finally {
    busyName.value = null
  }
}

function confirmDelete(tpl: TemplateInfo) {
  dialog.warning({
    title: 'Delete Template',
    content: `Delete template “${tpl.name}”? This cannot be undone.`,
    positiveText: 'Delete',
    negativeText: 'Cancel',
    onPositiveClick: () => {
      void deleteTemplate(tpl)
    },
  })
}

async function deleteTemplate(tpl: TemplateInfo) {
  busyName.value = tpl.name
  try {
    await unifiedApi.call('template.delete', { name: tpl.name })
    message.success(`Template “${tpl.name}” deleted`)
    // Refresh the list from the store (source of truth).
    await loadTemplates()
  } catch (err) {
    log.error(`Failed to delete template “${tpl.name}”:`, err)
    message.error(`Failed to delete template: ${errMsg(err)}`)
  } finally {
    busyName.value = null
  }
}

/** ISO-8601 timestamps from the backend store → locale string (fallback: raw). */
function formatTime(iso: string): string {
  if (!iso) return 'unknown'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}
</script>

<style scoped>
/*
 * Toolbar row fragment: mounted in the page's .we-toolbar. Colors are the app
 * theme tokens (themes.css); modal content inherits the Naive UI theme from
 * App.vue's n-config-provider. List rows mirror the palette item styling
 * (WorkflowNodePalette) for a consistent monochrome MVP surface.
 */
.template-manager {
  display: flex;
  gap: 8px;
  align-items: center;
}

.tm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.tm-status {
  padding: 12px 0;
  font-size: 12px;
  color: var(--app-text-muted);
}

.tm-status-error {
  color: var(--app-red);
}

.tm-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 400px;
  overflow-y: auto;
}

.tm-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 6px;
}

.tm-item:hover {
  background: var(--app-hover);
}

.tm-item-main {
  flex: 1;
  min-width: 0;
}

.tm-item-head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: space-between;
}

.tm-item-name {
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tm-item-meta {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--app-text-dim);
}

.tm-item-desc {
  margin-top: 2px;
  overflow: hidden;
  font-size: 11px;
  color: var(--app-text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tm-item-actions {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-shrink: 0;
}
</style>
