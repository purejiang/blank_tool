<template>
  <div class="plugins-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">{{ t('plugins.title') }}</h2>
        <p class="page-subtitle">{{ t('plugins.subtitle') }}</p>
      </div>
      <div class="head-actions">
        <n-tooltip placement="bottom">
          <template #trigger>
            <n-button size="small" quaternary @click="fetchPlugins">
              <template #icon><n-icon><RefreshCw /></n-icon></template>
              {{ t('plugins.refresh') }}
            </n-button>
          </template>
          {{ t('plugins.reloadHint') }}
        </n-tooltip>
        <n-button size="small" :loading="reloading" @click="onReload">
          <template #icon><n-icon><RotateCcw /></n-icon></template>
          {{ t('plugins.reload') }}
        </n-button>
      </div>
    </div>

    <div class="pl-cols">
      <!-- LEFT: plugin list -->
      <aside class="pl-col pl-left">
        <n-scrollbar class="pl-scroll">
          <div v-if="!plugins.length && !loading" class="pl-empty">{{ t('plugins.empty') }}</div>
          <div
            v-for="p in plugins"
            :key="p.name"
            class="pl-item"
            :class="{ active: p.name === selected?.name }"
            @click="select(p)"
          >
            <div class="pl-item-head">
              <span class="pl-name">{{ p.name }}</span>
              <n-tag size="tiny" :bordered="false" class="pl-ver">{{ p.version }}</n-tag>
            </div>
            <div class="pl-desc">{{ p.description }}</div>
          </div>
        </n-scrollbar>
        <div class="pl-dir-hint">
          <FolderOpen class="hint-icon" :size="13" />
          <span>{{ t('plugins.userDirHint') }}</span>
        </div>
      </aside>

      <!-- RIGHT: detail + run console -->
      <section class="pl-col pl-right">
        <template v-if="selected">
          <div class="pl-detail-head">
            <span class="pl-detail-name">{{ selected.name }}</span>
            <span class="pl-detail-meta">
              v{{ selected.version }} · {{ selected.author }}
              <template v-if="selected.params?.length"> · {{ t('plugins.paramCount', { n: selected.params.length }) }}</template>
            </span>
          </div>
          <p class="pl-detail-desc">{{ selected.description }}</p>

          <!-- params form / raw JSON fallback -->
          <div v-if="hasDeclaredParams" class="pl-form">
            <div v-for="param in selected!.params" :key="param.key" class="pl-field">
              <label class="pl-field-label">
                {{ param.label || param.key }}
                <span v-if="param.required" class="pl-req">{{ t('plugins.required') }}</span>
              </label>
              <n-checkbox
                v-if="param.type === 'bool'"
                size="small"
                :checked="!!formValues[param.key]"
                @update:checked="formValues[param.key] = $event"
              >
                {{ param.label || param.key }}
              </n-checkbox>
              <n-input-number
                v-else-if="param.type === 'number'"
                v-model:value="formValues[param.key]"
                size="small"
                class="pl-field-input"
              />
              <n-input
                v-else
                v-model:value="formValues[param.key]"
                size="small"
                class="pl-field-input"
                :placeholder="String(param.default ?? '')"
              />
            </div>
          </div>
          <div v-else class="pl-json">
            <div class="pl-json-label">{{ t('plugins.rawJson') }}</div>
            <n-input
              v-model:value="rawJson"
              type="textarea"
              size="small"
              :rows="3"
              placeholder='{"key": "value"}'
            />
          </div>

          <div class="pl-run-row">
            <n-button
              v-if="!running"
              type="primary" size="small" :disabled="missingRequired"
              @click="runPlugin"
            >
              <template #icon><n-icon><Play /></n-icon></template>
              {{ t('plugins.run') }}
            </n-button>
            <n-button v-else type="warning" size="small" @click="stopRun">
              <template #icon><n-icon><Square /></n-icon></template>
              {{ t('plugins.stop') }}
            </n-button>
            <span v-if="missingRequired" class="pl-req-hint">{{ t('plugins.missingRequired') }}</span>
          </div>

          <!-- log console -->
          <div class="pl-console">
            <div class="pl-console-head">
              <span>{{ t('plugins.logs') }}</span>
              <n-checkbox v-if="logs.length" v-model:checked="onlyErrors" size="small">
                {{ t('plugins.onlyErrors') }}
              </n-checkbox>
            </div>
            <div ref="consoleEl" class="pl-console-body">
              <div v-if="!shownLogs.length" class="pl-console-empty">{{ t('plugins.noLogs') }}</div>
              <div
                v-for="(l, i) in shownLogs"
                :key="i"
                class="pl-line"
                :class="'lv-' + l.level"
              >{{ l.body }}</div>
            </div>
          </div>

          <!-- result -->
          <div v-if="result" class="pl-result">
            <div class="pl-console-head">
              <span>{{ t('plugins.result') }}</span>
            </div>
            <pre class="pl-result-body">{{ JSON.stringify(result, null, 2) }}</pre>
          </div>
        </template>
        <div v-else class="pl-empty pl-right-empty">{{ t('plugins.selectHint') }}</div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * PluginsPage — browse / run external .py plugins.
 *
 * Running a plugin is a STREAMING request (plugin.run is @streaming): the
 * page follows the same pattern as useScriptRunner (automation) — genId →
 * taskStream.bindTask + setCallbacks → callBackendAPI → waitForPhase.
 */
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NCheckbox, NIcon, NInput, NInputNumber, NScrollbar, NTag, NTooltip, useMessage } from 'naive-ui'
import { FolderOpen, Play, RefreshCw, RotateCcw, Square } from 'lucide-vue-next'
import pluginService, { type PluginInfo } from '@services/PluginService'
import serviceManager from '@services/ServiceManager'

const { t } = useI18n()
const message = useMessage()

const plugins = ref<PluginInfo[]>([])
const loading = ref(false)
const reloading = ref(false)
const selected = ref<PluginInfo | null>(null)
const formValues = reactive<Record<string, any>>({})
const rawJson = ref('{}')
const running = ref(false)
const taskId = ref('')
const logs = ref<{ ts: number; text: string; level: 'info' | 'warn' | 'error' }[]>([])
const result = ref<any>(null)
const onlyErrors = ref(false)
const consoleEl = ref<HTMLElement | null>(null)

const hasDeclaredParams = computed(() => !!selected.value?.params?.length)

const missingRequired = computed(() =>
  (selected.value?.params || [])
    .filter((p) => p.required)
    .some((p) => {
      const v = formValues[p.key]
      return v === undefined || v === null || String(v).trim() === ''
    }),
)

/** `[plugin] msg` → level + body（与 RunPanel.normalizeLog 同一约定） */
function normalizeLog(text: string) {
  let body = String(text)
  let level: 'info' | 'warn' | 'error' = 'info'
  if (/\[(FAIL|ERROR)\]/i.test(body)) level = 'error'
  else if (/\[(WARN|CANCEL)/i.test(body)) level = 'warn'
  const m = /^\[([A-Za-z_][\w.-]*)\]\s+([\s\S]*)$/.exec(body)
  if (m && !/^(FAIL|ERROR|WARN|CANCEL)/i.test(m[1])) body = m[2]
  return { body, level }
}

const shownLogs = computed(() => {
  const list = logs.value.map((l) => {
    const n = normalizeLog(l.text)
    return { ts: l.ts, ...n }
  })
  return onlyErrors.value ? list.filter((l) => l.level !== 'info') : list
})

async function scrollBottom() {
  await nextTick()
  const el = consoleEl.value
  if (el) el.scrollTop = el.scrollHeight
}

function pushLog(text: string) {
  logs.value.push({ ts: Date.now() / 1000, text: String(text), level: 'info' })
  scrollBottom()
}

async function fetchPlugins() {
  loading.value = true
  try {
    plugins.value = await pluginService.list()
  } catch (e: any) {
    message.error(e?.message || String(e))
  } finally {
    loading.value = false
  }
}

async function onReload() {
  reloading.value = true
  try {
    plugins.value = await pluginService.reload()
    // reselect if the selected plugin still exists
    if (selected.value && !plugins.value.some((p) => p.name === selected.value!.name)) {
      selected.value = null
    }
    message.success(t('plugins.reloadDone', { n: plugins.value.length }))
  } catch (e: any) {
    message.error(e?.message || String(e))
  } finally {
    reloading.value = false
  }
}

function select(p: PluginInfo) {
  if (running.value) return
  selected.value = p
  logs.value = []
  result.value = null
  onlyErrors.value = false
  Object.keys(formValues).forEach((k) => delete formValues[k])
  for (const param of p.params || []) {
    formValues[param.key] = param.type === 'bool'
      ? !!param.default
      : param.type === 'number'
        ? Number(param.default ?? 0)
        : String(param.default ?? '')
  }
  rawJson.value = '{}'
}

function buildParams(): Record<string, unknown> {
  if (hasDeclaredParams.value) {
    const out: Record<string, unknown> = {}
    for (const param of selected.value!.params || []) out[param.key] = formValues[param.key]
    return out
  }
  try {
    const parsed = JSON.parse(rawJson.value || '{}')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed
  } catch { /* fallthrough */ }
  return {}
}

function genId(): string {
  try {
    return (crypto as any).randomUUID()
  } catch {
    return 'pl-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8)
  }
}

async function runPlugin() {
  if (running.value || !selected.value) return
  const name = selected.value.name
  const params = buildParams()
  const api = (window as any).electronAPI
  const taskStream = (await serviceManager.getService('taskStream')) as any

  running.value = true
  logs.value = []
  result.value = null
  const id = genId()
  taskId.value = id
  taskStream.bindTask(id)
  taskStream.setCallbacks(id, {
    onLog: (line: string) => pushLog(line),
    onComplete: (payload: any) => {
      result.value = payload
      running.value = false
    },
    onError: (msg: string) => {
      pushLog('[ERROR] ' + msg)
      running.value = false
    },
    onCancelled: () => {
      pushLog('[CANCELLED]')
      running.value = false
    },
  })

  try {
    // plugin.run is @streaming: the init envelope resolves to undefined —
    // never test it for stream_id; failures arrive via callbacks/latch.
    await api.callBackendAPI('plugin.run', { name, params, task_id: id })
    await taskStream.waitForPhase(id, 'operation')
  } catch (e: any) {
    const m = e?.message
    if (m !== 'cancelled' && m !== 'unbound') {
      pushLog('[ERROR] ' + (m || String(e)))
      running.value = false
    }
  }
}

async function stopRun() {
  if (!taskId.value) return
  const api = (window as any).electronAPI
  if (api && typeof api.cancelRequest === 'function') {
    try { await api.cancelRequest(taskId.value) } catch { /* ignore */ }
  }
}

onMounted(fetchPlugins)
</script>

<style scoped>
.plugins-page {
  max-width: var(--page-max-width);
  margin: 0 auto;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; flex: none; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; color: var(--app-text-primary); }
.page-subtitle { margin: 2px 0 0; font-size: 12px; color: var(--app-text-muted); }
.head-actions { display: flex; gap: 8px; }

.pl-cols {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  gap: 12px;
  overflow: hidden;
}
.pl-col {
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 10px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}
.pl-scroll { flex: 1; min-height: 0; }

/* left list */
.pl-item { padding: 8px 10px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; }
.pl-item:hover { background: rgba(128, 128, 128, 0.08); }
.pl-item.active { background: var(--app-blue-bg); border-color: var(--app-blue); }
.pl-item-head { display: flex; align-items: center; gap: 6px; }
.pl-name { font-size: 13px; font-weight: 600; color: var(--app-text-primary); }
.pl-ver { font-variant-numeric: tabular-nums; }
.pl-desc {
  font-size: 12px; color: var(--app-text-muted); margin-top: 2px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.pl-dir-hint {
  flex: none; margin-top: 8px; padding-top: 8px;
  border-top: 1px dashed var(--app-card-border);
  font-size: 11px; color: var(--app-text-muted);
  display: flex; gap: 6px; align-items: flex-start;
}
.hint-icon { flex: none; margin-top: 1px; }

/* right detail */
.pl-empty { padding: 24px 8px; text-align: center; color: var(--app-text-muted); font-size: 12px; }
.pl-right-empty { flex: 1; display: flex; align-items: center; justify-content: center; }
.pl-detail-head { display: flex; align-items: baseline; gap: 8px; flex: none; }
.pl-detail-name { font-size: 15px; font-weight: 600; color: var(--app-text-primary); }
.pl-detail-meta { font-size: 12px; color: var(--app-text-muted); }
.pl-detail-desc { margin: 4px 0 10px; font-size: 12px; color: var(--app-text-secondary, var(--app-text-muted)); flex: none; }

.pl-form { display: flex; flex-direction: column; gap: 8px; flex: none; margin-bottom: 10px; }
.pl-field { display: flex; align-items: center; gap: 8px; }
.pl-field-label { width: 140px; flex: none; font-size: 12px; color: var(--app-text-primary); text-align: right; }
.pl-req { color: var(--app-red, #e05561); margin-left: 4px; font-size: 11px; }
.pl-field-input { flex: 1; }
.pl-json { flex: none; margin-bottom: 10px; }
.pl-json-label { font-size: 12px; color: var(--app-text-muted); margin-bottom: 4px; }

.pl-run-row { display: flex; align-items: center; gap: 8px; flex: none; margin-bottom: 10px; }
.pl-req-hint { font-size: 11px; color: var(--app-red, #e05561); }

/* console + result share the same skin */
.pl-console, .pl-result { flex: none; display: flex; flex-direction: column; border: 1px solid var(--app-card-border); border-radius: 8px; overflow: hidden; }
.pl-console { flex: 1; min-height: 0; }
.pl-console-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 5px 10px; font-size: 12px; font-weight: 600; color: var(--app-text-primary);
  border-bottom: 1px solid var(--app-card-border); flex: none;
}
.pl-console-body { flex: 1; min-height: 0; overflow: auto; padding: 6px 10px; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 12px; background: var(--app-code-bg, transparent); }
.pl-console-empty { color: var(--app-text-muted); font-size: 12px; padding: 12px 0; text-align: center; }
.pl-line { white-space: pre-wrap; word-break: break-all; color: var(--app-text-primary); }
.pl-line.lv-warn { color: var(--app-yellow, #f0a020); }
.pl-line.lv-error { color: var(--app-red, #e05561); }
.pl-result-body {
  margin: 0; padding: 8px 10px; overflow: auto; max-height: 160px;
  font-family: 'SFMono-Regular', Consolas, monospace; font-size: 12px; color: var(--app-text-primary);
}
</style>
