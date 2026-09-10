<template>
  <n-modal :show="show" :title="t('automation.elements')" preset="card" style="width: 520px" @update:show="emit('update:show', $event)">
    <p class="muted">{{ t('automation.pickHint') }}</p>

    <!-- dumping in progress: show a spinner instead of looking frozen -->
    <div v-if="dumping" class="dumping">
      <n-spin size="medium" />
      <p class="muted dumping-hint">{{ t('automation.dumpingHint') }}</p>
    </div>

    <template v-else>
      <n-empty v-if="!elements.length" :description="t('automation.noElements')" size="small" />
      <n-list v-else bordered class="elem-list">
        <n-list-item v-for="(el, i) in elements" :key="i" @click="emit('apply', el)" class="elem-item">
          <div class="elem-main">
            <div class="elem-label-row">
              <span class="elem-label">{{ el.label }}</span>
              <span v-if="el.clickable" class="elem-click">{{ t('automation.clickable') }}</span>
              <span v-if="el.matchCount > 1" class="elem-multi">{{ t('automation.multiMatch', { n: el.matchCount }) }}</span>
            </div>
            <span class="elem-by">{{ el.by }} = {{ el.value }}</span>
          </div>
          <span class="elem-bounds">{{ el.bounds }}</span>
        </n-list-item>
      </n-list>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NModal, NList, NListItem, NEmpty, NSpin } from 'naive-ui'
import type { UiNode } from '@components/automation/uiDump'

defineProps<{
  show: boolean
  dumping: boolean
  elements: UiNode[]
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'apply', el: UiNode): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.muted { color: var(--app-text-muted); font-size: 12px; }
.dumping { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 40px 0; }
.dumping-hint { margin: 0; }
.elem-list { max-height: 360px; overflow: auto; }
.elem-item { cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.elem-item:hover { background: var(--app-blue-bg); }
.elem-main { display: flex; flex-direction: column; min-width: 0; }
.elem-label-row { display: flex; align-items: center; gap: 6px; min-width: 0; }
.elem-label { font-size: 13px; color: var(--app-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.elem-click { flex: 0 0 auto; font-size: 10px; line-height: 16px; color: var(--app-green); border: 1px solid currentColor; border-radius: 3px; padding: 0 4px; }
.elem-multi { flex: 0 0 auto; font-size: 10px; line-height: 16px; color: var(--app-warning, #d97706); border: 1px solid currentColor; border-radius: 3px; padding: 0 4px; }
.elem-by { font-size: 11px; color: var(--app-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.elem-bounds { font-size: 10.5px; color: var(--app-text-muted); flex: 0 0 auto; }
</style>
