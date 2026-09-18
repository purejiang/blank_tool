<template>
  <div class="run-controls">
    <div class="run-controls-row">
      <n-select
        :value="autoDeviceId"
        :options="deviceOptions"
        size="small"
        :placeholder="t('automation.selectDevice')"
        @update:value="emit('update:autoDeviceId', $event)"
      />
      <n-tooltip v-if="!running" :disabled="canRun" placement="top">
        <template #trigger>
          <n-button type="primary" size="small" :disabled="!canRun" class="run-btn" @click="emit('run')">
            <template #icon><n-icon><Play /></n-icon></template>
            {{ t('automation.run') }}
          </n-button>
        </template>
        {{ !autoDeviceId ? t('automation.noDevice') : t('automation.noScriptSelected') }}
      </n-tooltip>
      <n-button v-else type="warning" size="small" class="run-btn" @click="emit('stop')">
        <template #icon><n-icon><Square /></n-icon></template>
        {{ t('automation.stop') }}
      </n-button>
      <!-- 次级入口收进一个菜单：运行配置 / 运行记录（各自开弹窗）。行里只多一个
           按钮，但抓包状态必须仍然一眼可见 —— captureTraffic 打开时按钮右上角
           带一个圆点（tooltip 依旧说明它会改写设备代理）。 -->
      <n-dropdown
        trigger="click"
        placement="bottom-end"
        :options="menuOptions"
        @select="onMenuSelect"
      >
        <IconButton
          :icon="MoreHorizontal"
          :label="menuTip"
          :aria-label="t('automation.runMenu')"
          size="small"
          quaternary
          class="run-menu-btn"
        >
          <span v-if="captureTraffic" class="run-dot" />
        </IconButton>
      </n-dropdown>
    </div>
    <!-- non-blocking preflight hints (missing mitmproxy / ADBKeyBoard) -->
    <div v-if="hints.length" class="run-hints">
      <div v-for="(h, i) in hints" :key="i" class="run-hint">{{ h }}</div>
    </div>

    <!-- ============ run settings dialog ============ -->
    <!-- 运行配置：两栏（抓包 / 输入 / 异常处理）。值实时绑定到页面状态
         （后端在开跑时读取），所以弹窗里没有「确定」，关掉即可。 -->
    <RunConfigDialog
      :show="configOpen"
      :device-id="autoDeviceId"
      :capture-traffic="captureTraffic"
      :traffic-host-filter="trafficHostFilter"
      :continue-on-error="!!continueOnError"
      :abort-on-crash="abortOnCrash !== false"
      :enable-chinese-input="enableChineseInput !== false"
      :step-interval-ms="stepIntervalMs"
      :traffic-status="trafficStatus || null"
      :ime-status="imeStatus || null"
      :capture-unavailable="captureUnavailable"
      :detecting="detecting || ''"
      :installing-ca="installingCa"
      :resetting-traffic="resettingTraffic"
      @update:show="configOpen = $event"
      @update:capture-traffic="emit('update:captureTraffic', $event)"
      @update:traffic-host-filter="emit('update:trafficHostFilter', $event)"
      @update:continue-on-error="emit('update:continueOnError', $event)"
      @update:abort-on-crash="emit('update:abortOnCrash', $event)"
      @update:enable-chinese-input="emit('update:enableChineseInput', $event)"
      @update:step-interval-ms="emit('update:stepIntervalMs', $event)"
      @detect="emit('detect', $event)"
      @open-tools="emit('openTools', $event)"
      @install-ca="emit('installCa')"
      @reset-traffic="emit('resetTraffic')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDropdown, NIcon, NSelect, NTooltip } from 'naive-ui'
import { MoreHorizontal, Play, Square } from 'lucide-vue-next'
import IconButton from '@components/common/IconButton.vue'
import RunConfigDialog from './RunConfigDialog.vue'
import { useDeviceStore } from '@stores/deviceStore'
import type { TrafficStatus, ImeStatus } from '@services/AutomationService'

const props = withDefaults(defineProps<{
  autoDeviceId: string
  /** Run-time option: capture network traffic for this run. */
  captureTraffic: boolean
  /** Comma-separated host substrings; only matching hosts are recorded. */
  trafficHostFilter: string
  /** 步骤失败后继续执行下一步（默认 false：首个失败就中止运行）。 */
  continueOnError?: boolean
  /** 目标应用进程消失/重启时中止运行（默认 true）。 */
  abortOnCrash?: boolean
  /** 允许运行时切换输入法输入中文（默认 true）。 */
  enableChineseInput?: boolean
  /** 步骤之间的默认等待（ms，0 = 不等待）。 */
  stepIntervalMs?: number
  running: boolean
  canRun: boolean
  /** Non-blocking preflight warnings rendered under the controls row. */
  hints?: string[]
  /** capture is on but this machine can't capture (mitmproxy missing or the
   *  Python version doesn't match) — shown inside the settings dialog. */
  captureUnavailable?: boolean
  /** 运行记录条数：菜单项带个数字，不用打开就知道有没有历史 */
  historyCount?: number
  /** 运行配置弹窗里的状态展示（页面持有探测） */
  trafficStatus?: TrafficStatus | null
  imeStatus?: ImeStatus | null
  detecting?: '' | 'traffic' | 'ime'
  installingCa?: boolean
  resettingTraffic?: boolean
}>(), {
  // Boolean prop 未传时 Vue 会强转成 false —— 「崩溃即中止 / 中文输入」的语义
  // 默认是「开」，必须显式给默认值，否则未传就变成关。
  continueOnError: false,
  abortOnCrash: true,
  enableChineseInput: true,
  // 页面总会传入持久化的值；这个 0 只是组件单独挂载（测试）时的中性兜底，
  // 真正的默认间隔在 AUTOMATION_UI_DEFAULTS 里（300ms）。
  stepIntervalMs: 0,
})

const emit = defineEmits<{
  (e: 'update:autoDeviceId', v: string): void
  (e: 'update:captureTraffic', v: boolean): void
  (e: 'update:trafficHostFilter', v: string): void
  (e: 'update:continueOnError', v: boolean): void
  (e: 'update:abortOnCrash', v: boolean): void
  (e: 'update:enableChineseInput', v: boolean): void
  (e: 'update:stepIntervalMs', v: number): void
  (e: 'run'): void
  (e: 'stop'): void
  /** 菜单里选了「运行记录」—— 列表数据在页面，这里只发请求 */
  (e: 'openHistory'): void
  (e: 'detect', target: 'traffic' | 'ime'): void
  (e: 'openTools', target: 'traffic' | 'ime'): void
  (e: 'installCa'): void
  (e: 'resetTraffic'): void
}>()

const { t } = useI18n()
const deviceStore = useDeviceStore()
const deviceOptions = computed(() =>
  deviceStore.devices.map((d: any) => ({
    label: `${d.name || d.id}${d.status ? ' (' + d.status + ')' : ''}`,
    value: d.id,
  })),
)
const hints = computed(() => props.hints ?? [])

/** Run-settings dialog (traffic capture + chinese input + failure policy). */
const configOpen = ref(false)
/** 菜单按钮的 tooltip：**故意只留一行**。抓包会改写设备代理，这个状态不能藏，
 *  但细节（具体过滤条件）在设置弹窗里已经列全了 —— hover 时铺开一长串文字只会
 *  挡住视线，圆点 + 「抓包已开启」就够。 */
const menuTip = computed(() =>
  props.captureTraffic ? t('automation.runMenuTipOn') : t('automation.runMenuTip'),
)

/** 次级入口的弹出列表：运行配置（抓包 / 输入 / 异常处理）与运行记录（历史）。 */
const menuOptions = computed(() => [
  { key: 'settings', label: t('automation.runConfig') },
  {
    key: 'history',
    label: props.historyCount
      ? `${t('automation.runHistory')} (${props.historyCount})`
      : t('automation.runHistory'),
  },
])

function onMenuSelect(key: string | number) {
  if (key === 'settings') configOpen.value = true
  else if (key === 'history') emit('openHistory')
}
</script>

<style scoped>
/* single root so the parent column can lay it out; ONE row — the device
   select absorbs the slack, then the two actions (run, run settings).
   What a run captures lives in the settings dialog, not on the row. */
.run-controls { display: flex; flex-direction: column; gap: 6px; flex: none; }
.run-controls-row { display: flex; align-items: center; gap: 8px; }
.run-controls-row :deep(.n-select) { flex: 1; min-width: 0; }
.run-btn { flex: none; }
.run-menu-btn { flex: none; position: relative; }
/* 抓包开着必须一眼可见：收进菜单后，除了 tooltip 就只剩这个圆点 */
.run-dot {
  position: absolute; top: 3px; right: 3px;
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--app-yellow);
}
.run-hints { display: flex; flex-direction: column; gap: 2px; }
.run-hint { font-size: var(--app-font-size-sm); color: var(--app-text-muted); }
</style>
