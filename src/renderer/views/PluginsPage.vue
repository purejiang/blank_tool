<template>
  <div class="plugins-page app-page">
    <div class="app-page-header">
      <div>
        <h2 class="app-page-title">{{ t('plugins.title') }}</h2>
        <p class="app-page-sub">{{ t('plugins.subtitle') }}</p>
      </div>
      <div class="head-actions">
        <n-button size="small" quaternary @click="onImport">
          <template #icon><n-icon><Upload /></n-icon></template>
          {{ t('plugins.import') }}
        </n-button>
        <n-button size="small" quaternary :disabled="!selected" @click="onExport">
          <template #icon><n-icon><Download /></n-icon></template>
          {{ t('plugins.export') }}
        </n-button>
      </div>
    </div>

    <div class="pl-cols">
      <!-- LEFT: plugin list -->
      <aside class="pl-col pl-left">
        <!-- 重新加载是全局动作（重扫内置 + 用户目录），所以只放这里一处，
             不在每个 item 上重复一个「刷新」——那样点哪个都刷全部，误导。 -->
        <div class="pl-left-head">
          <span class="pl-left-title">{{ t('plugins.listLabel') }}</span>
          <n-button
            size="tiny"
            quaternary
            :loading="reloading"
            :title="t('plugins.reloadHint')"
            @click="onReload"
          >
            <template #icon><n-icon><RotateCcw /></n-icon></template>
            {{ t('plugins.refresh') }}
          </n-button>
        </div>
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
              <span class="pl-name" :title="pluginLabel(p)">{{ pluginLabel(p) }}</span>
              <n-tag v-if="p.builtin" size="tiny" :bordered="false" class="pl-kind">{{ t('plugins.builtin') }}</n-tag>
              <n-tag size="tiny" :bordered="false" class="pl-ver">{{ p.version }}</n-tag>
              <!-- 删除是逐项动作 → 挂在每项右端（刷新/导入/导出是全局或选中态动作，留在页头） -->
              <n-button
                size="tiny"
                quaternary
                circle
                type="error"
                class="pl-del"
                :disabled="running"
                :title="t('plugins.delete')"
                @click.stop="onDelete(p)"
              >
                <template #icon><n-icon><Trash2 /></n-icon></template>
              </n-button>
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
            <span class="pl-detail-name">{{ selectedLabel }}</span>
            <n-tag v-if="selected.builtin" size="tiny" :bordered="false" class="pl-kind">{{ t('plugins.builtin') }}</n-tag>
            <!-- the id stays the identity every plugin.* call uses; show it
                 when the package ships a friendlier manifest name -->
            <span v-if="selectedIdAlias" class="pl-detail-id" :title="selectedIdAlias">
              {{ t('plugins.idLabel') }} {{ selectedIdAlias }}
            </span>
            <span class="pl-detail-meta">
              v{{ selected.version }} · {{ selected.author }}
              <template v-if="selected.params?.length"> · {{ t('plugins.paramCount', { n: selected.params.length }) }}</template>
            </span>
          </div>
          <p class="pl-detail-desc">{{ selected.description }}</p>

          <!-- 自定义 UI 模式：整块右侧交给插件自己的界面（运行按钮 / 日志 / 结果
               都由它渲染，宿主只负责转发日志与结果，否则会出现「里面一个运行按钮、
               外面又一个」和两套日志）。按 ui_path 声明切模式（而非 html 是否已
               加载），加载间隙显示占位——否则表单+运行按钮会闪出来一帧。 -->
          <template v-if="isUiPlugin">
            <iframe
              v-if="uiHtmlFor === selected!.name"
              ref="uiFrameEl"
              class="pl-ui-frame"
              sandbox="allow-scripts"
              :srcdoc="uiHtml"
            ></iframe>
            <div v-else class="pl-ui-loading">{{ t('plugins.uiLoading') }}</div>
          </template>

          <!-- 无自定义 UI：宿主渲染 参数表单 + 运行/停止 + 日志 + 结果 -->
          <template v-else>
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
                type="primary" size="small"               :disabled="missingRequired"
                @click="runPlugin()"
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
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NCheckbox, NIcon, NInput, NInputNumber, NScrollbar, NTag, useDialog, useMessage } from 'naive-ui'
import { Download, FolderOpen, Play, RotateCcw, Square, Trash2, Upload } from 'lucide-vue-next'
import pluginService, { type PluginInfo } from '@services/PluginService'
import serviceManager from '@services/ServiceManager'
import { useDeviceStore } from '@stores/deviceStore'
import { genId } from '@utils/id'
import { readTextFile } from '@utils/readTextFile'

const { t } = useI18n()
const message = useMessage()
// in-app confirmations: the native dialog.showMessageBox ignores the app theme
// and looks nothing like the rest of the UI → use Naive's dialog everywhere
const dialog = useDialog()
// device snapshot served to plugin UIs via the getDevices bridge message
const deviceStore = useDeviceStore()

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
// custom UI mode (package plugins with manifest ui)
const uiHtml = ref('')
/** which plugin's html uiHtml currently holds — the iframe renders only when
 *  it equals the selected plugin's name (prevents cross-plugin bleed-through) */
const uiHtmlFor = ref('')
/** mode is decided by the DECLARATION (ui_path), not by load state — otherwise
 *  the form+run-button branch flashes during the async ui load on every switch */
const isUiPlugin = computed(() => !!selected.value?.ui_path)
const uiFrameEl = ref<HTMLIFrameElement | null>(null)

/**
 * Injected into the plugin ui html before it lands in the srcdoc iframe.
 * The iframe is sandboxed (allow-scripts only, opaque origin) — its ONLY
 * channel to the app is postMessage; `window.pluginBridge` is the thin
 * wrapper plugins are supposed to use.
 */
const BRIDGE_SCRIPT = `<script>
(function () {
  var handlers = { log: [], result: [], error: [], meta: [], devices: [], file: [], dir: [], confirm: [] };
  window.addEventListener('message', function (e) {
    var d = e.data || {};
    if (d.type === '__bridge.log') handlers.log.forEach(function (f) { f(d.text, d.level); });
    else if (d.type === '__bridge.result') handlers.result.forEach(function (f) { f(d.payload); });
    else if (d.type === '__bridge.error') handlers.error.forEach(function (f) { f(d.message); });
    else if (d.type === '__bridge.meta') handlers.meta.forEach(function (f) { f(d.info); });
    else if (d.type === '__bridge.devices') handlers.devices.forEach(function (f) { f(d.devices); });
    else if (d.type === '__bridge.file') handlers.file.forEach(function (f) { f(d.canceled, d.filePath); });
    else if (d.type === '__bridge.dir') handlers.dir.forEach(function (f) { f(d.canceled, d.dirPath); });
    else if (d.type === '__bridge.confirm') handlers.confirm.forEach(function (f) { f(d.ok); });
  });
  window.pluginBridge = {
    run: function (params) { parent.postMessage({ type: 'plugin.run', params: params || {} }, '*'); },
    cancel: function () { parent.postMessage({ type: 'plugin.cancel' }, '*'); },
    log: function (text, level) { parent.postMessage({ type: 'plugin.log', text: String(text == null ? '' : text), level: level || 'info' }, '*'); },
    getMeta: function () { parent.postMessage({ type: 'plugin.getMeta' }, '*'); },
    getDevices: function () { parent.postMessage({ type: 'plugin.getDevices' }, '*'); },
    pickFile: function (options) { parent.postMessage({ type: 'plugin.pickFile', options: options || {} }, '*'); },
    pickDirectory: function (options) { parent.postMessage({ type: 'plugin.pickDirectory', options: options || {} }, '*'); },
    openPath: function (path, reveal) { parent.postMessage({ type: 'plugin.openPath', path: String(path == null ? '' : path), reveal: !!reveal }, '*'); },
    toast: function (text, level) { parent.postMessage({ type: 'plugin.toast', text: String(text == null ? '' : text), level: level || 'info' }, '*'); },
    confirm: function (title, content) { parent.postMessage({ type: 'plugin.confirm', title: String(title == null ? '' : title), content: String(content == null ? '' : content) }, '*'); },
    onLog: function (f) { handlers.log.push(f); },
    onResult: function (f) { handlers.result.push(f); },
    onError: function (f) { handlers.error.push(f); },
    onMeta: function (f) { handlers.meta.push(f); },
    onDevices: function (f) { handlers.devices.push(f); },
    onFile: function (f) { handlers.file.push(f); },
    onDir: function (f) { handlers.dir.push(f); },
    onConfirm: function (f) { handlers.confirm.push(f); }
  };
  parent.postMessage({ type: 'plugin.ready' }, '*');
})();
<\/script>`

function injectBridge(html: string) {
  if (/<head[^>]*>/i.test(html)) {
    return html.replace(/<head[^>]*>/i, (m) => m + BRIDGE_SCRIPT)
  }
  return BRIDGE_SCRIPT + html
}

function postToUi(type: string, extra: Record<string, unknown> = {}) {
  uiFrameEl.value?.contentWindow?.postMessage({ type, ...extra }, '*')
}

function metaFor(p: PluginInfo | null) {
  if (!p) return null
  return {
    name: p.name,
    display_name: p.display_name || p.name,
    version: p.version,
    author: p.author,
    description: p.description,
    params: p.params || [],
  }
}

async function loadCustomUi(p: PluginInfo) {
  // uiHtmlFor tracks which plugin uiHtml belongs to: the iframe only renders
  // when it matches the current selection, so switching plugins shows the
  // loading placeholder instead of the PREVIOUS plugin's UI (or the form).
  if (!p.ui_path) {
    uiHtml.value = ''
    uiHtmlFor.value = ''
    return
  }
  try {
    // readTextFile unwraps the { success, data } IPC envelope — passing the
    // raw result to srcdoc would render the string "[object Object]"
    uiHtml.value = injectBridge(await readTextFile(p.ui_path))
    uiHtmlFor.value = p.name
  } catch (e: any) {
    uiHtml.value = ''
    uiHtmlFor.value = ''
    message.error(`${t('plugins.uiReadFail')}: ${e?.message || String(e)}`)
  }
}

/** whitelist bridge for the sandboxed plugin iframe */
function onWindowMessage(e: MessageEvent) {
  const frame = uiFrameEl.value
  if (!frame || e.source !== frame.contentWindow) return
  const d: any = e.data || {}
  if (typeof d.type !== 'string' || !d.type.startsWith('plugin.')) return
  switch (d.type) {
    case 'plugin.ready':
    case 'plugin.getMeta':
      postToUi('__bridge.meta', { info: metaFor(selected.value) })
      break
    case 'plugin.run':
      void runPlugin(d.params)
      break
    case 'plugin.cancel':
      void stopRun()
      break
    case 'plugin.log':
      pushLog(String(d.text ?? ''), d.level === 'warn' || d.level === 'error' ? d.level : 'info')
      break
    case 'plugin.getDevices':
      // read-only snapshot: id + display fields only, no device handles
      postToUi('__bridge.devices', {
        devices: deviceStore.devices.map((dev: any) => ({
          id: String(dev.id ?? ''),
          name: String(dev.name ?? ''),
          status: String(dev.status ?? ''),
        })),
      })
      break
    case 'plugin.pickFile': {
      // native open dialog via the existing IPC wrapper; only the picked
      // path string ever crosses back into the sandbox
      const api = window.electronAPI as any
      void (async () => {
        try {
          const res = await api.selectFile({
            properties: ['openFile'],
            ...(typeof d.options === 'object' && d.options ? d.options : {}),
          })
          postToUi('__bridge.file', {
            canceled: !res || res.canceled || !res.filePaths?.length,
            filePath: res?.filePaths?.[0] || '',
          })
        } catch (err: any) {
          postToUi('__bridge.file', { canceled: true, filePath: '' })
          pushLog(`pickFile failed: ${err?.message || String(err)}`, 'error')
        }
      })()
      break
    }
    case 'plugin.pickDirectory': {
      // directory flavor of pickFile — same native dialog, directory mode
      const api = window.electronAPI as any
      void (async () => {
        try {
          const res = await api.selectDirectory({
            properties: ['openDirectory'],
            ...(typeof d.options === 'object' && d.options ? d.options : {}),
          })
          postToUi('__bridge.dir', {
            canceled: !res || res.canceled || !res.filePaths?.length,
            dirPath: res?.filePaths?.[0] || '',
          })
        } catch (err: any) {
          postToUi('__bridge.dir', { canceled: true, dirPath: '' })
          pushLog(`pickDirectory failed: ${err?.message || String(err)}`, 'error')
        }
      })()
      break
    }
    case 'plugin.openPath': {
      // open a file/dir via the OS (reveal=true → explorer selects it);
      // failures surface in the plugin console, no reply message
      const api = window.electronAPI as any
      void (async () => {
        try {
          const res = await api.openPath(String(d.path ?? ''), d.reveal ? { reveal: true } : null)
          if (res && res.success === false) {
            pushLog(`openPath failed: ${res.error || 'unknown'}`, 'error')
          }
        } catch (err: any) {
          pushLog(`openPath failed: ${err?.message || String(err)}`, 'error')
        }
      })()
      break
    }
    case 'plugin.toast': {
      // host-side light toast; level → naive message variant
      const text = String(d.text ?? '')
      if (d.level === 'success') message.success(text)
      else if (d.level === 'error') message.error(text)
      else if (d.level === 'warning') message.warning(text)
      else message.info(text)
      break
    }
    case 'plugin.confirm': {
      // in-app confirm (naive dialog); resolves via __bridge.confirm{ok}
      dialog.warning({
        title: String(d.title ?? ''),
        content: String(d.content ?? ''),
        positiveText: t('common.confirm'),
        negativeText: t('common.cancel'),
        onPositiveClick: () => postToUi('__bridge.confirm', { ok: true }),
        onNegativeClick: () => postToUi('__bridge.confirm', { ok: false }),
        onMaskClick: () => postToUi('__bridge.confirm', { ok: false }),
        onEsc: () => postToUi('__bridge.confirm', { ok: false }),
      })
      break
    }
  }
}

/**
 * Display label: package plugins may ship a friendlier `manifest.name`,
 * which the backend exposes as `display_name`. The id (`p.name`) never
 * changes — it stays what run/export/delete are called with.
 */
function pluginLabel(p: PluginInfo | null | undefined): string {
  return p?.display_name || p?.name || ''
}

const selectedLabel = computed(() => pluginLabel(selected.value))
/** the id, shown only when it differs from the display label */
const selectedIdAlias = computed(() =>
  selected.value && selectedLabel.value !== selected.value.name ? selected.value.name : '',
)

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
    // explicit level (plugin bridge log) wins over text-derived level
    return { ts: l.ts, body: n.body, level: l.level !== 'info' ? l.level : n.level }
  })
  return onlyErrors.value ? list.filter((l) => l.level !== 'info') : list
})

async function scrollBottom() {
  await nextTick()
  const el = consoleEl.value
  if (el) el.scrollTop = el.scrollHeight
}

function pushLog(text: string, level: 'info' | 'warn' | 'error' = 'info') {
  logs.value.push({ ts: Date.now() / 1000, text: String(text), level })
  scrollBottom()
  // 自定义 UI 模式下宿主不渲染日志面板 → 同一行转发给插件自己的界面
  if (uiHtml.value) {
    const n = normalizeLog(String(text))
    postToUi('__bridge.log', { text: n.body, level: level !== 'info' ? level : n.level })
  }
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

async function onImport() {
  const api = window.electronAPI as any
  const res = await api.showOpenDialog({
    title: t('plugins.import'),
    properties: ['openFile'],
    filters: [{ name: 'Plugin Package', extensions: ['zip'] }],
  })
  if (!res || res.canceled || !Array.isArray(res.filePaths) || !res.filePaths.length) return
  try {
    let out = await pluginService.importPackage(res.filePaths[0], false)
    if (!Array.isArray(out)) {
      // same-id plugin already installed — confirm before wiping it
      const pending = out as { needs_overwrite: boolean; id: string }
      const okToOverwrite = await new Promise<boolean>((resolve) => {
        dialog.warning({
          title: t('plugins.overwriteTitle'),
          content: t('plugins.overwriteMsg', { id: pending.id }),
          positiveText: t('common.confirm'),
          negativeText: t('common.cancel'),
          onPositiveClick: () => resolve(true),
          onNegativeClick: () => resolve(false),
          onMaskClick: () => resolve(false),
          onEsc: () => resolve(false),
        })
      })
      if (!okToOverwrite) {
        message.info(t('plugins.cancelled'))
        return
      }
      out = await pluginService.importPackage(res.filePaths[0], true)
    }
    plugins.value = out as PluginInfo[]
    message.success(t('plugins.importDone'))
  } catch (e: any) {
    message.error(e?.message || String(e))
  }
}

async function onExport() {
  const p = selected.value
  if (!p) {
    message.warning(t('plugins.exportNeedSelect'))
    return
  }
  const api = window.electronAPI as any
  const res = await api.showSaveDialog({
    title: t('plugins.export'),
    defaultPath: `${p.name}.zip`,
    filters: [{ name: 'Plugin Package', extensions: ['zip'] }],
  })
  if (!res || res.canceled || !res.filePath) return
  try {
    await pluginService.exportPackage(p.name, res.filePath)
    message.success(t('plugins.exportDone'))
  } catch (e: any) {
    message.error(e?.message || String(e))
  }
}

/** 逐项删除：确认框走应用内 Naive dialog（原生 message box 不跟主题） */
function onDelete(p: PluginInfo) {
  if (running.value) return
  const who = pluginLabel(p)
  dialog.warning({
    title: t('plugins.deleteTitle'),
    content: p.builtin
      ? t('plugins.deleteBuiltinMsg', { name: who })
      : t('plugins.deleteMsg', { name: who }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    // async onPositiveClick keeps the dialog open (positive button in loading)
    // until the backend answers — no stale list while the rescan runs
    onPositiveClick: async () => {
      try {
        plugins.value = await pluginService.deletePlugin(p.name)
        // the deleted plugin is gone from the refreshed list — drop the selection
        if (selected.value && !plugins.value.some((x) => x.name === selected.value!.name)) {
          selected.value = null
        }
        message.success(t('plugins.deleteDone', { name: who }))
      } catch (e: any) {
        message.error(e?.message || String(e))
      }
    },
  })
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
  void loadCustomUi(p)
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

async function runPlugin(paramsOverride?: Record<string, unknown>) {
  if (running.value || !selected.value) return
  const name = selected.value.name
  // form/JSON params are the base; iframe-supplied params win per key
  const params = { ...buildParams(), ...(paramsOverride && typeof paramsOverride === 'object' ? paramsOverride : {}) }
  const api = window.electronAPI
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
      // custom UI owns the result panel — hand the payload over
      if (uiHtml.value) postToUi('__bridge.result', { payload })
    },
    onError: (msg: string) => {
      pushLog('[ERROR] ' + msg)
      running.value = false
      if (uiHtml.value) postToUi('__bridge.error', { message: msg })
    },
    onCancelled: () => {
      pushLog('[CANCELLED]')
      running.value = false
      // 取消也算一次结束：用 result 通道让插件 UI 复位按钮
      if (uiHtml.value) postToUi('__bridge.result', { payload: { success: false, cancelled: true } })
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
  const api = window.electronAPI
  if (api && typeof api.cancelRequest === 'function') {
    try { await api.cancelRequest(taskId.value) } catch { /* ignore */ }
  }
}

onMounted(() => {
  void fetchPlugins()
  window.addEventListener('message', onWindowMessage)
})

onUnmounted(() => {
  window.removeEventListener('message', onWindowMessage)
})
</script>

<style scoped>
.plugins-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
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
.pl-left-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 8px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--app-card-border);
}
.pl-left-title { font-size: var(--app-font-size-sm); font-weight: 600; color: var(--app-text-primary); }
.pl-scroll { flex: 1; min-height: 0; }

/* left list */
.pl-item { padding: 8px 10px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; }
.pl-item:hover { background: var(--app-hover); }
.pl-item.active { background: var(--app-blue-bg); border-color: var(--app-blue); }
.pl-item-head { display: flex; align-items: center; gap: 6px; }
.pl-name { flex: 1; min-width: 0; font-size: var(--app-font-size-md); font-weight: 600; color: var(--app-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pl-ver { flex: none; font-variant-numeric: tabular-nums; }
.pl-kind { flex: none; opacity: .75; }
/* per-item delete: dimmed until the row is hovered/selected */
.pl-del { flex: none; opacity: .5; transition: opacity .12s ease; }
.pl-item:hover .pl-del, .pl-item.active .pl-del { opacity: 1; }
.pl-desc {
  font-size: var(--app-font-size-sm); color: var(--app-text-muted); margin-top: 2px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.pl-dir-hint {
  flex: none; margin-top: 8px; padding-top: 8px;
  border-top: 1px dashed var(--app-card-border);
  font-size: var(--app-font-size-xs); color: var(--app-text-muted);
  display: flex; gap: 6px; align-items: flex-start;
}
.hint-icon { flex: none; margin-top: 1px; }

/* right detail */
.pl-empty { padding: 24px 8px; text-align: center; color: var(--app-text-muted); font-size: var(--app-font-size-sm); }
.pl-right-empty { flex: 1; display: flex; align-items: center; justify-content: center; }
.pl-detail-head { display: flex; align-items: baseline; gap: 8px; flex: none; }
.pl-detail-name { font-size: var(--app-font-size-xl); font-weight: 600; color: var(--app-text-primary); }
.pl-detail-id {
  flex: none; align-self: center;
  font-family: var(--app-font-mono); font-size: var(--app-font-size-xs);
  color: var(--app-text-muted); background: var(--app-code-bg);
  border-radius: 4px; padding: 1px 6px;
}
.pl-detail-meta { font-size: var(--app-font-size-sm); color: var(--app-text-muted); }
.pl-detail-desc { margin: 4px 0 10px; font-size: var(--app-font-size-sm); color: var(--app-text-secondary, var(--app-text-muted)); flex: none; }

.pl-form { display: flex; flex-direction: column; gap: 8px; flex: none; margin-bottom: 10px; }
.pl-field { display: flex; align-items: center; gap: 8px; }
.pl-field-label { width: 140px; flex: none; font-size: var(--app-font-size-sm); color: var(--app-text-primary); text-align: right; }
.pl-req { color: var(--app-red); margin-left: 4px; font-size: var(--app-font-size-xs); }
.pl-field-input { flex: 1; }
.pl-json { flex: none; margin-bottom: 10px; }
.pl-json-label { font-size: var(--app-font-size-sm); color: var(--app-text-muted); margin-bottom: 4px; }

.pl-run-row { display: flex; align-items: center; gap: 8px; flex: none; margin-bottom: 10px; }
.pl-req-hint { font-size: var(--app-font-size-xs); color: var(--app-red); }

/* console + result share the same skin */
.pl-ui-frame {
  flex: 1;
  min-height: 0;
  width: 100%;
  border: 1px solid var(--app-card-border);
  border-radius: 8px;
  background: var(--app-card-bg);
}
.pl-ui-loading {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--app-font-size-md);
  color: var(--app-text-muted);
  border: 1px solid var(--app-card-border);
  border-radius: 8px;
  background: var(--app-card-bg);
}
.pl-console, .pl-result { flex: none; display: flex; flex-direction: column; border: 1px solid var(--app-card-border); border-radius: 8px; overflow: hidden; }
.pl-console { flex: 1; min-height: 0; }
.pl-console-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 5px 10px; font-size: var(--app-font-size-sm); font-weight: 600; color: var(--app-text-primary);
  border-bottom: 1px solid var(--app-card-border); flex: none;
}
.pl-console-body { flex: 1; min-height: 0; overflow: auto; padding: 6px 10px; font-family: var(--app-font-mono); font-size: var(--app-font-size-sm); background: var(--app-code-bg, transparent); }
.pl-console-empty { color: var(--app-text-muted); font-size: var(--app-font-size-sm); padding: 12px 0; text-align: center; }
.pl-line { white-space: pre-wrap; word-break: break-all; color: var(--app-text-primary); }
.pl-line.lv-warn { color: var(--app-yellow); }
.pl-line.lv-error { color: var(--app-red); }
.pl-result-body {
  margin: 0; padding: 8px 10px; overflow: auto; max-height: 160px;
  font-family: var(--app-font-mono); font-size: var(--app-font-size-sm); color: var(--app-text-primary);
}
</style>
