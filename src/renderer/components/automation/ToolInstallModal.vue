<template>
  <n-modal
    :show="show"
    :title="t('automation.toolsInstall')"
    preset="card"
    style="width: 640px"
    @update:show="emit('update:show', $event)"
  >
    <div data-testid="tool-install-modal" class="tim-root">
      <!-- probing: spinner instead of looking frozen -->
      <div v-if="probing" class="tim-probing">
        <n-spin size="small" />
      </div>

      <template v-else>
        <!-- ==================== Section 1: traffic capture (PC side) ==================== -->
        <section data-testid="traffic-section" class="tim-block">
          <div class="app-subhead">{{ t('automation.tools.sectionTraffic') }}</div>

          <!-- status row：与设置页的状态行同一套视觉（图标 + 状态 + 说明） -->
          <div class="tim-row">
            <div class="tim-icon" :style="{ color: trafficOk ? 'var(--app-green)' : 'var(--app-yellow)' }">
              <n-icon size="16"><CheckCircle v-if="trafficOk" /><AlertCircle v-else /></n-icon>
            </div>
            <div class="tim-info">
              <div class="tim-line">{{ t(trafficStateKey) }}</div>
              <div v-if="trafficStatus?.lib_path" class="tim-line tim-mono">{{ trafficStatus.lib_path }}</div>
            </div>
          </div>

          <div class="tim-actions">
            <n-button
              data-testid="install-mitmproxy-btn"
              size="small"
              type="primary"
              :loading="installingMitm"
              :disabled="installingMitm"
              @click="installMitm"
            >
              {{ t(trafficStatus?.installed ? 'automation.tools.reinstall' : 'automation.tools.installNow') }}
            </n-button>
          </div>

          <!-- streaming install log (last N lines, auto-scroll) -->
          <div v-if="mitmLogs.length || installingMitm" class="tim-log-wrap">
            <div class="tim-log-label">{{ t('automation.tools.installLog') }}</div>
            <div ref="mitmLogEl" data-testid="mitm-log" class="tim-log">
              <div v-for="(line, i) in mitmLogs" :key="i" class="tim-log-line">{{ line }}</div>
            </div>
          </div>

          <div v-if="mitmError" data-testid="mitm-error" class="tim-error">{{ mitmError }}</div>

          <!-- degraded: pip unavailable / install failed → copyable manual command -->
          <div v-if="degraded" class="tim-degraded">
            <div class="tim-warn">{{ t('automation.tools.degradedTitle') }}</div>
            <div data-testid="manual-command" class="tim-mono-block">{{ degraded.manual_command }}</div>
            <div class="tim-actions">
              <IconButton
                :icon="Copy"
                :label="t('automation.tools.copyCommand')"
                data-testid="copy-command-btn"
                size="tiny"
                quaternary
                @click="copyCommand"
              />
              <span v-if="copied === 'command'" class="tim-copied">{{ t('automation.copied') }}</span>
              <n-button size="tiny" quaternary data-testid="open-runtime-folder-btn" @click="openRuntimeFolder">
                {{ t('automation.tools.openFolder') }}
              </n-button>
            </div>
          </div>

          <!-- CA certificate row -->
          <div class="tim-row tim-ca-row">
            <div class="tim-icon" :style="{ color: trafficStatus?.ca_cert_exists ? 'var(--app-green)' : 'var(--app-yellow)' }">
              <n-icon size="16"><CheckCircle v-if="trafficStatus?.ca_cert_exists" /><AlertCircle v-else /></n-icon>
            </div>
            <div class="tim-info">
              <div class="tim-line">{{ t('automation.tools.caTitle') }}</div>
              <div v-if="certPath" class="tim-line tim-mono">{{ certPath }}</div>
              <div v-if="!trafficStatus?.ca_cert_exists" class="tim-hint">{{ t('automation.tools.caAutoHint') }}</div>
              <div v-if="caOk" class="tim-ok">{{ t('automation.tools.caInstallDone') }}</div>
              <div v-if="caError" data-testid="ca-error" class="tim-error">{{ caError }}</div>
            </div>
            <div class="tim-actions">
              <n-button v-if="certPath" size="tiny" quaternary @click="openCertFolder">
                {{ t('automation.tools.caOpenFolder') }}
              </n-button>
              <!-- disabled-reason tooltip: only explains WHY when it is blocked -->
              <n-tooltip :disabled="!caBlocked" placement="top">
                <template #trigger>
                  <span class="tim-btn-wrap">
                    <n-button
                      data-testid="install-ca-btn"
                      size="tiny"
                      :loading="installingCa"
                      :disabled="caBlocked"
                      @click="installCaCert"
                    >
                      {{ t('automation.tools.caInstall') }}
                    </n-button>
                  </span>
                </template>
                {{ t('automation.tools.caInstallDisabled') }}
              </n-tooltip>
            </div>
          </div>

          <!-- tutorial -->
          <div class="tim-tutorial">
            <div class="tim-hint">{{ t('automation.tools.tutorialTitle') }}</div>
            <ol class="tim-steps">
              <li v-for="k in TRAFFIC_TUTORIAL" :key="k">{{ t('automation.tools.tutorial.traffic.' + k) }}</li>
            </ol>
          </div>
        </section>

        <!-- ==================== Section 2: ADBKeyBoard (device side) ==================== -->
        <section data-testid="ime-section" class="tim-block">
          <div class="app-subhead">{{ t('automation.tools.sectionIme') }}</div>

          <div class="tim-row">
            <div class="tim-icon" :style="{ color: imeStatus?.installed ? 'var(--app-green)' : 'var(--app-yellow)' }">
              <n-icon size="16"><CheckCircle v-if="imeStatus?.installed" /><AlertCircle v-else /></n-icon>
            </div>
            <div class="tim-info">
              <div class="tim-line">
                {{ t('automation.tools.imeDevice') }}: {{ deviceId || t('automation.tools.imeNoDevice') }}
              </div>
              <div class="tim-line">
                {{ t(imeStateKey) }}<span v-if="imeStatus?.active"> · {{ t('automation.tools.imeActive') }}</span>
              </div>
            </div>
          </div>

          <div class="tim-actions">
            <n-tooltip :disabled="!!deviceId" placement="top">
              <template #trigger>
                <span class="tim-btn-wrap">
                  <n-button
                    data-testid="install-ime-btn"
                    size="small"
                    type="primary"
                    :loading="installingIme"
                    :disabled="installingIme || !deviceId"
                    @click="installImeOnline"
                  >
                    {{ t('automation.tools.imeDownloadInstall') }}
                  </n-button>
                </span>
              </template>
              {{ t('automation.tools.imeNeedDevice') }}
            </n-tooltip>
            <n-tooltip :disabled="!!deviceId" placement="top">
              <template #trigger>
                <span class="tim-btn-wrap">
                  <n-button
                    data-testid="local-apk-btn"
                    size="small"
                    :disabled="installingIme || !deviceId"
                    @click="installLocalApk"
                  >
                    {{ t('automation.tools.imeInstallLocal') }}
                  </n-button>
                </span>
              </template>
              {{ t('automation.tools.imeNeedDevice') }}
            </n-tooltip>
          </div>

          <!-- download progress (only flows in the online-download phase) -->
          <div v-if="imeProgress" data-testid="ime-progress" class="tim-progress">
            <n-progress type="line" :percentage="imeProgress.progress" />
          </div>

          <!-- streaming install log (last N lines, auto-scroll) -->
          <div v-if="imeLogs.length || installingIme" class="tim-log-wrap">
            <div class="tim-log-label">{{ t('automation.tools.installLog') }}</div>
            <div ref="imeLogEl" data-testid="ime-log" class="tim-log">
              <div v-for="(line, i) in imeLogs" :key="i" class="tim-log-line">{{ line }}</div>
            </div>
          </div>

          <div v-if="imeError" data-testid="ime-error" class="tim-error">{{ imeError }}</div>

          <!-- GitHub repo: selectable TEXT + copy button; deliberately no external link -->
          <div class="tim-row tim-repo-row">
            <span class="tim-hint">{{ t('automation.tools.imeRepo') }}:</span>
            <span class="tim-mono tim-repo">{{ IME_REPO_URL }}</span>
            <IconButton
              :icon="Copy"
              :label="t('automation.tools.copyRepoUrl')"
              data-testid="copy-repo-btn"
              size="tiny"
              quaternary
              @click="copyRepoUrl"
            />
            <span v-if="copied === 'repo'" class="tim-copied">{{ t('automation.copied') }}</span>
          </div>

          <!-- tutorial -->
          <div class="tim-tutorial">
            <div class="tim-hint">{{ t('automation.tools.tutorialTitle') }}</div>
            <ol class="tim-steps">
              <li v-for="k in IME_TUTORIAL" :key="k">{{ t('automation.tools.tutorial.ime.' + k) }}</li>
            </ol>
          </div>
        </section>
      </template>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NModal, NProgress, NSpin, NTooltip } from 'naive-ui'
import { AlertCircle, CheckCircle, Copy } from 'lucide-vue-next'
import IconButton from '@components/common/IconButton.vue'
import serviceManager from '@services/ServiceManager'
import {
  INSTALL_IDLE_TIMEOUT,
  type TerminalPayload,
  type TrafficStatus,
  type ImeStatus,
} from '@services/AutomationService'

const props = defineProps<{
  show: boolean
  deviceId: string
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'changed'): void
}>()

const { t } = useI18n()

// Same DI path as the automation page: services come from the ServiceManager.
async function autoSvc() {
  return serviceManager.getService('automation')
}
async function sysSvc() {
  return serviceManager.getService('system')
}

const IME_REPO_URL = 'https://github.com/senzhk/ADBKeyBoard'
const TRAFFIC_TUTORIAL = ['s1', 's2', 's3', 's4']
const IME_TUTORIAL = ['s1', 's2', 's3']
const MAX_LOG_LINES = 200

// ---------------------------------------------------------------- state --
const probing = ref(false)
const trafficStatus = ref<TrafficStatus | null>(null)
const imeStatus = ref<ImeStatus | null>(null)

const installingMitm = ref(false)
const installingIme = ref(false)
const installingCa = ref(false)

const mitmLogs = ref<string[]>([])
const imeLogs = ref<string[]>([])
const imeProgress = ref<{ progress: number; downloaded: number; total: number; speed: string } | null>(null)

const mitmError = ref('')
const imeError = ref('')
const caError = ref('')
const caOk = ref(false)
const copied = ref<'' | 'command' | 'repo'>('')

/** Degraded terminal payload — the promise RESOLVED with "install failed,
 *  here is the exact manual command" (review M1 consumer side). */
const degraded = ref<TerminalPayload | null>(null)

const trafficOk = computed(() => !!trafficStatus.value?.ready)
const trafficStateKey = computed(() => {
  const s = trafficStatus.value
  if (!s) return 'automation.tools.statusUnknown'
  if (s.ready) return 'automation.tools.statusReady'
  if (s.python_mismatch) return 'automation.tools.statusVersionMismatch'
  return 'automation.tools.statusNotInstalled'
})

const imeStateKey = computed(() => {
  const s = imeStatus.value
  if (!s) return 'automation.tools.statusUnknown'
  if (s.installed) return 'automation.tools.imeInstalled'
  return 'automation.tools.imeNotInstalled'
})

/** CA cert path is not part of TrafficStatus — it is the deterministic
 *  backend layout `<dir-of-lib>/conf/mitmproxy-ca-cert.pem`. Derived only
 *  when the cert actually exists (never probed speculatively). */
const certPath = computed(() => {
  if (!trafficStatus.value?.ca_cert_exists) return ''
  const lib = trafficStatus.value.lib_path || ''
  const base = lib.replace(/[\\/][^\\/]*$/, '')
  return base ? `${base}/conf/mitmproxy-ca-cert.pem` : ''
})

const caBlocked = computed(() =>
  installingCa.value || !props.deviceId || !trafficStatus.value?.ca_cert_exists,
)

// ----------------------------------------------------------------- open --
watch(() => props.show, (v) => {
  if (!v) return
  // Reset the installing flags too: an install whose stream went silent
  // (watchdog) or a wedged previous session must never keep the buttons
  // loading/disabled after the modal is reopened.
  installingMitm.value = false
  installingIme.value = false
  installingCa.value = false
  mitmLogs.value = []
  imeLogs.value = []
  imeProgress.value = null
  degraded.value = null
  mitmError.value = ''
  imeError.value = ''
  caError.value = ''
  caOk.value = false
  copied.value = ''
  void probeAll()
})

async function probeAll() {
  probing.value = true
  try {
    const automation = await autoSvc()
    // force=true on BOTH probes — a just-finished install must be seen.
    trafficStatus.value = await automation.getTrafficStatus(true)
    imeStatus.value = props.deviceId ? await automation.getImeStatus(props.deviceId) : null
  } catch {
    // getService failures land here; probes themselves resolve to null
  } finally {
    probing.value = false
  }
}

/** Any successful install → tell the page (it clears the probe cache and
 *  refreshes its own status), then re-probe here with force. */
function changed() {
  emit('changed')
  void probeAll()
}

// ------------------------------------------------------------- handlers --
function pushLog(list: Ref<string[]>, line: string) {
  list.value = [...list.value, line].slice(-MAX_LOG_LINES)
}

/** Watchdog sentinel → the i18n idle-timeout text (the install may still be
 *  running in the background); any other error keeps its raw message. */
function errorMessage(e: unknown): string {
  const msg = (e as any)?.message || String(e)
  return msg === INSTALL_IDLE_TIMEOUT ? t('automation.tools.installIdleTimeout') : msg
}

async function installMitm() {
  if (installingMitm.value) return
  installingMitm.value = true
  mitmError.value = ''
  degraded.value = null
  mitmLogs.value = []
  try {
    const automation = await autoSvc()
    const payload = await automation.installMitmproxy({
      onLog: (line) => pushLog(mitmLogs, line),
    })
    // Terminal promise contract: degraded is a RESOLVED "failure with a way
    // out" (manual command block), not an error; only rejections error out.
    if (payload?.degraded) {
      degraded.value = payload
    } else {
      changed()
    }
  } catch (e: any) {
    mitmError.value = errorMessage(e)
  } finally {
    installingMitm.value = false
  }
}

async function installImeOnline() {
  if (installingIme.value || !props.deviceId) return
  installingIme.value = true
  imeError.value = ''
  imeLogs.value = []
  imeProgress.value = null
  try {
    const automation = await autoSvc()
    const payload = await automation.installIme(props.deviceId, {
      onLog: (line) => pushLog(imeLogs, line),
      onProgress: (p: any) => { imeProgress.value = p },
    })
    if (payload?.success === false) {
      imeError.value = payload?.error || payload?.message || t('automation.tools.installFailed')
    } else {
      changed()
    }
  } catch (e: any) {
    imeError.value = errorMessage(e)
  } finally {
    installingIme.value = false
    imeProgress.value = null
  }
}

async function installLocalApk() {
  if (installingIme.value || !props.deviceId) return
  imeError.value = ''
  try {
    const system = await sysSvc()
    const res = await system.selectFile({
      title: t('automation.tools.imeInstallLocal'),
      filters: [{ name: 'APK', extensions: ['apk'] }],
    })
    const path = res?.filePaths?.[0]
    if (!path) return // picker canceled
    installingIme.value = true
    imeLogs.value = []
    const automation = await autoSvc()
    const payload = await automation.installIme(props.deviceId, undefined, path)
    if (payload?.success === false) {
      imeError.value = payload?.error || payload?.message || t('automation.tools.installFailed')
    } else {
      changed()
    }
  } catch (e: any) {
    imeError.value = errorMessage(e)
  } finally {
    installingIme.value = false
  }
}

async function installCaCert() {
  if (caBlocked.value) return
  installingCa.value = true
  caError.value = ''
  caOk.value = false
  try {
    const automation = await autoSvc()
    const res = await automation.installCa(props.deviceId)
    if (res?.success === false) {
      caError.value = res?.error || t('automation.tools.installFailed')
    } else {
      caOk.value = true
      changed()
    }
  } catch (e: any) {
    caError.value = e?.message || String(e)
  } finally {
    installingCa.value = false
  }
}

// ----------------------------------------------------------------- copy --
function flashCopied(which: 'command' | 'repo') {
  copied.value = which
  setTimeout(() => { if (copied.value === which) copied.value = '' }, 1500)
}

async function copyCommand() {
  const cmd = degraded.value?.manual_command || ''
  if (!cmd) return
  try {
    const system = await sysSvc()
    await system.copyText(cmd)
    flashCopied('command')
  } catch { /* clipboard unavailable — the block is selectable text */ }
}

async function copyRepoUrl() {
  try {
    const system = await sysSvc()
    await system.copyText(IME_REPO_URL)
    flashCopied('repo')
  } catch { /* clipboard unavailable — the URL is selectable text */ }
}

// ----------------------------------------------------------------- open --
/** Parent dir of lib_path (the runtime mitmproxy folder). openPath on a
 *  directory opens Explorer on it (reveal semantics). */
function openRuntimeFolder() {
  const lib = degraded.value?.lib_path || trafficStatus.value?.lib_path || ''
  const parent = lib.replace(/[\\/][^\\/]*$/, '')
  const target = parent || lib
  if (!target) return
  void sysSvc().then((s) => s.openPath(target)).catch(() => {})
}

/** The cert FILE itself → openPath reveals it selected in Explorer. */
function openCertFolder() {
  if (!certPath.value) return
  void sysSvc().then((s) => s.openPath(certPath.value)).catch(() => {})
}

// --------------------------------------------------------- log auto-scroll
const mitmLogEl = ref<HTMLElement | null>(null)
const imeLogEl = ref<HTMLElement | null>(null)

async function scrollToBottom(elRef: Ref<HTMLElement | null>) {
  await nextTick()
  const el = elRef.value
  if (el) el.scrollTop = el.scrollHeight
}
watch(() => mitmLogs.value.length, () => { void scrollToBottom(mitmLogEl) })
watch(() => imeLogs.value.length, () => { void scrollToBottom(imeLogEl) })
</script>

<style scoped>
.tim-root { display: flex; flex-direction: column; gap: 20px; }
.tim-block { display: flex; flex-direction: column; gap: 10px; }

/* status row：与设置页状态行同一套视觉，页面局部类 */
.tim-row { display: flex; align-items: flex-start; gap: 10px; }
.tim-icon { flex: none; display: flex; padding-top: 2px; }
.tim-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.tim-line { font-size: var(--app-font-size-sm); color: var(--app-text-primary); line-height: 1.55; }
.tim-mono { font-family: var(--app-font-mono); word-break: break-all; color: var(--app-text-secondary); }
.tim-hint { font-size: var(--app-font-size-sm); color: var(--app-text-muted); line-height: 1.55; }

.tim-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.tim-btn-wrap { display: inline-flex; }

/* streaming log mini-window */
.tim-log-wrap { display: flex; flex-direction: column; gap: 4px; }
.tim-log-label { font-size: var(--app-font-size-xs); color: var(--app-text-muted); }
.tim-log {
  max-height: 140px; overflow: auto; padding: 6px 8px;
  background: var(--app-body-bg); border: 1px solid var(--app-card-border);
  border-radius: 6px; scrollbar-gutter: stable; overscroll-behavior: contain;
}
.tim-log-line {
  font-family: var(--app-font-mono); font-size: var(--app-font-size-xs);
  color: var(--app-text-secondary); white-space: pre-wrap; word-break: break-all; line-height: 1.5;
}

/* errors / success / degraded */
.tim-error { font-size: var(--app-font-size-sm); color: var(--app-red); line-height: 1.55; word-break: break-all; }
.tim-ok { font-size: var(--app-font-size-sm); color: var(--app-green); }
.tim-degraded {
  display: flex; flex-direction: column; gap: 6px; padding: 10px;
  border: 1px solid var(--app-yellow); border-radius: 8px;
}
.tim-warn { font-size: var(--app-font-size-sm); color: var(--app-yellow); line-height: 1.55; }
.tim-mono-block {
  font-family: var(--app-font-mono); font-size: var(--app-font-size-xs);
  color: var(--app-text-primary); background: var(--app-body-bg);
  border: 1px solid var(--app-card-border); border-radius: 6px;
  padding: 8px; white-space: pre-wrap; word-break: break-all;
  user-select: text; cursor: text;
}
.tim-copied { font-size: var(--app-font-size-xs); color: var(--app-green); }

.tim-progress { display: flex; align-items: center; gap: 8px; }
.tim-repo-row { align-items: center; }
.tim-repo { user-select: text; cursor: text; }

/* tutorials */
.tim-tutorial { display: flex; flex-direction: column; gap: 4px; }
.tim-steps { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 2px; }
.tim-steps li { font-size: var(--app-font-size-sm); color: var(--app-text-muted); line-height: 1.55; }

.tim-probing { display: flex; justify-content: center; padding: 24px 0; }
</style>
