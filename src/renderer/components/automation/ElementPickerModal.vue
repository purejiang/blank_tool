<template>
  <AppModal
    :show="show"
    :title="t('automation.elements')"
    :width="520"
    @update:show="emit('update:show', $event)"
  >
    <p class="app-muted">{{ t('automation.pickHint') }}</p>

    <!-- dumping in progress: show a spinner instead of looking frozen -->
    <div v-if="dumping" class="dumping">
      <n-spin size="medium" />
      <p class="app-muted dumping-hint">{{ t('automation.dumpingHint') }}</p>
    </div>

    <template v-else>
      <n-empty v-if="!elements.length" :description="t('automation.noElements')" size="small" />
      <n-list v-else bordered class="elem-list">
        <n-list-item v-for="(el, i) in elements" :key="i" @click="emit('apply', el)" class="elem-item">
          <div class="elem-main">
            <div class="elem-label-row">
              <span class="elem-label" :title="el.label">{{ el.label }}</span>
              <span v-if="el.clickable" class="elem-click">{{ t('automation.clickable') }}</span>
              <span v-if="el.editable" class="elem-edit">{{ t('automation.editable') }}</span>
              <span v-if="el.matchCount > 1" class="elem-multi">{{ t('automation.multiMatch', { n: el.matchCount }) }}</span>
            </div>
            <span class="elem-by" :title="`${el.by} = ${el.value}`">{{ el.by }} = {{ el.value }}</span>
          </div>
          <span class="elem-bounds">{{ el.bounds }}</span>
        </n-list-item>
      </n-list>
    </template>
  </AppModal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NList, NListItem, NEmpty, NSpin } from 'naive-ui'
import AppModal from '@components/common/AppModal.vue'
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
.dumping { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 40px 0; }
.dumping-hint { margin: 0; }
  .elem-list { max-height: 360px; overflow: auto; scrollbar-gutter: stable; overscroll-behavior: contain; }
.elem-item { cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.elem-item:hover { background: var(--app-blue-bg); }
.elem-main { display: flex; flex-direction: column; min-width: 0; }
.elem-label-row { display: flex; align-items: center; gap: 6px; min-width: 0; }
.elem-label { font-size: var(--app-font-size-md); color: var(--app-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.elem-click { flex: 0 0 auto; font-size: var(--app-font-size-xs); line-height: 16px; color: var(--app-green); border: 1px solid currentColor; border-radius: 3px; padding: 0 4px; }
.elem-edit { flex: 0 0 auto; font-size: var(--app-font-size-xs); line-height: 16px; color: var(--app-blue); border: 1px solid currentColor; border-radius: 3px; padding: 0 4px; }
.elem-multi { flex: 0 0 auto; font-size: var(--app-font-size-xs); line-height: 16px; color: var(--app-yellow); border: 1px solid currentColor; border-radius: 3px; padding: 0 4px; }
.elem-by { font-size: var(--app-font-size-xs); color: var(--app-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.elem-bounds { font-size: var(--app-font-size-xs); color: var(--app-text-muted); flex: 0 0 auto; }
</style>
