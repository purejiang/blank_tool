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
    <!-- Everything that changes WHAT a run captures lives here. The values are
         live-bound to the page state (read by the backend when a run starts),
         so there is nothing to confirm — just close. -->
    <n-modal
      v-model:show="configOpen"
      preset="card"
      :title="t('automation.runConfig')"
      style="width: 420px"
    >
      <div class="rcf-block">
        <div class="rcf-head">
          <span class="rcf-label">{{ t('automation.captureTraffic') }}</span>
          <n-switch
            size="small"
            :value="captureTraffic"
            @update:value="emit('update:captureTraffic', $event)"
          />
        </div>
        <div class="rcf-hint">{{ t('automation.captureTrafficHint') }}</div>
        <div v-if="captureTraffic && captureUnavailable" class="rcf-warn">
          {{ t('automation.captureTrafficUnavailable') }}
        </div>
      </div>
      <div class="rcf-block" :class="{ 'is-off': !captureTraffic }">
        <span class="rcf-label">{{ t('automation.captureFilter') }}</span>
        <n-dynamic-tags
          class="rcf-input"
          size="small"
          :value="filterTags"
          :disabled="!captureTraffic"
          :max="20"
          :input-props="{ placeholder: t('automation.captureFilterPlaceholder') }"
          @update:value="onFilterTags"
        />
        <div class="rcf-hint">{{ t('automation.captureFilterHint') }}</div>
      </div>
      <template #footer>
        <n-space justify="end">
          <n-button size="small" @click="configOpen = false">{{ t('common.close') }}</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDropdown, NDynamicTags, NIcon, NModal, NSelect, NSpace, NSwitch, NTooltip } from 'naive-ui'
import { MoreHorizontal, Play, Square } from 'lucide-vue-next'
import IconButton from '@components/common/IconButton.vue'
import { useDeviceStore } from '@stores/deviceStore'

const props = defineProps<{
  autoDeviceId: string
  /** Run-time option: capture network traffic for this run. */
  captureTraffic: boolean
  /** Comma-separated host substrings; only matching hosts are recorded. */
  trafficHostFilter: string
  running: boolean
  canRun: boolean
  /** Non-blocking preflight warnings rendered under the controls row. */
  hints?: string[]
  /** capture is on but this machine can't capture (mitmproxy missing or the
   *  Python version doesn't match) — shown inside the settings dialog. */
  captureUnavailable?: boolean
  /** 运行记录条数：菜单项带个数字，不用打开就知道有没有历史 */
  historyCount?: number
}>()

const emit = defineEmits<{
  (e: 'update:autoDeviceId', v: string): void
  (e: 'update:captureTraffic', v: boolean): void
  (e: 'update:trafficHostFilter', v: string): void
  (e: 'run'): void
  (e: 'stop'): void
  /** 菜单里选了「运行记录」—— 列表数据在页面，这里只发请求 */
  (e: 'openHistory'): void
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

/** Run-settings dialog (traffic capture + host filter). */
const configOpen = ref(false)
/** Filter conditions as a tag list — a comma-separated string field is not
 *  obvious to fill in (and easy to get wrong). */
const filterTags = computed(() =>
  props.trafficHostFilter.split(',').map((s) => s.trim()).filter(Boolean),
)
/** tags → the comma-joined string the backend reads. `,` is the wire
 *  separator, so it can never live inside a single condition. */
function onFilterTags(tags: string[]) {
  emit(
    'update:trafficHostFilter',
    tags.map((s) => s.replace(/,/g, ' ').trim()).filter(Boolean).join(','),
  )
}
/** 菜单按钮的 tooltip：**故意只留一行**。抓包会改写设备代理，这个状态不能藏，
 *  但细节（具体过滤条件）在设置弹窗里已经列全了 —— hover 时铺开一长串文字只会
 *  挡住视线，圆点 + 「抓包已开启」就够。 */
const menuTip = computed(() =>
  props.captureTraffic ? t('automation.runMenuTipOn') : t('automation.runMenuTip'),
)

/** 次级入口的弹出列表：运行配置（抓包 + 域名过滤）与运行记录（历史）。 */
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

/* ---- run settings dialog ---- */
/* teleported by n-modal, but the vnodes are created here, so the scoped
   attribute still lands on them */
.rcf-block { display: flex; flex-direction: column; gap: 6px; }
.rcf-block + .rcf-block { margin-top: 16px; }
.rcf-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.rcf-label { font-size: var(--app-font-size-md); color: var(--app-text-primary); }
.rcf-hint { font-size: var(--app-font-size-sm); line-height: 1.55; color: var(--app-text-muted); }
.rcf-warn { font-size: var(--app-font-size-sm); line-height: 1.55; color: var(--app-red); }
.rcf-input { width: 100%; }
.rcf-block.is-off .rcf-label,
.rcf-block.is-off .rcf-hint { opacity: .55; }
</style>
