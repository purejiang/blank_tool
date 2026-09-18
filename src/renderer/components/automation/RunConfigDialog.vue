<template>
  <AppModal
    :show="show"
    :title="t('automation.runConfig')"
    :width="640"
    @update:show="emit('update:show', $event)"
  >
    <div class="rcfg-body">
      <!-- 左栏：抓包 / 输入 / 异常处理（tablist + 键盘操作） -->
      <aside class="rcfg-nav" role="tablist" aria-orientation="vertical">
        <div
          v-for="tab in tabs"
          :key="tab.key"
          class="app-nav-item"
          :class="{ active: tab.key === activeTab }"
          role="tab"
          :aria-selected="tab.key === activeTab"
          :tabindex="tab.key === activeTab ? 0 : -1"
          @click="activeTab = tab.key"
          @keydown="onNavKeydown($event)"
        >
          <n-icon size="14"><component :is="tab.icon" /></n-icon>
          <span>{{ tab.label }}</span>
        </div>
      </aside>

      <section class="rcfg-panel">
        <!-- ==================== 抓包 ==================== -->
        <template v-if="activeTab === 'capture'">
          <!-- 第一行：是否开启抓包 -->
          <div class="rcfg-row">
            <div class="rcfg-info">
              <div class="rcfg-label">{{ t('automation.captureTraffic') }}</div>
              <div class="rcfg-hint">
                {{ captureLocked ? t('automation.captureDisabledHint') : t('automation.captureTrafficHint') }}
              </div>
            </div>
            <n-switch
              size="small"
              :value="captureTraffic"
              :disabled="captureLocked"
              @update:value="emit('update:captureTraffic', $event)"
            />
          </div>
          <div v-if="captureTraffic && captureUnavailable" class="rcfg-warn">
            {{ t('automation.captureTrafficUnavailable') }}
          </div>

          <!-- 第二行：抓包工具（没有它就不能开启抓包） -->
          <div class="rcfg-tool">
            <div class="rcfg-info">
              <div class="rcfg-tool-title">{{ t('automation.tools.sectionTraffic') }}</div>
              <!-- 状态一行放下：工具状态 + 设备连接状态（原先各占一行，弹窗里太占高） -->
              <div class="rcfg-state">
                <n-icon size="14" :style="{ color: trafficReady ? 'var(--app-green)' : 'var(--app-yellow)' }">
                  <CheckCircle v-if="trafficReady" /><AlertCircle v-else />
                </n-icon>
                <span>{{ trafficStateText }}</span>
                <span v-if="deviceStateText" class="rcfg-state-side">· {{ deviceStateText }}</span>
              </div>
              <div
                v-if="trafficStatus?.lib_path"
                class="rcfg-mono"
                :title="trafficStatus.lib_path"
              >{{ trafficStatus.lib_path }}</div>
            </div>
            <div class="rcfg-ops">
              <n-button size="tiny" secondary :loading="detecting === 'traffic'" @click="emit('detect', 'traffic')">
                {{ t('automation.detect') }}
              </n-button>
              <n-button size="tiny" type="primary" secondary @click="emit('openTools', 'traffic')">
                {{ trafficReady ? t('automation.tools.reinstall') : t('automation.installTool') }}
              </n-button>
            </div>
          </div>

          <!-- 第三行：CA 证书（没装就引导安装） -->
          <div class="rcfg-tool">
            <div class="rcfg-info">
              <div class="rcfg-tool-title">{{ t('automation.tools.caTitle') }}</div>
              <template v-if="!trafficStatus?.ca_cert_exists">
                <div class="rcfg-hint">{{ t('automation.certNotReady') }}</div>
              </template>
              <div v-else class="rcfg-state">
                <n-icon size="14" :style="{ color: caOnDevice ? 'var(--app-green)' : 'var(--app-yellow)' }">
                  <CheckCircle v-if="caOnDevice" /><AlertCircle v-else />
                </n-icon>
                <span>{{ caOnDevice ? t('automation.certDeviceOk') : t('automation.certDeviceMissing') }}</span>
              </div>
            </div>
            <div v-if="trafficStatus?.ca_cert_exists" class="rcfg-ops">
              <n-button
                size="tiny"
                secondary
                :loading="installingCa"
                :disabled="!deviceId || caOnDevice"
                @click="emit('installCa')"
              >
                {{ t('automation.tools.caInstall') }}
              </n-button>
            </div>
          </div>

          <!-- 过滤条件：一条一行（列表），列表内部滚动 —— 标签云在弹窗里会跟过滤说明
               抢高度、条件一多就放不下。抓包关闭时不可编辑。 -->
          <div class="rcfg-block" :class="{ 'is-off': !captureTraffic }">
            <div class="rcfg-block-head">
              <span class="rcfg-label">{{ t('automation.captureFilter') }}</span>
              <n-tooltip trigger="hover" placement="top">
                <template #trigger>
                  <n-icon size="13" class="rcfg-info-icon"><Info /></n-icon>
                </template>
                {{ t('automation.captureFilterHintDetail') }}
              </n-tooltip>
              <n-button
                size="tiny"
                quaternary
                type="primary"
                class="rcfg-add"
                :disabled="!captureTraffic"
                @click="addFilterRow"
              >
                {{ t('automation.captureFilterAdd') }}
              </n-button>
            </div>

            <!-- 滑动列表：固定高度的盒子，条件再多也只在盒内滚动（不改变弹窗高度）；
                 空态也占同样的高度，避免「加了第一条条件」时整个面板跳一下。 -->
            <div class="rcfg-list">
              <div v-if="!filterRows.length" class="rcfg-empty">
                {{ t('automation.captureFilterEmpty') }}
              </div>
              <div
                v-for="(row, i) in filterRows"
                :key="i"
                class="rcfg-list-row"
                @keyup.enter="addFilterRow"
              >
                <n-input
                  size="tiny"
                  :value="row"
                  :disabled="!captureTraffic"
                  :placeholder="t('automation.captureFilterPlaceholder')"
                  @update:value="(v: string) => onFilterRowInput(i, v)"
                />
                <IconButton
                  :icon="Trash2"
                  :label="t('automation.captureFilterRemove')"
                  size="tiny"
                  quaternary
                  type="error"
                  :disabled="!captureTraffic"
                  @click="removeFilterRow(i)"
                />
              </div>
            </div>

            <div class="rcfg-hint">{{ t('automation.captureFilterHint') }}</div>
          </div>

          <!-- 手动修复：抓包被强杀后设备会卡在已失效的 HTTP 代理上 -->
          <div class="rcfg-actions">
            <n-button size="tiny" quaternary :loading="resettingTraffic" @click="emit('resetTraffic')">
              {{ t('automation.repairProxy') }}
            </n-button>
          </div>
        </template>

        <!-- ==================== 输入 ==================== -->
        <template v-else-if="activeTab === 'input'">
          <!-- 第一行：是否开启中文输入 -->
          <div class="rcfg-row">
            <div class="rcfg-info">
              <div class="rcfg-label">{{ t('automation.enableChineseInput') }}</div>
              <div class="rcfg-hint">{{ t('automation.enableChineseInputHint') }}</div>
            </div>
            <n-switch
              size="small"
              :value="enableChineseInput"
              @update:value="emit('update:enableChineseInput', $event)"
            />
          </div>
          <div v-if="!enableChineseInput" class="rcfg-warn">
            {{ t('automation.inputDisabledHint') }}
          </div>

          <!-- 第二行：ADBKeyBoard（没有它就没法输入中文） -->
          <div class="rcfg-tool">
            <div class="rcfg-info">
              <div class="rcfg-tool-title">{{ t('automation.imeToolTitle') }}</div>
              <div class="rcfg-state">
                <n-icon size="14" :style="{ color: imeInstalled ? 'var(--app-green)' : 'var(--app-yellow)' }">
                  <CheckCircle v-if="imeInstalled" /><AlertCircle v-else />
                </n-icon>
                <span>{{ imeStateText }}</span>
              </div>
              <div class="rcfg-hint">
                {{ t('automation.tools.imeDevice') }}: {{ deviceId || t('automation.tools.imeNoDevice') }}
              </div>
            </div>
            <div class="rcfg-ops">
              <n-button
                size="tiny"
                secondary
                :loading="detecting === 'ime'"
                :disabled="!deviceId"
                @click="emit('detect', 'ime')"
              >
                {{ t('automation.detect') }}
              </n-button>
              <n-button
                size="tiny"
                type="primary"
                secondary
                :disabled="!deviceId"
                @click="emit('openTools', 'ime')"
              >
                {{ t('automation.tools.imeDownloadInstall') }}
              </n-button>
            </div>
          </div>
        </template>

        <!-- ==================== 执行 ==================== -->
        <template v-else-if="activeTab === 'exec'">
          <!-- 步骤间隔：脚本不用手写 wait 步骤也能有节奏。0 = 不插入等待。 -->
          <div class="rcfg-row">
            <div class="rcfg-info">
              <div class="rcfg-label">{{ t('automation.stepInterval') }}</div>
              <div class="rcfg-hint">{{ t('automation.stepIntervalHint') }}</div>
            </div>
            <n-input-number
              size="small"
              class="rcfg-interval"
              :value="stepIntervalMs"
              :min="0"
              :step="50"
              @update:value="(v: number | null) => emit('update:stepIntervalMs', Number(v) || 0)"
            >
              <template #suffix>ms</template>
            </n-input-number>
          </div>
          <div class="rcfg-hint rcfg-hint-block">
            {{ t('automation.stepIntervalStartHint') }}
          </div>
        </template>

        <!-- ==================== 异常处理 ==================== -->
        <template v-else>
          <div class="rcfg-row">
            <div class="rcfg-info">
              <div class="rcfg-label">{{ t('automation.continueOnError') }}</div>
              <div class="rcfg-hint">{{ t('automation.continueOnErrorHint') }}</div>
            </div>
            <n-switch
              size="small"
              :value="continueOnError"
              @update:value="emit('update:continueOnError', $event)"
            />
          </div>
          <div class="rcfg-row">
            <div class="rcfg-info">
              <div class="rcfg-label">{{ t('automation.abortOnCrash') }}</div>
              <div class="rcfg-hint">{{ t('automation.abortOnCrashHint') }}</div>
            </div>
            <n-switch
              size="small"
              :value="abortOnCrash"
              @update:value="emit('update:abortOnCrash', $event)"
            />
          </div>
        </template>
      </section>
    </div>

    <!-- 没有 footer：关闭靠右上角的 X（右上角已经有 X 了，右下角再来个「关闭」是重复的）。
         footer 只留给真正的功能按钮（如运行记录的「刷新」、元信息的「确定」）。 -->
  </AppModal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NInput, NInputNumber, NSwitch, NTooltip } from 'naive-ui'
import { Activity, AlertCircle, CheckCircle, Info, Keyboard, Timer, Trash2, AlertTriangle } from 'lucide-vue-next'
import AppModal from '@components/common/AppModal.vue'
import IconButton from '@components/common/IconButton.vue'
import { handleNavKeydown } from '@utils/navKeys'
import type { TrafficStatus, ImeStatus } from '@services/AutomationService'

const props = defineProps<{
  show: boolean
  /** 当前选中的设备（探测/安装引导都按它来） */
  deviceId: string
  captureTraffic: boolean
  trafficHostFilter: string
  continueOnError: boolean
  abortOnCrash: boolean
  enableChineseInput: boolean
  /** 步骤之间的默认等待（ms，0 = 不等待；单步可用 delay_ms 覆盖） */
  stepIntervalMs: number
  /** 电脑端 + （带设备时）设备端的抓包探测结果 */
  trafficStatus: TrafficStatus | null
  /** 当前设备的 ADBKeyBoard 状态 */
  imeStatus: ImeStatus | null
  /** 抓包开着但本机不可用（沿用页面里的既有警告） */
  captureUnavailable?: boolean
  /** 正在进行的探测（按钮 loading） */
  detecting?: '' | 'traffic' | 'ime'
  installingCa?: boolean
  resettingTraffic?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'update:captureTraffic', v: boolean): void
  (e: 'update:trafficHostFilter', v: string): void
  (e: 'update:continueOnError', v: boolean): void
  (e: 'update:abortOnCrash', v: boolean): void
  (e: 'update:enableChineseInput', v: boolean): void
  (e: 'update:stepIntervalMs', v: number): void
  /** 请求重新探测：traffic = mitmproxy + 设备就绪；ime = ADBKeyBoard */
  (e: 'detect', target: 'traffic' | 'ime'): void
  /** 打开工具安装弹窗（并定位到对应段） */
  (e: 'openTools', target: 'traffic' | 'ime'): void
  (e: 'installCa'): void
  (e: 'resetTraffic'): void
}>()

const { t } = useI18n()

const activeTab = ref<'capture' | 'input' | 'exec' | 'errors'>('capture')
const tabs = computed(() => [
  { key: 'capture' as const, label: t('automation.runConfigCapture'), icon: Activity },
  { key: 'input' as const, label: t('automation.runConfigInput'), icon: Keyboard },
  { key: 'exec' as const, label: t('automation.runConfigExec'), icon: Timer },
  { key: 'errors' as const, label: t('automation.runConfigErrors'), icon: AlertTriangle },
])

/** 左栏 tablist 的键盘操作（方向键/Home/End 切换，Enter/Space 选中） */
function onNavKeydown(event: KeyboardEvent) {
  handleNavKeydown(event, tabs.value.map((tab) => tab.key), activeTab.value, (key) => {
    activeTab.value = key as typeof activeTab.value
  })
}

const trafficReady = computed(() => props.trafficStatus?.ready === true)
/** 没有抓包工具就不允许开启抓包（已经开启的仍可关闭，见 captureUnavailable 警告） */
const captureLocked = computed(() => !trafficReady.value && !props.captureTraffic)
const trafficStateText = computed(() => {
  const s = props.trafficStatus
  if (!s) return t('automation.tools.statusUnknown')
  if (s.ready) return t('automation.tools.statusReady')
  if (s.python_mismatch) return t('automation.tools.statusVersionMismatch')
  return t('automation.tools.statusNotInstalled')
})
/** 设备侧的抓包就绪信息只在带 device_id 探测时才有 */
const caOnDevice = computed(() => props.trafficStatus?.ca_on_device === true)
const deviceStateText = computed(() => {
  if (!props.deviceId) return t('automation.tools.imeNoDevice')
  const state = props.trafficStatus?.device_state
  if (!state) return t('automation.detectNoDevice')
  return state === 'device' ? t('automation.deviceOk') : t('automation.deviceOffline')
})

const imeInstalled = computed(() => props.imeStatus?.installed === true)
const imeStateText = computed(() => {
  const s = props.imeStatus
  if (!s) return t('automation.tools.statusUnknown')
  return s.installed ? t('automation.tools.imeInstalled') : t('automation.tools.imeNotInstalled')
})

/** 过滤条件：一条一行。列表是本地编辑态（允许空行），写回页面时按逗号连接
 *  （`，` 是 wire 分隔符，所以单个条件里不能出现逗号，输入时直接替换成空格）。 */
const filterRows = ref<string[]>([])
/** 最近一次由本组件写出去的值：回灌时跳过，避免输入过程中行被重建（丢光标/空行）。 */
let lastEmittedFilter = ''

function splitFilter(value: string): string[] {
  return String(value || '').split(',').map((s) => s.trim()).filter(Boolean)
}
function normalizeFilter(rows: string[]): string[] {
  return rows.map((s) => String(s ?? '').replace(/,/g, ' ').trim()).filter(Boolean)
}
function emitFilterRows() {
  lastEmittedFilter = normalizeFilter(filterRows.value).join(',')
  emit('update:trafficHostFilter', lastEmittedFilter)
}
function onFilterRowInput(index: number, value: string) {
  const rows = [...filterRows.value]
  rows[index] = value
  filterRows.value = rows
  emitFilterRows()
}
function addFilterRow() {
  if (!props.captureTraffic) return
  filterRows.value = [...filterRows.value, '']
}
function removeFilterRow(index: number) {
  filterRows.value = filterRows.value.filter((_, i) => i !== index)
  emitFilterRows()
}

watch(() => props.trafficHostFilter, (v) => {
  const value = String(v || '')
  if (value === lastEmittedFilter) return
  filterRows.value = splitFilter(value)
}, { immediate: true })
</script>

<style scoped>
/* 两栏：左导航固定宽，右面板吸收剩余宽度 */
.rcfg-body { display: flex; gap: 14px; align-items: stretch; }
.rcfg-nav { width: 104px; flex: none; display: flex; flex-direction: column; gap: 2px; }
/* 面板高度固定：三个页签内容长短不一（抓包最长），如果让 n-card 自适应，切页签时
   整个弹窗会跟着长高/缩小 —— 关闭按钮和标题都会跳。这里给内容区一个固定高度，
   超出时在面板内部滚动（scrollbar-gutter: stable 保证滚动条出现也不改变宽度）。
   直接子元素 flex: none，避免内容过高时被压扁而不是滚动。 */
.rcfg-panel {
  flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px;
  height: 400px;
  overflow-y: auto;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
}
.rcfg-panel > * { flex: none; }

.rcfg-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.rcfg-row + .rcfg-row { margin-top: 0; }
.rcfg-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.rcfg-label { font-size: var(--app-font-size-md); color: var(--app-text-primary); }
.rcfg-tool-title { font-size: var(--app-font-size-sm); font-weight: 600; color: var(--app-text-primary); }
.rcfg-hint { font-size: var(--app-font-size-sm); line-height: 1.55; color: var(--app-text-muted); }
.rcfg-warn { font-size: var(--app-font-size-sm); line-height: 1.55; color: var(--app-red); }
/* 「执行」页签：右侧的数字输入固定宽（默认会被 flex 拉满整行，不好看也不好点） */
.rcfg-interval { width: 120px; flex: none; }
.rcfg-hint-block { padding-top: 2px; }
.rcfg-mono {
  font-family: var(--app-font-mono); font-size: var(--app-font-size-xs);
  color: var(--app-text-muted);
  /* 单行省略：路径很长时换行会把下面的内容顶下去，弹窗高度就不可控了 */
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* 工具行：状态信息在左，检测/安装按钮在右（按钮不换行） */
.rcfg-tool {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  padding: 8px 10px; border: 1px solid var(--app-card-border); border-radius: 8px;
}
.rcfg-state { display: flex; align-items: center; gap: 6px; font-size: var(--app-font-size-sm); color: var(--app-text-secondary); }
.rcfg-state-side { color: var(--app-text-muted); font-size: var(--app-font-size-xs); }
.rcfg-ops { flex: none; display: flex; align-items: center; gap: 6px; }

.rcfg-block { display: flex; flex-direction: column; gap: 6px; }
.rcfg-block.is-off .rcfg-label,
.rcfg-block.is-off .rcfg-hint { opacity: 0.55; }
.rcfg-block-head { display: flex; align-items: center; gap: 6px; }
.rcfg-info-icon { color: var(--app-text-dim); cursor: help; }
.rcfg-add { margin-left: auto; }
/* 域名过滤 = 固定高度的滑动列表：最多约 3 行可见，再多在盒内滚动 */
.rcfg-list {
  height: 88px;
  overflow-y: auto;
  overscroll-behavior: contain;
  border: 1px solid var(--app-card-border);
  border-radius: 6px;
  padding: 4px 6px;
}
.rcfg-list-row { display: flex; align-items: center; gap: 6px; padding-bottom: 4px; }
.rcfg-list-row :deep(.n-input) { flex: 1; min-width: 0; }
.rcfg-empty {
  font-size: var(--app-font-size-sm); color: var(--app-text-dim);
  padding: 6px 0;
}
.rcfg-actions { display: flex; justify-content: flex-end; }
</style>
